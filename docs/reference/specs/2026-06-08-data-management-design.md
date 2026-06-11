# 基础数据管理功能设计

## 概述

将现有 DataSyncPage 拆分为两个独立页面：「基础数据管理」和「定时任务」。数据管理页面提供股票池管理、各类型数据的同步触发、状态查看和数据清理功能，采用按数据类型组织的卡片式布局。

## 页面结构

### 导航变更

- 移除现有"数据同步"导航项
- 新增"数据管理"导航项（路由 `/data-management`）
- 新增"定时任务"导航项（路由 `/scheduler`）

### 基础数据管理页面 (`/data-management`)

采用卡片网格布局，顶部为股票池管理区，下方为各数据类型管理卡片。

#### 股票池管理区（顶部）

- 股票池列表表格：展示当前关注股票（代码、名称、行业、关注时间、数据完整度）
- 添加股票：搜索框按代码/名称搜索 Lixinger 数据，一键添加到股票池
- 移除股票：支持单条和批量移除
- 数据完整度：每只股票用图标显示各类数据同步状态（估值/财报/K线/分红）

#### 数据管理卡片（下方网格，4 个卡片）

**估值快照卡片**
- 状态：最近同步时间、覆盖股票数、PE/PB 百分位覆盖率
- 操作：手动同步（全量/增量）、按时间范围清理历史数据
- 详情：展开查看各股票最新估值

**财报数据卡片**
- 状态：最近同步时间、年度/季度报告数、行业覆盖情况
- 操作：手动同步（指定股票/全量）、按年度清理
- 详情：查看各股票财报覆盖年份

**K线数据卡片**
- 状态：最近同步时间、日/周/月K线数据量、时间覆盖范围
- 操作：手动同步（指定股票+频率）、按时间范围清理
- 详情：查看各股票K线起止日期

**分红数据卡片**
- 状态：最近同步时间、分红记录数、最近分红日期
- 操作：手动同步、清理历史数据
- 详情：查看各股票分红汇总

#### 交互模式

- 手动同步：确认对话框 → 显示同步范围和预估耗时 → 执行时轮询进度 → 完成刷新
- 数据清理：时间范围选择器 → 显示删除记录数预估 → 确认执行 → 刷新状态

### 定时任务页面 (`/scheduler`)

从现有 DataSyncPage 迁移任务管理和执行日志两个标签页，功能和交互保持不变。

## 后端 API

### 新增 Router：`backend/app/routers/data_management.py`

#### 股票池管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/data-management/universe` | 获取股票池列表（含数据完整度） |
| POST | `/api/data-management/universe/search` | 搜索股票（代码/名称） |
| POST | `/api/data-management/universe/add` | 添加股票到股票池 |
| DELETE | `/api/data-management/universe/{stock_id}` | 从股票池移除 |
| POST | `/api/data-management/universe/batch-remove` | 批量移除 |

#### 数据同步

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/data-management/status` | 全量数据状态概览 |
| POST | `/api/data-management/sync/{data_type}` | 触发同步（valuations/financials/klines/dividends） |
| GET | `/api/data-management/sync/{task_id}/status` | 查询同步进度 |

#### 数据清理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/data-management/cleanup/{data_type}` | 按时间范围清理数据 |
| GET | `/api/data-management/cleanup/{data_type}/preview` | 预览清理记录数 |

### 服务层

新增 `backend/app/services/data_management_service.py`：
- 聚合现有服务的调用（financial_service、kline_service、dividend_service、valuation_service）
- 新增数据清理方法（按时间范围删除历史数据）
- 新增状态聚合查询（各类型记录数、最近同步时间）
- 股票池操作复用 watchlist 服务层逻辑

### 同步任务模式

同步操作采用异步任务模式：触发后立即返回 `task_id`，前端轮询进度。

## 数据模型

不新增数据库模型。复用现有模型：Stock、ValuationSnapshot、FinancialStatement、PriceKline、DividendRecord。

## 迁移策略

1. 新建 `DataManagementPage` 组件，实现数据管理功能
2. 新建 `SchedulerPage` 组件，迁移现有任务管理和执行日志
3. 更新路由和导航配置
4. 新增后端 router 和 service
5. 移除原有 `DataSyncPage`

## 文件变更清单

### 新增文件
- `backend/app/routers/data_management.py`
- `backend/app/services/data_management_service.py`
- `backend/app/schemas/data_management.py`
- `frontend/src/pages/DataManagementPage.tsx`
- `frontend/src/pages/SchedulerPage.tsx`

### 修改文件
- `backend/app/main.py` — 注册新 router
- `frontend/src/App.tsx` — 更新路由配置
- `frontend/src/components/Layout.tsx` — 更新导航栏
- `frontend/src/api/client.ts` — 新增 API 函数
- `frontend/src/api/types.ts` — 新增类型定义

### 删除文件
- `frontend/src/pages/DataSyncPage.tsx`
