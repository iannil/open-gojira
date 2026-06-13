# 前端页面接口重构 — 采用 TanStack Query

> **日期**: 2026-06-13
> **状态**: 进行中（方向已定，Phase 0 未开始）
> **关联**: `docs/active/roadmap.md`、`docs/progress/STATUS.md`、`memory/daily/2026-06-13.md`

## 目标 (Goal)

把前端 12 个页面从"各自手搓 `useState` + `useEffect` + `load()`"统一到**一套服务端状态约定**，消除当前 loading/error/empty/mutation-refetch 的 12 种不一致写法，并顺带拆掉 `CockpitPage.tsx`（1251 行）这个把数据编排、业务 handler、10 个展示型组件揉在一起的 monolith。

**Why**: 当前 `PlansPage` 没有 error 态（只 `message.error`），`CandidatesPage` 把 `loading` 挂在 Table 上并吞掉错误，`DataManagementPage` 用 `refreshKey` 计数器 + `.catch(()=>{})`。金融控制台对"请求是否竞态、数据是否陈旧、刷新是否生效"敏感，需要一个库级的正确性基线，而不是再写一个自制 hook。

## 范围 (Scope)

- **影响模块**: 前端全部 12 个页面 + `src/App.tsx`（挂 Provider）；新增 `src/lib/`、`src/components/QueryBoundary.tsx`、`src/features/<domain>/` 特性文件夹。
- **不在范围内**: 后端任何改动；API 客户端函数签名（`src/api/client.ts` 的 ~50 个 async 函数保持不变，直接作为 `queryFn`）；axios/zustand/antd 版本。

## 设计决策 (Why TanStack Query)

经 `/design-an-interface` 流程产出 4 个候选并对比：

| 方案 | 形态 | 结论 |
|---|---|---|
| A. 最小 hook (`useResource`+`PageShell`) | 2 个导出，无依赖 | 备选主轴，无缓存/去重/竞态护栏 |
| B. 配置驱动框架 (`<ResourcePage spec>`) | 页面 = 配置对象 | 否决：为 12 页造 react-admin，dashboard 原型打架 |
| **C. TanStack Query + 特性文件夹** | 库 + 约定层 | **选定**：库级正确性 + devtools + 跨页 invalidation |
| D. Render-prop 组件 (`<Query>`/`<Mutation>`) | JSX 数据流 | 否决：wrapper hell，CRUD 页嵌套过深 |

**关键分歧是缓存**：C 把服务端状态缓存当核心抽象（SWR + 去重 + 竞态安全），A/D 明确不做缓存。金融场景下竞态正确性 + 刷新可观测性（devtools）的收益被认为超过引入依赖与每特性样板代码的成本。

从 A 借的：feature-folder 文件拆分（配合 hook 化安全拆解 CockpitPage）。从 D 借的：`initialLoading` vs `isFetching` 的显式区分（TanStack Query 原生提供 `isLoading`/`isFetching`/`isPending`）。

## 接口规格

### 1. 依赖与全局配置

安装（`frontend/`）：

```bash
npm install @tanstack/react-query
```

**`src/lib/queryClient.ts`**（新建）：

```ts
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,              // 10s 内不重拉；按 query 可覆盖（金融数据偏短）
      gcTime: 5 * 60_000,
      retry: 1,                       // Lixinger 偶发抖动
      retryDelay: (i) => Math.min(1000 * 2 ** i, 4000),
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
    },
    mutations: { retry: 0 },          // 用户显式动作，失败必须立刻可见
  },
});
```

**`src/App.tsx`** 在 `<AntApp>` 内、`<BrowserRouter>` 外加 Provider：

```tsx
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { queryClient } from './lib/queryClient';
// ...
<AntApp>
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>...</BrowserRouter>
    {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
  </QueryClientProvider>
</AntApp>
```

### 2. 文件夹布局（feature-folder）

