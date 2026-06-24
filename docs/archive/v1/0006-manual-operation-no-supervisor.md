# ADR-0006: 全手动运维模型(无 supervisor / 无自动 backup / 无自动维护)

2026-06-24 决定:Gojira 的运维完全 manual。worker 进程没有 launchd/systemd 保活,挂了你手动重启。SQLite backup 没有自动定时,你手动 `cp`。日志/DB 维护没有自动清理,你手动处理。

## Context

grill-me 第 13 题推荐 B(launchd + 定时 backup),理由是 Q5 的 8 周 reliability gate 需要稳定运行 + 数据不丢。但用户明确选 A「全手动」,与决策 1/8 的 YAGNI 路线一致——不引入 launchd plist / cron job / 备份脚本等运维基础设施。

这直接和 Q5 的「8 周连续」冲突:worker 挂了没人拉起,plan_runner 不跑,8 周计时实际断续。冲突用决策 12 松解——8 周重新解读为 elapsed time(经过时间),不要求 uptime。

## Considered Options

- **launchd + 定时 backup(推荐项)**:被拒。用户选 A,接受手动运维的代价
- **NUC 专用硬件 + systemd**:被拒。额外硬件投入,Phase 1 over-kill
- **云端 VPS**:被拒。违反目标 #2「不引入云基础设施」

## Consequences

### 不做

- launchd plist / systemd unit / supervisor 配置
- 自动 backup 脚本(cron / launchd 触发)
- 自动 maintenance(日志轮转、DB vacuum、旧记录清理)

### 做(用户手动责任)

- worker 挂了:`./dev.sh status` 看到 worker 红灯 → `./dev.sh restart worker`
- backup:**强烈建议每周至少一次** `cp backend/data/gojira.db backend/data/backups/manual-$(date +%Y%m%d).db`(8 周数据丢不起)
- 维护:SQLite 膨胀到 500MB+ 时手动 `VACUUM` + 清旧 audit_log / pipeline_runs / llm_logs

### 补救措施(降低 manual 代价)

- Cockpit `WorkerHeartbeatCard`:worker 每 60s 写心跳,卡片显示「最后心跳时间 / 存活状态」。weekly review 时一眼看到 worker 是否还活着——不需要你每天主动检查
- `dev.sh status`:一键查看双进程状态
- 事故定义(决策 10)里「worker 进程崩溃」会触发桌面通知——这是 manual 运维下的兜底:worker 挂了你会知道(前提是 API 进程还活着能发通知)

### Phase 2 复审触发条件

- 翻 auto 后 uptime 才真正关键(autopilot 17:45 跑,worker 必须活着):届时重新评估是否加 launchd
- 如果 Phase 1 期间 worker 挂了 >3 天你没发现(heartbeat 卡片没看 / 桌面通知没收到),说明 manual 运维不够,**必须**加 supervisor
- 如果某次数据丢失(没 backup)导致可靠性评估无依据,**必须**加自动 backup

### 风险接受

- 数据丢失:8 周 paper 数据若丢,可靠性评估重启,损失 ~8 周时间。接受
- worker 长时间挂掉:plan run 攒不齐,可靠性 gate 延后。接受(决策 12 已松解 elapsed time)

## 关联

- 决策来源:`docs/active/redesign-decisions.md` 决策 11
- Q5/Q11 冲突松解(8 周 = elapsed):决策 12
- worker heartbeat 补救:ADR-0004
- Phase 2 复审触发:ADR-0002
