# Gojira Frontend

Gojira 投资分析系统的前端，基于 React 19 + TypeScript + Vite。

## 技术栈

- **UI 框架**：Ant Design 6
- **图表**：ECharts（通过 echarts-for-react）
- **HTTP 客户端**：Axios
- **路由**：React Router v7
- **主题**："墨韵金阁"（Ink & Gold Pavilion），使用 CSS 自定义属性 + Ant Design ConfigProvider

## 页面路由

| 路径 | 页面 | 功能 |
|------|------|------|
| `/` | DashboardPage | 总览仪表板 |
| `/analysis` | AnalysisPage | 三步分析向导 + 求评分器 + 行业模板 |
| `/valuation` | ValuationPage | 估值工具（百分位、EPS、综合、银行股、投机） |
| `/portfolio` | PortfolioPage | 持仓管理 + 分红记录 |
| `/discipline` | DisciplinePage | 投资日记 + 纪律检查 |
| `/compare` | ComparePage | 多股对比 |

## 关键文件

- `src/api/client.ts` — 所有 API 调用函数集中定义
- `src/api/types.ts` — TypeScript 类型（与后端 schemas 对应）
- `src/styles/theme.css` — 全局主题变量

## 开发命令

```bash
npm install        # 安装依赖
npm run dev        # 开发服务器（端口 3000，代理 /api 到 3001）
npm run build      # 构建
npm run lint       # ESLint 检查
```
