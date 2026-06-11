# 候选池筛选增强设计

> 日期: 2026-06-10

## 背景

候选池页面 (`/candidates`) 当前仅支持 2 个筛选条件（所属计划、状态）。Stock 模型上有行业、安全主题、象限、评级、Qiu评分、总部地区等字段未暴露为筛选条件。

## 方案

**前端内存筛选**：页面一次性加载全量候选数据，筛选逻辑全部在浏览器端完成。候选池数据量通常几十到几百条，无需后端分页过滤。

## 筛选条件清单

| 筛选项 | 字段 | 控件类型 | 选项来源 |
|--------|------|---------|---------|
| 所属计划 | plan_id / plan_name | Select | API 拉取计划列表（已有） |
| 状态 | status | Select | active / removed / promoted（已有） |
| 行业 | stock_industry | Select | 从返回数据去重提取 |
| 安全主题 | stock_security_theme | Select | 枚举：能源/粮食/金融/资源/科技/信息/民生 |
| 象限 | stock_quadrant | Select | 枚举：procyclical/countercyclical/distressed_reversal/financial |
| 评级 | stock_tier | Select | 枚举：heaven/mystic |
| Qiu评分 | stock_qiu_score | Select | 枚举：0/1/2/3 |
| 总部地区 | stock_hq_region | Select | 从返回数据去重提取 |
| 是否置顶 | pinned | Switch | 是/否 |

## 后端变更

### 1. 扩展 CandidateResponse Schema

在 `backend/app/schemas/candidate.py` 的 `CandidateResponse` 中新增字段：

```python
stock_security_theme: Optional[str] = None
stock_quadrant: Optional[str] = None
stock_tier: Optional[str] = None
stock_qiu_score: int = 0
stock_hq_region: Optional[str] = None
```

### 2. 更新 _to_response 映射

在 `backend/app/routers/candidates.py` 的 `_to_response` 函数中补充新字段映射：

```python
stock_security_theme=stock.security_theme if stock else None,
stock_quadrant=stock.quadrant if stock else None,
stock_tier=stock.tier if stock else None,
stock_qiu_score=stock.qiu_score if stock else 0,
stock_hq_region=stock.hq_region if stock else None,
```

后端不需要新增 API 端点或修改 service 层。

## 前端变更

### 3. 可折叠筛选面板

- 表格上方放一个「筛选」按钮（带 Badge 显示已激活筛选数量）
- 按钮旁显示已激活筛选的 Tag（可点击移除）
- 点击按钮展开/收起筛选面板（Ant Design Collapse）
- 面板内用 Row/Col 排列筛选项，每行 4 个（Col span=6）
- 面板底部放「重置」按钮清空所有筛选

### 4. 筛选逻辑

- 所有筛选值用 useState 管理
- 数据列表用 useMemo 根据筛选条件过滤
- 枚举类字段（security_theme、quadrant、tier、qiu_score）使用硬编码选项
- 动态字段（industry、hq_region）从返回数据中 useMemo 去重生成选项
- 筛选采用 AND 逻辑：所有条件同时满足

### 5. 前端类型更新

在 `frontend/src/api/types.ts` 中扩展 CandidateResponse 类型，新增后端对应的字段。

## 不包含

- 后端分页/排序增强
- 筛选条件持久化（localStorage）
- 筛选结果导出
