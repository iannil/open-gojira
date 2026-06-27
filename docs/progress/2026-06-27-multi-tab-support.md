# 多 Tab 打开支持 — 实现记录

**日期**: 2026-06-27  
**目标**: 为 Gojira 前端增加多 tab 同时打开支持，用户可同时打开多个页面，方便切换。

## 架构设计

### 核心思路

- **Keep-alive tab 策略**：每个已打开的 tab 页面保持挂载（mounted），不活跃的 tab 通过 `display: none` 隐藏，切换时无需重新渲染
- **基于 React Router v7 的 `Routes` 多实例渲染**：活跃 tab 通过正常的 `<Outlet />` 渲染；不活跃 tab 通过独立的 `<Routes location={tabPath}>` 渲染，保留了 `useParams()` 的正确行为（如 StockDetailPage 的 `:code` 参数）
- **集中式路由配置**：所有路由定义从 `App.tsx` 提取到 `routeConfig.ts`，作为唯一真相源，同时被主 Routes 和 tab Routes 使用

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/features/tabs/routeConfig.ts` | 19 条路由定义 + `findRouteDef` / `resolveTabTitle` 查找函数 |
| `src/features/tabs/TabContext.tsx` | `TabProvider` + `useTabs` hook，管理 tabs 列表 / activeKey |
| `src/features/tabs/TabBar.tsx` | Tab 栏 UI：滚动容器、关闭按钮、中键关闭、键盘可用 |
| `src/features/tabs/TabContent.tsx` | Keep-alive 内容渲染器：活跃 tab 用 `<Outlet />`，不活跃用自独立 `<Routes>` |
| `src/features/tabs/index.ts` | 模块级重新导出 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/components/Layout.tsx` | 拆分为 `Layout`（TabProvider 外壳）+ `LayoutInner`（实际 UI）；导航点击时调用 `openTab()`；替换 `<Outlet />` 为 `<TabContent />`；在 header 和主内容之间插入 `<TabBar />` |
| `src/styles/theme.css` | 新增 `~120` 行 tab bar / tab content 样式，与"墨韵金阁"风格一致 |

### 未修改

- `App.tsx` — 现有 Routes 结构保持不变，`<TabContent />` 内部兼容 `<Outlet />`

## 关键交互

1. **导航点击** → 调用 `openTab(path, resolveTabTitle(path))` → 若已有同路径 tab 则激活，否则新建 → 最后 `navigate(path)`
2. **Tab 切换** → 激活目标 tab → 若路径与当前 URL 不同则 `navigate(tab.pathname)`
3. **关闭 Tab** → 关闭后自动切换到邻近 tab 并导航到其路径；首页 tab（`/`）不可关闭
4. **首页 tab** — 始终固定在 tab 列表第一个、不可关闭

## 设计决策

- **不做完整 keep-alive 状态恢复（initial state）**：采用最简 keep-alive 方案——仅保持组件挂载，不保存滚动位置。需要时可在后续迭代中增强
- **不使用第三方库**：纯 React Context + React Router API 实现，无额外依赖
- **股票详情 tab 标题**：动态路由 `/stock/:code` 的 tab 标题显示为 `股票 600519`

## 验证

- `npx tsc --noEmit` ✓ 无错误
- `npm run build` ✓ 构建通过
