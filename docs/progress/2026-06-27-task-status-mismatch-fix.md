# 2026-06-27: Task 状态异常修复（success 但实际 failed）

## 问题

task #173 `theme_scan_on_demand`（以及 `deep_research_on_demand`）在执行失败后，TaskEngine 页面显示状态为 **"success"**，但实际结果是失败的。用户反馈：*"Failed 提示failed但是状态却是success"*。

## 根因分析

TaskEngine 的 `_execute_and_finalize` 方法判断 run status 的逻辑只有一条标准：**函数是否抛出异常**。
- 无异常 → status = `"success"`
- 有异常（含 TimeoutError/CancelledError/其他 Exception）→ status = `"failed"`

TaskEngine **从不检查函数的返回值**。返回的 dict 只存为 `result_summary` 字段，其中 `"status"` 键被完全忽略。

而 `deep_research_on_demand` 和 `theme_scan_on_demand` 两个 `@task` 函数在 `except Exception:` 块中做了：
1. `db.rollback()` — 回滚事务
2. 标记数据库中的 report 为 failed 状态
3. `return {"status": "failed", ...}` — **返回但没抛异常**

函数正常返回 → TaskEngine 认为成功 → status = `"success"`。这是错误的。

## 修复

将两个函数 except 块末尾的 `return {"status": "failed", ...}` 改为 `raise`（重新抛出当前异常）。

文件：`backend/app/tasks/llm_pipelines.py`

### deep_research_on_demand（原 line 233）
```python
# 修改前：
return {"status": "failed", "stock_code": stock_code}

# 修改后：
raise
```

### theme_scan_on_demand（原 line 311）
```python
# 修改前：
return {"status": "failed", "theme": theme}

# 修改后：
raise
```

数据库中的 report 标记为 failed 的逻辑保留不变（在 `raise` 之前执行）。

## 风险

- `raise` 后的 db session 清理由 SQLAlchemy `SessionLocal()` 上下文管理器的 `__exit__` 处理，不会泄漏连接。
- 不影响任何其他 task 或 scheduler job。
- 所有其他 task 函数的错误处理方式不一，但经 grep 确认仅此两处有 `return {"status": "failed"}` 模式。
