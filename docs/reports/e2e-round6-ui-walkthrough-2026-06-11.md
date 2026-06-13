# P1-1 UI 走查 checklist (round6 回归)

> **走查日期**: 2026-06-12(填实际走查日期)
> **走查人**: [你的名字]
> **走查对象**: round6 修复后的 9 个前端页面
> **关联**: `docs/reports/e2e-round6-acceptance-2026-06-11.md` (API smoke 验收)

## 走查前准备

```bash
# 在项目根目录
cp backend/data/gojira.db backend/data/gojira.db.bak   # 备份 DB
./dev.sh                                                # 启动前后端
```

打开浏览器访问 http://localhost:3000,按下表逐项核对。每项填 ✅/❌/⚠️ + 备注。

走查结束后:
```bash
pkill -f "uvicorn app.main:app" || true
mv backend/data/gojira.db.bak backend/data/gojira.db   # 还原 DB
```

## 走查项

### Cockpit (`/`)
- [ ] 页面加载无 JS error (F12 Console 干净)
- [ ] 持仓列表显示 `weight_pct` 列,数值与 Universe 页一致(P0-03 验证)
- [ ] 若有草稿,草稿行显示 `source` 列/徽标(P1-13 验证)
- [ ] 若持仓某只股价格不可用,该行 pnl 显示"数据不可用"或" - ",不是 `NaN%` 或 `0.00%`(P0-04 残留检查)
- [ ] 加权 DYR 卡片显示合理数值
- [ ] 周期仪表盘显示当前 PE 分位档位

**备注**:

### Universe (`/universe`)
- [ ] 默认查看时,持仓股(held=true)的 weight_pct 与 Cockpit 一致(P0-03 第二端)
- [ ] 切换股票池时不报错
- [ ] 关键字搜索含 % 时不会枚举全量(P1-01 注入防御)

**备注**:

### Plans (`/plans`)
- [ ] 4 个内置预案可见(core_value / resource_macro / bank_anchor / contrarian_scan)
- [ ] 点 "运行" 按钮,触发 POST /api/plans/{id}/run,返回 200
- [ ] 运行后点 "候选股" 能看到候选列表

**备注**:

### Candidates (`/candidates`)
- [ ] 候选股列表加载
- [ ] 7 个筛选条件可用
- [ ] 提升 candidate 到 watchlist 不报错

**备注**:

### StockDetail (`/stock/600519`)
- [ ] K线图加载
- [ ] 论点变量区域可见
- [ ] 修改一个论点变量 → 保存 → 页面自动刷新显示新值(P1-12 验证)
- [ ] 基本信息卡片显示 code/name/industry

**备注**:

### Portfolio (通过 Cockpit 进入持仓编辑)
- [ ] 编辑某持仓的 buy_price → 保存 → Cockpit weight_pct 更新(P0-03 反向验证)
- [ ] 尝试添加一个超大持仓(撞行业上限)→ 报错信息显示且 Cockpit 未变(P0-05 验证)

**备注**:

### Review (`/review`)
- [ ] 月度复盘页面加载无错
- [ ] 时间轴 / 命中率统计区域可见(若 audit_log 有数据)

**备注**:

### DataManagement (`/data`)
- [ ] 5 个 Tab 都可切换(健康 / Pipeline / 股票池 / 质量 / 清理)
- [ ] 健康面板显示数据库大小 + 最后同步时间
- [ ] Pipeline 控制面板列出 5 个 pipeline(universe/dividend/financial/kline/valuation)

**备注**:

### Scheduler (`/scheduler`)
- [ ] 调度任务列表显示 6 个 cron job
- [ ] 点 "立即运行" 不报错(可取消,不必真等执行完)

**备注**:

## 整体感受

- 加载速度可接受?(Cockpit 应在 2s 内完成 - round6 P1-10 并行化)
- 任何页面有 JS error?记录到这里
- 任何页面有 "undefined" / "NaN" 字样?记录到这里

## 总结

- 通过项: X / N
- 失败项: 列表
- 待修(γ 分级 round6 尾巴): 列表

---

## 走查完成后

填完后,告诉 Claude Code 走查完毕,它会:
1. 把本文件 commit
2. 跑 Task 11(γ 分级处理发现的 bug,如 alert_service 重构)
3. 跑 Task 12(更新 roadmap/STATUS)