```
src/features/<domain>/
  queries.ts              # xxxKeys 工厂（纯数据，无副作用）
  useXxxQueries.ts        # useXxxQuery 等
  useXxxMutations.ts      # useCreateXxxMutation 等
  components/              # 展示型子组件
  XxxPage.tsx             # 哑页面
  index.ts
```

`src/pages/*.tsx` 变成 3 行 re-export（保持 `App.tsx` 的 lazy import 不变）：

```tsx
// src/pages/PlansPage.tsx
export { PlansPage as default } from '../features/plans/PlansPage';
```

共享基础设施：`src/lib/queryClient.ts`、`src/lib/useToastMutation.ts`、`src/components/QueryBoundary.tsx`。

### 3. 接口签名

#### 3.1 Query key 工厂规约（`queries.ts`）

层级 tuple，顶层 namespace = 特性名；筛选条件与 id 永远是叶子，不烤进 namespace。

```ts
export const planKeys = {
  all:        () => ['plans']                                         as const,
  list:       (filter: PlanFilter) => [...planKeys.all(), 'list', filter] as const,
  detail:     (id: number) => [...planKeys.all(), 'detail', id]           as const,
  strategies: () => ['strategies']                                     as const,
} as const;
```

铁律：`invalidateQueries({ queryKey: planKeys.all() })` 必须清掉整个子树。

#### 3.2 `useToastMutation`（`src/lib/useToastMutation.ts`）

把"mutation + toast + invalidate"焊成项目约定。页面永远不直接调 `useMutation`。

```ts
import { useMutation, useQueryClient,
         type UseMutationOptions, type QueryKey } from '@tanstack/react-query';
import { useAntdStatic } from '../hooks/useAntdStatic';

export interface ToastMutationOptions<TData, TVars, TContext = unknown>
    extends UseMutationOptions<TData, Error, TVars, TContext> {
  successMsg?: string | ((data: TData) => string);
  errorMsg?: string | false | ((err: Error) => string);
  invalidate?: QueryKey[] | ((data: TData) => QueryKey[]);
}

export function useToastMutation<TData, TVars, TContext = unknown>(
  mutationFn: (vars: TVars) => Promise<TData>,
  options: ToastMutationOptions<TData, TVars, TContext> = {},
) {
  const { message } = useAntdStatic();
  const queryClient = useQueryClient();
  return useMutation<TData, Error, TVars, TContext>({
    mutationFn, retry: 0, ...options,
    onSuccess: async (data, vars, ctx) => {
      if (options.successMsg) {
        message.success(typeof options.successMsg === 'function'
          ? options.successMsg(data) : options.successMsg);
      }
      const keys = typeof options.invalidate === 'function'
        ? options.invalidate(data) : (options.invalidate ?? []);
      await Promise.all(keys.map((k) => queryClient.invalidateQueries({ queryKey: k })));
      return options.onSuccess?.(data, vars, ctx);
    },
    onError: (err, vars, ctx) => {
      if (options.errorMsg !== false) {
        const msg = typeof options.errorMsg === 'function'
          ? options.errorMsg(err) : (options.errorMsg ?? `操作失败：${err.message}`);
        message.error(msg);
      }
      return options.onError?.(err, vars, ctx);
    },
  });
}
```

#### 3.3 `<QueryBoundary>`（`src/components/QueryBoundary.tsx`）

数据态门控，吸收 loading/error/empty 三态。**页面从此不再写 `if (!data) return ...`。** 与应用级 `ErrorBoundary`（崩溃兜底）职责不同，互不替代。

