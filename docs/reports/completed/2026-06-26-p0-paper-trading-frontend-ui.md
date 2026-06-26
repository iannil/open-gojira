# 2026-06-26 P0 纸面交易前端 UI 实施记录

> 从 grill-me 拷问 → 执行模式，完成 P0 四项中的全部改动

## 改动清单

### P0-④: T+1 可用股数 API endpoint
- **状态**: ✅ 已存在，无需新增
- `GET /api/portfolio/{code}/available` 已完整实现（position_service.available_quantity + portfolio router + AvailableQuantityResponse schema）
- 验证：返回 `{'code':'000001', 'available':0, 'frozen':0, 'total':0}` 正常

### P0-①: 重建 /drafts 页
- **文件**: `frontend/src/features/drafts/DraftsPage.tsx` (stub → 280+ 行完整组件)
- 功能：过滤 tabs（待处理 / 已执行 / 已取消，默认待处理）
- 每个 draft 以 Card 展示，含：code、方向标签、status、reason、source、triggered_at、expires_at（TTL 倒计时，<24h 标红）、strategy_tier、thesis_status、target_price、sizing_logic、suggested_quantity
- SELL draft：内嵌 T+1 可用股数（调用 `getAvailableQuantity`）
- 操作按钮：成交（→ ExecuteModal）+ 取消
- 顶部统计：待处理 / 买入 / 卖出 计数卡片
- QueryBoundary + EmptyState 覆盖 loading/error/empty 状态

### P0-②: 确认成交弹窗
- **位置**: `DraftsPage.tsx` 内的 `ExecuteModal` 组件
- 回填字段：实际成交价（¥）、实际数量、成交时间
- 调用 `POST /drafts/{id}/execute` → 记录 Trade + audit_log
- invalidate: drafts / trades / cockpit / holdings 四组 query key

### P0-③: Cockpit 信号区
- **后端**: `cockpit_service.py` — 新增 `signal_alerts` / `signal_alerts_count` 字段（从 unresolved alerts 中过滤 category="signal"）
- **前端类型**: `CockpitResponse` 接口新增 `signal_alerts: CockpitAlertV2[]` / `signal_alerts_count: number`
- **前端组件**: `CockpitPage.tsx` "待办信号"区域 — 当有 signal 类告警时，在 draft 表格下方以 Alert 组件展示；无 draft 但有 signal 时也不显示空状态

### 前置 Step 1-2: DraftResponse 字段补齐
- `backend/app/schemas/draft.py`: Phase 5 字段（research_report_id, target_price, strategy_tier, sizing_logic, thesis_status, expires_at, serenity_thesis, suggested_quantity）
- `backend/app/routers/drafts.py`: `_to_response()` 同步更新
- `frontend/src/api/types.ts`: `DraftResponse` 接口同步 + `CockpitResponse` 更新

## 验证结果
- `pytest`: 555 passed, 2 warnings (22s)
- `npm run build`: passed
- `tsc --noEmit`: 零错误

## 时间
2026-06-26 19:14~19:18（~4 分钟）
