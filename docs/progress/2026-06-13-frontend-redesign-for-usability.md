# 前端易用性重设计 — 视觉原语 + IA 对齐 + 合并执行

> **日期**: 2026-06-13
> **状态**: 进行中（共识已达成，Phase 0a 未开始）
> **关联**: `docs/progress/2026-06-13-page-interface-tanstack-query.md`（数据状态轨道）、`docs/progress/STATUS.md`、`docs/active/roadmap.md`

## 目标 (Goal)

把 12 个页面的「使用不直观 / 新手不友好 / 排版样式不一致 / 不够美观」三个叠加问题，通过**抽共享原语 + 重排 IA 对齐业务流 + 在 TanStack Query 迁移过程中同步应用**一次性解决，而不是先迁 TanStack 再返工视觉。

**Why**: 已有的 TanStack Query 迁移计划只解决了「数据状态约定」（loading/error/empty/mutation-refetch 的 12 种写法不一致），没有解决：
- C：用户（项目所有者本人）隔段时间回来忘了具体怎么用 → 没有持续在场的页面定位
- D：冷启动 / 周期空状态没有引导，看到空白页不知道下一步
- 视觉一致性：211 个 inline style 块，fontSize 12/13/14/11/10/16/20/22/28 九种字号没规则，硬编码颜色绕过 theme token

把这两件事合并到一次 per-page 迁移里，避免每个文件被改两次。

## 范围 (Scope)

- **影响模块**: 前端 `src/styles/theme.css`、`src/components/Layout.tsx`、新增 `src/components/primitives/` 目录、12 个页面 + `src/pages/PlansPage.tsx` retrofit
- **不在范围内**:
  - 后端任何改动（schemas / services / routers 全部不动）
  - API 客户端签名（`src/api/client.ts` 不变）
  - 移动端响应式（维持桌面优先，`overflow: hidden + 100vh`）
  - 暗色模式、i18n（维持当前浅色 / 中文 UI）
  - Ant Design 版本、ECharts 版本、zustand 版本

## 设计决策（来自 `/grill-me` 共识）

| 维度 | 决策 | 理由摘要 |
|---|---|---|
| 痛点诊断 | C+D 为主，A 为辅 | 个人工具，"新手"= 隔段时间回来的自己 |
| C 治疗机制 | 标准化 PageHeader，永远在场 | Tour 看完就忘；被动可见优于主动找 |
| 视觉一致性 | 层级 2：抽共享原语 + token 化 | 软规范已验证失效（PageHeader 存在但未起作用） |
| 协同策略 | 策略 1：TanStack + feature-folder + 视觉 三合一，按页 PR | 同一文件改两次的总成本高于一次改透 |
| 页面顺序 | 简单 → 复杂（DataManagement → Cockpit 收尾） | 让原语在简单页面上稳定再攻复杂 |
| IA | 重排导航为 6 组对齐业务流，URL 不变 | 当前"驾驶舱"组混合入口/数据/反思，加剧 C |
| 审美方向 | B1：方向不变 + 允许方向内精细调整 | 不预先 gate reference 页，按 PR review |
| 空状态 | 3 variant（cold / filter / quiet） | 一刀切的空状态会误导（周期空 vs 冷启动） |
| 共享原语 | PageHeader / PageSection / EmptyState / StatCard / FilterBar | 不抽 ConceptHint，靠 PageHeader.purpose 兜底 |

## 接口规格

### 1. Token 扩展（`theme.css` `:root` 追加）

字号 scale 收敛到 5 档，删除中间值（10/11/13/15/18/22/26）。原 `h1~h4` 规则改为引用 token。

```css
:root {
  /* ── Typography Scale (5 档) ─────────────────────────────────────── */
  --fs-xs:  12px;   /* caption / 表格次要文字 / tag */
  --fs-sm:  14px;   /* body 基准 */
  --fs-md:  16px;   /* lead / 强调正文 */
  --fs-lg:  20px;   /* 子区块标题 */
  --fs-xl:  28px;   /* 页面标题 */

  --fw-regular:  400;
  --fw-medium:   500;
  --fw-semibold: 600;
  --fw-bold:     700;

  --lh-tight:   1.2;
  --lh-snug:    1.4;
  --lh-normal:  1.6;

  /* ── Spacing Scale (4px 网格, 7 档) ──────────────────────────────── */
  --sp-1:  4px;
  --sp-2:  8px;
  --sp-3:  12px;
  --sp-4:  16px;
  --sp-6:  24px;
  --sp-8:  32px;
  --sp-12: 48px;

  /* ── Numeric 字体专用（数字一律走 mono） ────────────────────────── */
  --font-numeric: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
}
```