```tsx
import type { ReactNode } from 'react';
import { Alert, Button, Empty, Spin } from 'antd';

export interface QueryLike<T> {
  isLoading: boolean;
  isFetching?: boolean;
  isError: boolean;
  error: unknown;
  data: T | undefined;
  refetch?: () => unknown;
}

export interface QueryBoundaryProps<T> {
  query: QueryLike<T>;
  isEmpty?: (data: T) => boolean;
  emptyRender?: ReactNode;
  errorRender?: (err: Error, retry: () => void) => ReactNode;
  skeleton?: ReactNode;
  children: (data: T, isFetching: boolean) => ReactNode;
}

export function QueryBoundary<T>(props: QueryBoundaryProps<T>) {
  const { query } = props;
  if (query.isLoading) return <>{props.skeleton ?? <Spin />}</>;
  if (query.isError) {
    const err = query.error as Error;
    const retry = () => void query.refetch?.();
    return <>{props.errorRender
      ? props.errorRender(err, retry)
      : <Alert type="error" showIcon message={err.message}
          action={<Button size="small" onClick={retry}>重试</Button>} />}</>;
  }
  const data = query.data as T;
  if (props.isEmpty && props.isEmpty(data)) {
    return <>{props.emptyRender ?? <Empty />}</>;
  }
  return <>{props.children(data, !!query.isFetching)}</>;
}
```

### 4. 页面契约（"哑页面"规则）

每个 `XxxPage.tsx` **必须**：只读 query hook 结果 + 渲染；mutation 走 `useXxxMutation()`；用 `<QueryBoundary>` 包裹数据态区域，children 是 render-prop `(data, isFetching) => ...`。

**禁止**：页面体内写 `useEffect` 拉数据、`useState` 存服务端数据、`try/catch` 包 mutation happy path、直接调 `message.success/error`、手写 loading/error/empty 三态分支。

**允许**（非服务端状态）：`useState` 存 UI 状态（筛选条件、Modal 开关、选中行、折叠态）；跨页复杂 UI 状态可用 zustand（已装）。边界让规则可执行——review 时只盯"是不是在管 fetch 的 data/loading/error"。

### 5. 各原型落地模式

**(a) 仪表盘聚合 (CockpitPage)** — 多源并列，每个 query 独立 `<QueryBoundary>`；重卡片自持 query。

```tsx
export default function CockpitPage() {
  const summaryQ = useCockpitQuery();
  return (
    <div>
      <PageHeader title="自动驾驶舱" enLabel="Cockpit" />
      <QueryBoundary query={summaryQ}>
        {(data, isFetching) => (
          <div className="cockpit-grid">
            <GoalNavigator data={data.cashflow} refreshing={isFetching} />
            <DraftsTable />          {/* 自持 useDraftsQuery + useExecuteDraftMutation */}
            <ThemeExposureCard />    {/* 自持 useThemeExposureQuery */}
            <AlertsList alerts={data.alerts} />
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}
```

```ts
export const useExecuteDraftMutation = () =>
  useToastMutation((id: number) => executeDraft(id), {
    successMsg: '已登记成交 + 记录 trade',
    invalidate: () => [cockpitKeys.summary(), cockpitKeys.drafts(), ['trades']],
  });
```

**(b) 可筛选列表 (CandidatesPage)** — 客户端筛选：query 无筛选参数，过滤在 `useMemo` 里做，缓存复用；服务端筛选：筛选对象进 query key，`placeholderData: keepPreviousData` 防闪烁。

**(c) CRUD (PlansPage)** — 注意 `runPlan` 会产生候选 + 草稿，`invalidate` 要失效三个子树：

```ts
export const useRunPlanMutation = () =>
  useToastMutation((id: number) => runPlan(id) as Promise<RunResult>, {
    successMsg: (r) => `扫描完成：${r.passed ?? 0} 通过，${r.drafts_emitted ?? 0} 草稿`,
    invalidate: () => [planKeys.all(), ['candidates'], ['cockpit']],
  });
```

**(d) 详情页 (StockDetailPage)** — 唯一带路由参数的页：

```ts
export function useStockQuery(code: string | undefined) {
  return useQuery({
    queryKey: stockKeys.detail(code),
    queryFn: () => getStock(code!),
    enabled: !!code,           // code 未就绪时挂起，不发请求
  });
}
```

