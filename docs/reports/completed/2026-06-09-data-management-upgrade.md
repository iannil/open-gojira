# 数据管理模块精细化升级

> 日期：2026-06-09
> 分支：feature/gojira-investment-system

## 变更摘要

将数据管理页面从单体页面重构为 5 个 Tab 页的精细化管理系统，充分利用后端已有的 Pipeline 基础设施。

## 新增功能

### 后端
- **新增 `GET /api/data-management/quality` 端点**：综合数据质量评估
  - 完整性分析（股票覆盖率）
  - 新鲜度检测（按数据类型不同阈值）
  - 缺口检测（K线/估值缺失交易日）
  - 异常统计（死信队列 DATA_ANOMALY 计数）
  - 验证通过率（Pipeline 运行历史）
  - 自动生成改进建议

### 前端
- **Tab 1 数据健康概览**：综合健康评分、4 种数据类型新鲜度卡片、API 用量、死信队列摘要
- **Tab 2 数据同步**：Pipeline 控制面板、实时进度轮询、运行历史、失败重试、详情抽屉
- **Tab 3 股票池管理**：增强型表格（排序、完整度进度条、批量同步、批量复制代码）
- **Tab 4 数据质量**：质量评分、完整性/新鲜度/缺口/异常指标、改进建议列表
- **Tab 5 数据清理**：内联清理面板、存储用量概览

## 新增文件

### 后端（3 个）
- `backend/app/schemas/data_quality.py`
- `backend/app/services/data_quality_service.py`
- 修改 `backend/app/routers/data_management.py`

### 前端（14 个）
- `frontend/src/components/data-management/constants.ts`
- `frontend/src/components/data-management/hooks/useDataStatus.ts`
- `frontend/src/components/data-management/hooks/usePipelinePolling.ts`
- `frontend/src/components/data-management/hooks/useStockPool.ts`
- `frontend/src/components/data-management/DataHealthDashboard.tsx`
- `frontend/src/components/data-management/PipelineManagement.tsx`
- `frontend/src/components/data-management/PipelineRunDetail.tsx`
- `frontend/src/components/data-management/PipelineProgressTracker.tsx`
- `frontend/src/components/data-management/StockPoolManagement.tsx`
- `frontend/src/components/data-management/DataQualityPanel.tsx`
- `frontend/src/components/data-management/DataCleanupPanel.tsx`
- 重写 `frontend/src/pages/DataManagementPage.tsx`
- 修改 `frontend/src/api/types.ts`
- 修改 `frontend/src/api/client.ts`

## 验证

- 后端测试：304 passed（排除 1 个预存在的 kline-summary 失败）
- 前端构建：✓ 无错误