新增 utility 类（`theme.css` 末尾追加一节）：

```css
.num {                          /* 数字单元格：表格/卡片金额/百分比/计数 */
  font-family: var(--font-numeric);
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
  letter-spacing: -0.01em;
}
.num-lg { font-size: var(--fs-xl); font-weight: var(--fw-semibold); }
.num-md { font-size: var(--fs-md); font-weight: var(--fw-medium); }
```

卡片去边框（替换 AntD Card 默认 `border: 1px solid` 行为）：

```css
.ant-card.gojira-card {
  border: none;
  box-shadow: 0 1px 2px rgba(28, 25, 23, 0.04), 0 1px 1px rgba(28, 25, 23, 0.02);
  border-radius: var(--radius-lg);
}
.ant-card.gojira-card:hover {
  box-shadow: 0 2px 6px rgba(28, 25, 23, 0.06), 0 1px 2px rgba(28, 25, 23, 0.03);
}
```

### 2. Layout 重排（`src/components/Layout.tsx` 改 NAV_GROUPS）

URL 不变，只改分组 label 和顺序：

```tsx
const NAV_GROUPS = [
  {
    label: '入口',
    items: [
      { key: '/', label: '主看板', labelEn: 'Cockpit', icon: <DashboardOutlined /> },
    ],
  },
  {
    label: '数据',
    items: [
      { key: '/universe', label: '股票池', labelEn: 'Stock Pool', icon: <AppstoreOutlined /> },
      { key: '/data-management', label: '数据管理', labelEn: 'Data', icon: <DatabaseOutlined /> },
    ],
  },
  {
    label: '策略',
    items: [
      { key: '/strategies', label: '策略库', labelEn: 'Strategies', icon: <ThunderboltOutlined /> },
      { key: '/plans', label: '预案', labelEn: 'Plans', icon: <ScheduleOutlined /> },
    ],
  },
  {
    label: '执行',
    items: [
      { key: '/candidates', label: '候选池', labelEn: 'Candidates', icon: <UserOutlined /> },
      { key: '/trades', label: '成交流水', labelEn: 'Trades', icon: <TransactionOutlined /> },
    ],
  },
  {
    label: '反思',
    items: [
      { key: '/review', label: '复盘', labelEn: 'Review', icon: <LineChartOutlined /> },
      { key: '/backtest', label: '回测', labelEn: 'Backtest', icon: <BarChartOutlined /> },
    ],
  },
  {
    label: '自动化',
    items: [
      { key: '/scheduler', label: '定时任务', labelEn: 'Scheduler', icon: <ClockCircleOutlined /> },
      { key: '/monitoring', label: '监控配置', labelEn: 'Monitoring', icon: <BellOutlined /> },
    ],
  },
];
```

### 3. 共享原语 API（新建 `src/components/primitives/`）

#### 3.1 `<PageHeader>`（取代现有同名组件）

```tsx
// src/components/primitives/PageHeader.tsx
export interface PageHeaderFlowStep {
  label: string;           // 「策略库」
  to?: string;             // 可点击跳转；当前步不带 to
  current?: boolean;       // 高亮当前步
}

export interface PageHeaderProps {
  title: string;                       // 「预案」
  enLabel?: string;                    // 「Plans」（次级灰字）
  purpose: string;                     // 一句话定位，必须用通俗语言
  flow?: PageHeaderFlowStep[];         // 可选：典型流程指示
  actions?: ReactNode;                 // 可选：右上角主操作按钮
  sysAlertSlot?: ReactNode;            // 可选：SystemAlertBanner 已在 Layout，这里不重复
}
```

**purpose 写作规范**：
- 不写功能名（"Plan 管理面板"），写业务定义（"预案 = 把一个策略绑到一组股票上，运行后自动产出候选股"）
- 限一句话，< 50 字
- 必须解释「这是干嘛的」+「跟上下游的关系」至少其一

**flow 写作规范**：
- 3-5 步，当前步 `current: true` 不带 `to`
- 命名用业务术语，不用页面术语（"运行预案扫描"而非"点击 Run 按钮"）

#### 3.2 `<PageSection>`