**(e) 标签页控制台 (DataManagementPage)** — 每个 tab 自己的 query + 稳定 key；跨 tab 刷新 = 任一 tab 的 mutation `invalidate(['data-management'])`。**删除** `refreshKey` 计数器 + `setTimeout(triggerRefresh, 3000)`——query key namespace 本身就是刷新信号。共享的 `fetchUniverseStats` 在每个 tab mount 时 dedupe 成一次请求。

## 迁移计划（每步一个提交，每步验收）

| Phase | 内容 | 验收 |
|---|---|---|
| **0** | 装包；建 `lib/queryClient.ts` + `lib/useToastMutation.ts` + `components/QueryBoundary.tsx`；`App.tsx` 挂 Provider + devtools | `npm run build` 通过；应用行为零变化；devtools 可见 |
| **1** | 试点 **PlansPage**：建 `features/plans/`（queries + hooks + mutations + 拆 `PlanTable`/`PlanForm`） | 列表/新建/运行/启停/删除全链路；mutation 正确失效 + toast；手写 `message.error('加载失败')` 消失 |
| **2** | **CockpitPage 数据层迁移**（先不拆文件）：建 `features/cockpit/{queries,queries hooks,mutations}`，整页换 query + boundary，10 张卡仍内联 | 仪表盘加载、executeDraft/cancelDraft、cashflow goal 编辑全链路；行为与 Phase 1 前一致 |
| **3** | **CockpitPage 拆文件**（独立提交）：10 张卡抽到 `features/cockpit/components/`，DraftsTable/ThemeExposureCard 改自持 query | `CockpitPage.tsx` 从 1251 行降到 ~150 行；每张卡可独立查看 |
| **4** | **长尾页面**（按风险升序）：Strategies、Scheduler、Trades、Review → Candidates（客户端筛选）→ StockDetail（`enabled`）→ DataManagement（删 `refreshKey`）→ Universe、Backtest、Monitoring | 每页 mutation 后正确失效；`pages/*.tsx` 全部变 re-export |
| **5** | 收尾：删旧 `load()`；全量 `npm run build` + `npm run lint`；逐页人工冒烟 | 全绿 |

每步提交信息：`refactor(frontend): migrate <Page> to TanStack Query`。

## 已决断（2 个判断点，2026-06-13 锁定）

1. **默认 `staleTime` = 10s**。金融数据偏短；mutation 都强制失效，10s 主要防"反复 mount 重拉"。按 query 仍可覆盖：盘面类（cockpit）保持默认或更短，字典类（strategies）调到 5min（`staleTime: 5 * 60_000`）。
2. **Phase 2 / Phase 3 保持拆分**（换数据层 + 拆 Cockpit 文件，分两步降风险，各自独立提交）。

## 验证 (Verification)

- [ ] 类型检查：`npm run build`（每 Phase 后）
- [ ] Lint：`npm run lint`（每 Phase 后）
- [ ] 端到端冒烟：每个迁移完的页面，验证加载/错误/空/mutation 刷新四态
- [ ] devtools 抽查：确认 query key 层级、invalidation 命中预期子树、无重复请求（dedupe 生效）
- [ ] 回归：后端 402 测试不受影响（纯前端改动）

## 下一步 (Next Steps)

1. 启动 Phase 0（基础设施，无功能变更）。
2. Phase 1 试点 PlansPage 后，回顾约定层是否需要调整，再铺开。

## 参考 (References)

- `/design-an-interface` 流程产出的 4 候选方案（A 最小 hook / B 配置框架 / C TanStack Query / D render-prop），本文件即 C 的落定版
- TanStack Query v5 文档：https://tanstack.com/query/latest
- 现状基线：`src/pages/*.tsx`（12 个页面）、`src/api/client.ts`（~50 个 async 函数）、`src/App.tsx`（react-router v7 + lazy）