```tsx
// src/components/primitives/PageSection.tsx
export interface PageSectionProps {
  title?: string;              // 可选区块标题（不传 = 无标题区块）
  subtitle?: string;           // 可选副标题（次级灰字）
  extra?: ReactNode;           // 可选：右侧操作区（"刷新"/"展开全部"）
  variant?: 'card' | 'plain';  // card = 包卡片（默认）；plain = 仅标题+内容
  children: ReactNode;
}
```

替代裸 `<Card><Title>...</Title>...</Card>` 堆叠。统一内部 padding 用 `--sp-6`。

#### 3.3 `<EmptyState>`（3 variant）

```tsx
// src/components/primitives/EmptyState.tsx
export type EmptyStateVariant = 'cold' | 'filter' | 'quiet';

export interface EmptyStateProps {
  variant: EmptyStateVariant;
  title: string;                          // 「还没有策略」/「无匹配候选」/「今日无新信号」
  description?: string;                   // cold 必填，含概念解释；filter 选填；quiet 不需要
  cta?: { label: string; onClick: () => void; primary?: boolean };
  icon?: ReactNode;                       // 不传则按 variant 选默认图标
  // filter variant 专用：
  onClearFilter?: () => void;             // 「清除筛选」快捷
}
```

**variant 判定表**（PR review 时按此表核对）：

| 场景 | variant | 视觉密度 | 是否带 CTA |
|---|---|---|---|
| 从未配置过任何数据（冷启动） | `cold` | 大图标 + 标题 + 概念解释 + 主 CTA | 必带 |
| 有数据但当前筛选无匹配 | `filter` | 中图标 + 标题 + 「清除筛选」 | 带 onClearFilter |
| 数据存在但本期无事件（如今日无 drafts） | `quiet` | 极小图标 + 一行说明，无按钮 | 不带 |

#### 3.4 `<StatCard>`

```tsx
// src/components/primitives/StatCard.tsx
export interface StatCardProps {
  label: string;                  // 「年度被动现金流」
  value: ReactNode;               // 数字（自动 .num-lg mono 类）
  delta?: {                       // 可选：同比/环比
    value: string;                // 「+12.4%」
    direction: 'up' | 'down' | 'flat';
    good?: 'up' | 'down';         // 方向的好坏事性（涨跌看场景）
  };
  hint?: string;                  // 可选：次级说明（「目标 ¥120k」）
  loading?: boolean;
  onClick?: () => void;           // 可选：整卡可点击跳详情
}
```

`delta.direction` 自动染色：方向匹配 `good` 用 `--color-success`，反向用 `--color-danger`，`flat` 用 `--text-tertiary`。

#### 3.5 `<FilterBar>`

```tsx
// src/components/primitives/FilterBar.tsx
export interface FilterBarProps {
  children: ReactNode;            // 筛选控件（Select / DatePicker 等）
  onReset?: () => void;           // 「重置」按钮；不传则不显示
  actions?: ReactNode;            // 最右侧自定义操作（如「导出」）
}
```

布局：左侧 flex wrap 筛选控件，右侧 sticky「重置」+ actions。统一间距 `--sp-3`。

### 4. TanStack Query 集成（沿用已有计划）

数据状态轨道完全沿用 `2026-06-13-page-interface-tanstack-query.md`：
- `queryClient` / `useToastMutation` / `<QueryBoundary>` 已存在
- feature-folder 布局已定（`features/<domain>/{queries,hooks,mutations,components,XxxPage.tsx}`）
- 每个 `XxxPage.tsx` 是"哑页面"，用 `<QueryBoundary>` 包裹数据态区域

**新增的集成点**：`<QueryBoundary>` 的 `emptyRender` 默认改用 `<EmptyState variant="...">`，把空状态视觉统一到原语层。具体 variant 由页面 prop 注入：

```tsx
<QueryBoundary
  query={plansQ}
  isEmpty={(data) => data.length === 0}
  emptyRender={<EmptyState variant="cold" title="还没有预案"
    description="预案 = 把一个策略绑到一组股票上，运行后自动产出候选股"
    cta={{ label: '创建第一个预案', onClick: () => setCreateOpen(true) }} />}
>
  {(data, isFetching) => <PlanTable data={data} refreshing={isFetching} />}
</QueryBoundary>
```

## 迁移计划（每个 Phase = 一个独立提交）

### Phase 0a — Foundation：视觉原语 + token（无功能变化）

**文件**:
- 修改: `frontend/src/styles/theme.css`（追加 typography/spacing/numeric token + utility 类 + `.gojira-card`）
- 修改: `frontend/src/components/Layout.tsx`（重排 NAV_GROUPS，仅数据变更，无 JSX 结构改动）
- 新建: `frontend/src/components/primitives/PageHeader.tsx`
- 新建: `frontend/src/components/primitives/PageSection.tsx`
- 新建: `frontend/src/components/primitives/EmptyState.tsx`
- 新建: `frontend/src/components/primitives/StatCard.tsx`
- 新建: `frontend/src/components/primitives/FilterBar.tsx`
- 新建: `frontend/src/components/primitives/index.ts`（统一导出）

**验收**:
- [ ] `npm run build` 通过
- [ ] `npm run lint` 通过
- [ ] 导航分组重排后，所有 12 个页面 URL 仍可达
- [ ] 原 `src/components/PageHeader.tsx` 暂保留（旧页面仍在用），新 PageHeader 单独命名空间在 `primitives/` 下
- [ ] 原语在 Storybook 不可用（项目无 Storybook）→ 写一个临时 `frontend/src/components/primitives/__preview__.tsx` 路由 `/__primitives__` 仅供 dev 模式人工验收，**不入 prod bundle**（用 `import.meta.env.DEV` gate）

**提交信息**: `refactor(frontend): add visual primitives + typography scale (Phase 0a)`

### Phase 0b — IA 重排：Layout（独立小提交）

**说明**: 0a 已经把 NAV_GROUPS 改了，所以 0b 其实是 0a 的一部分。这里单列是为了在 review 时让导航变更可被独立讨论/回滚。

**实际操作**: 把 Layout 改动从 Phase 0a 拆出来单独提交，提交信息: `refactor(frontend): regroup nav by business flow (Phase 0b)`

### Phase 1 — PlansPage 视觉 retrofit

**当前状态**: `features/plans/` 已 TanStack 迁移完成（Phase 1 of TanStack plan）。本 Phase 只补视觉层。

**文件**:
- 修改: `frontend/src/features/plans/PlansPage.tsx`（用新 `<PageHeader>` + `<PageSection>`）
- 修改: `frontend/src/features/plans/components/*`（如有 StatCard 模式则替换）
- 评估: 是否替换 `<Empty>` 为 `<EmptyState variant="cold">`

**关键决策点**:
- PlansPage 的 PageHeader.purpose 应为："预案 = 把一个策略绑到一组股票上，运行后自动产出候选股"
- PlansPage 的 flow 应为: 策略库 → **预案(当前)** → 候选池 → 成交流水
- 空状态 variant: 当无任何预案时为 `cold`；当筛选无匹配时为 `filter`

**验收**:
- [ ] 列表/新建/运行/启停/删除全链路（回归 Phase 1 of TanStack）
- [ ] 空状态正确 variant 切换
- [ ] PageHeader flow 中"预案"高亮
- [ ] `npm run build` 通过

**提交信息**: `refactor(frontend): retrofit PlansPage with new primitives (Phase 1)`

### Phase 2-12 — 按简单 → 复杂顺序逐页迁移

每页 = 一个 PR = 三件事同时完成（TanStack 数据层 + feature-folder 化 + 视觉原语应用）。提交信息统一：`refactor(frontend): migrate <Page> to TanStack Query + primitives (Phase N)`

| Phase | 页面 | LOC | TanStack 难点 | 视觉重点 |
|---|---|---|---|---|
| 2 | DataManagementPage | 137 | 删 `refreshKey` 计数器；tab 各自 query + 跨 tab invalidate(['data-management']) | 3 tab 区分；空数据时每个 tab 给 cold EmptyState |
| 3 | StrategiesPage | 219 | 字典类，`staleTime: 5min` | 卡片网格（去边框）；purpose 写"策略 = 一组买卖规则的集合" |
| 4 | TradesPage | 254 | 简单列表 | 表格 + StatCard 顶部汇总（成交笔数 / 净流入） |
| 5 | CandidatesPage | 340 | 客户端筛选（query 无 filter 参数，过滤在 useMemo） | `<FilterBar>` 首发；筛选无匹配时 filter EmptyState |
| 6 | SchedulerPage | 377 | Job 列表 + 启停 mutation | 任务列表 + 下次执行时间 mono 呈现 |
| 7 | ReviewPage | 456 | 复盘项 CRUD | ECharts 图表卡片化 |
| 8 | BacktestPage | 564 | 回测任务 + 结果 | StatCard + 图表 |
| 9 | StockDetailPage | 630 | `enabled: !!code`（路由参数 gate） | 详情页 PageHeader 用股票名做 title |
| 10 | UniversePage | 727 | 大表格 + 多筛选 | `<FilterBar>` 重度使用；行内 actions 整理 |
| 11 | MonitoringPage | 799 | 告警规则 CRUD + 测试 | 规则表 + 触发历史 |
| 12a | CockpitPage（数据层） | 1251 | 多源聚合；每张卡自持 query | 暂不动视觉，仅替换数据层 |
| 12b | CockpitPage（拆文件 + 视觉） | ~150（迁移后） | 10 张卡抽到 `features/cockpit/components/` | StatCard 大量使用；PageHeader flow 高亮当前在「入口」 |

**Cockpit 拆分两步的理由**：单 PR 把"换数据层 + 拆 10 个组件 + 重做视觉"揉一起，diff 会超过 1500 行不可 review。12a 跟 12b 各自独立提交，跟 TanStack 计划 Phase 2/3 的拆分逻辑一致。

### Phase 13 — 收尾

- 删旧 `src/components/PageHeader.tsx`（确认所有引用已切到新 primitives）
- 删 dev-only `/__primitives__` 预览路由
- 全量 `npm run build` + `npm run lint`
- 逐页人工冒烟：每页 4 态（loading/error/empty/data）

## 验证 (Verification)

### 每个 Phase 后必跑

- [ ] `npm run build` 通过（TypeScript 类型检查 + Vite 构建）
- [ ] `npm run lint` 通过
- [ ] dev 服务器 `./dev.sh` 启动，目标页面手测四态：
  - loading（首次进入时的骨架屏 / spinner）
  - error（断网或后端关时的错误提示 + 重试按钮）
  - empty（按 variant 判定表确认 cold/filter/quiet 用对）
  - data（功能与迁移前一致）
- [ ] mutation 后 query 正确失效（devtools 抽查）

### Phase 0a 后额外

- [ ] `/__primitives__` 预览路由在 dev 下可见，展示 5 个原语 + token 示例
- [ ] prod 构建不含 `/__primitives__`（`import.meta.env.DEV` gate 生效）

### Phase 0b 后额外

- [ ] 导航 6 组分组正确显示
- [ ] 所有 12 个页面 URL 仍可达（点击每个导航项都能进）
- [ ] 当前页 active 状态正确（高亮当前位置）

### Phase 12b 后（Cockpit 最终态）

- [ ] CockpitPage.tsx < 200 行
- [ ] 10 张卡片全部在 `features/cockpit/components/` 下
- [ ] StatCard 替代所有手写卡片样式
- [ ] 数字一律 mono

## 回滚策略

- **每个 Phase = 一个独立提交**，可单独 `git revert`
- Phase 0a 的原语**新建不删旧**（旧 PageHeader 保留到 Phase 13），降低回滚难度
- Phase 0b 的 Layout 改动是单文件单数组改动，回滚 = 单文件 revert
- Phase 12a/12b 拆分正是为了 Cockpit 回滚粒度

## 已决断（4 个判断点，2026-06-13 锁定）

1. **抽 5 个原语，不抽更多**。ConceptHint / DataTable / MetricRow 否决（避免过度工程）。
2. **原语放在 `src/components/primitives/`** 而非 `src/components/`。语义清晰，未来扩展易追踪。
3. **空状态 3 variant 而非 1 个统一原语**。cold/filter/quiet 语义边界清晰，PR review 时按判定表核对。
4. **Cockpit 拆 Phase 12a/12b**。降低单 PR diff size，跟 TanStack 计划已锁定的 Phase 2/3 拆分对齐。

## 下一步 (Next Steps)

1. 启动 Phase 0a（基础设施 + 原语，无功能变更）
2. Phase 0a 完成后让用户在 `/__primitives__` 预览路由人工验收 5 个原语
3. Phase 0b 单独提交（IA 重排）
4. Phase 1（PlansPage retrofit）作为第一个端到端示范，让用户验收视觉方向
5. Phase 2-12 按顺序推进，每个 Phase 完成后用户 review

## 参考 (References)

- `/grill-me` 共识（本会话）
- `docs/progress/2026-06-13-page-interface-tanstack-query.md`（数据状态轨道）
- `docs/standards/serialization.md`（序列化标准）
- `frontend/src/styles/theme.css`（当前主题）
- `frontend/src/components/Layout.tsx`（当前导航）
- 现状基线：12 个页面共 5755 行，211 个 inline style 块，9 种字号无规则
