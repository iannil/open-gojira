# 全面审计决策记录 (2026-06-14)

> 日期: 2026-06-14
> 状态: 已确认 (grill-me 会话产出, 19 个决策 + 实施工作分解)
> 关联: `docs/progress/STATUS.md` | `docs/active/roadmap.md` | `docs/reference/specs/2026-06-13-revisit-production-readiness-plan.md`

## 背景

2026-06-13 重审 production-readiness-plan 后,实测发现:
- 220 pending BUY drafts(原 0,watchlist 闸门移除后增长)
- 0 holdings,0 backtest_runs,0 alert_events
- 7 次 Lixinger token expired 警告 + 7 次 circuit opened(全部 silent in_app)
- 20-43% sanity violation rate
- 0/0/0 行 historical_* 数据(backtest engine 完全依赖)

用户目标:**"以生产环境能实战,能真实的完成自动化投资分析的目标,只有真实买入卖出股票留给手动"**。

基于此发起全面 grill-me 审计,产出 19 个决策。

---

## 决策清单(19 个)

### C 分支:Backtest 策略验证(10 个决策)

| # | 决策 | 选项 | 推理 |
|---|---|---|---|
| 1 | **审计目标** | C (策略被回测验证) | 当前 0 backtest_runs,信任闸门要求先验证策略 |
| 2 | **基于输出的动作** | A (信任闘门软) | 不预承诺阈值,靠"看起来不离谱"建立信心即可开始用 |
| 3 | **担心的层** | A (策略逻辑层) | 最直接的不信任是"rule_json 写得对不对",不是"引擎模拟多准" |
| 4 | **输出格式** | B + 临时脚本 | 每笔交易明细 + spot-check CLI 脚本(随机抽样 + 子条件评估 + raw data)。不做 UI dashboard |
| 5 | **数据范围** | A (309 candidates × 5y) | Trust gate 不需要 clean universe。selection bias 影响预测不影响逻辑验证 |
| 6 | **采样** | B (30 条分层 5/策略) | 强制覆盖 6 策略,~15 min 时间预算 |
| 7 | **spot-check 方法** | C (分层+边界+异常自动检测) | 每策略 5 条 = 2 极端 + 2 边界 + 1 反例;脚本主动扫描异常信号 |
| 8 | **失败回退路径** | D (spot-check 输出分类 bug 层) | spot-check 输出已含 A(rule)/B(引擎)/C(数据)三层信息,直接分类 |
| 9 | **迭代流程** | B (3 轮 cap, ~1 hour) | 1 轮发现主要 bug,2 轮验证修复,3 轮最终确认 |
| 10 | **backtest engine 升级** | A (改用 production strategy_engine) | **关键**:v1 engine 用 flat rules 不支持 AND/OR,但 6 策略全部用 AND/OR。必须升级 |
| 11 | **执行规格默认值** | 全接受 | ¥1M initial / production sizing / 沪深300 benchmark / 空仓 T=0 |
| 12 | **trust gate 通过后** | D (1-2 周日常使用 + 高置信时执行首单) | 不直接首单(A 太快),不 30 天无人值守(C 太依赖基础设施) |
| 13 | **ship 顺序** | C (minimal slice 先验证 pipeline) | 1 策略 × 1 股 × 6 月 → 验证 pipeline → 再扩到 309 × 5y |

### A 分支:数据完整性(2 个决策)

| # | 决策 | 选项 | 推理 |
|---|---|---|---|
| 14 | **token 死亡响应** | B-min (UI banner only) | 前端 Alert banner 读 system_alerts。不阻塞操作,不引入 server_chan,不暂停 scheduler。依赖 Q12 D 的用户纪律 |
| 15 | **sanity violation 处理** | A (忽略, spot-check 兜底) | 20-43% violation 多在策略不用的字段(pcf_ttm / mc=0)。策略阈值天然排除坏数据。spot-check 脚本输出每条信号的 sanity 状态作为兜底 |

### D 分支:Drafts 累积处理(2 个决策)

| # | 决策 | 选项 | 推理 |
|---|---|---|---|
| 16 | **stale drafts 处理** | A (auto-supersede) | 每次 plan run 后,所有 pending drafts 中本轮没重新触发 BUY 的,自动 mark `superseded`。draft = 当前建议,过期自动关闭 |
| 17 | **Cockpit draft 展示** | A (保持 Top 5 + show all link) | Q18 决策后 drafts 从 220 → 30-50,Top 5 已覆盖核心。Q12 D 强调高置信才执行 |

### 收尾决策

| # | 决策 | 选项 | 推理 |
|---|---|---|---|
| 18 | **是否继续 drill** | A (停止,进入 ship 阶段) | 19 个决策已覆盖战略层;B/C/E 要么已解决要么是下游;继续 drill 边际收益递减 |

---

## 关键技术发现

### 发现 1:backtest engine v1 与 production strategy 语义错配

**位置**: `backend/app/services/backtest_engine.py` line 19-22

```python
v1 limitations (documented, not bugs):
- Single stock at a time per signal (no portfolio-level constraints)
- No shorting (SELL only if held)
- Strategy rules evaluated independently (AND/OR not supported in v1)
```

**实际状态**:
- v1 backtest engine 用 `config["strategy_rules"]: list[dict]` — flat list,每个 rule 独立评估
- 6 个 production 策略全部用 AND/OR(`high_dividend_cushion`: DYR≥4% **AND** 分红可持续≥60 **AND** OCF/NI≥0.8)
- 直接跑 backtest,要么拆 AND/OR(语义扭曲),要么解析失败

**Q10 决策**: 升级 backtest engine 调用 production `strategy_engine.evaluate(rule_json, ctx)`。这是 Q1-Q9 全部决策的前提。

### 发现 2:drafts 累积极制

**位置**: `backend/app/services/draft_service.py:40-139` 的 `emit()` 函数

```python
# Idempotent: if a pending draft with the same plan/stock/step already exists,
# update it in place instead of creating a duplicate.
```

**实际状态**:
- emit 是 (plan, stock, step_kind, step_index) 幂等 — 不会创建重复
- 220 drafts 是 **220 个独立 stocks** 触发 BUY 信号,**不是 daily 重复**
- **但**: plan_runner 不评估"现有 drafts 是否仍满足条件",已 stale 的 drafts 永远 pending

**Q18 决策**: plan_runner 加 supersede 逻辑(30 行代码),本轮未重新触发的 drafts 自动 mark `superseded`。

### 发现 3:historical_* 表完全空

```
historical_klines:     0 rows
historical_valuations: 0 rows
historical_financials: 0 rows
```

backtest engine 显式依赖(line 23)。historical_data_pipeline 已存在但从未运行。

**Q5 + Q13 决策**: 先 minimal slice(1 股 × 6 月)验证 pipeline,再扩到 309 × 5y。

### 发现 4:Lixinger token 死亡响应断链

**位置**: `backend/app/services/lixinger_client.py:295-360`

```python
# Token / quota / limit issues are critical and need operator action.
if _looks_like_token_or_quota(msg):
    ...
    """Token/quota business errors get a critical alert immediately."""
```

**实际状态**:
- Detection 完整(circuit breaker + token 检测 + system_alert)
- Response 断链(alert 仅 in_app silent;scheduler 继续;drafts 继续生成)
- 7 次 token expire + 7 次 circuit opened 实测全部 silent

**Q15 决策**: B-min(UI banner only)— 不阻塞但视觉提醒,依赖用户纪律。

---

## 实施工作分解

### C 分支(minimal slice first,~4-7 天)

| 阶段 | 工作 | 估时 | 依赖 |
|---|---|---|---|
| **C.1 Slice** | 1 策略(undervalued_entry) × 1 股(600519) × 6 月(2023 H1) | ~1 天 | 之前 |
| C.1.1 | Backtest engine 升级:用 production strategy_engine | 1-2 天 | 独立 |
| C.1.2 | Backfill 600519 × 6 月 × 3 endpoints(klines + valuations + financials) | 秒级 | 独立 |
| C.1.3 | Spot-check 脚本:`spot_check_backtest.py --run-id N --sample-per-strategy 5` | 0.5 天 | 需 C.1.1 + C.1.2 |
| C.1.4 | 跑 slice backtest + spot-check 5 条信号,验证 pipeline 端到端 | ~1 小时 | 需 C.1.3 |
| **C.2 Full** | 扩到 309 × 5y | ~3 天 | 需 C.1 通过 |
| C.2.1 | Backfill 309 × 5y × 3 endpoints(Lixinger 配额约束) | 1-3 天 | 需 C.1 验证 pipeline |
| C.2.2 | 跑 6 策略 × 309 × 5y backtest | 小时级 | 需 C.2.1 |
| C.2.3 | 3 轮迭代 spot-check(每轮 30 条) | ~1 小时 | 需 C.2.2 |

### A 分支(~1 天)

| 工作 | 估时 |
|---|---|
| Cockpit 顶部 Alert banner 组件,数据源 `GET /api/system_alerts?severity=critical&acknowledged=false` | 0.5 天 |
| banner 文案: `"⚠️ 数据可能过期: {alert.message},最后同步 {data_freshness.last_synced_at}"` | 含上面 |
| banner 不阻塞操作,点击跳 `/data` | 含上面 |

### D 分支(~0.5 天)

| 工作 | 估时 |
|---|---|
| plan_runner 加 supersede 逻辑(30 行):run 结束后扫 pending drafts,本轮未触发的 mark `superseded` | 0.5 天 |
| Draft status 增加 `superseded`(若 schema 需要扩展)或复用 `cancelled` 语义 | 含上面 |
| Cockpit "Top 5 by qiu + N more pending" 文案微调 | 极低 |

### E 分支 dry-run(同步进行,与 C.1 并行)

| 工作 | 估时 |
|---|---|
| 用现有 220 drafts 跑端到端 dry-run:draft → DisciplineChecklistModal → 模拟 broker 回报 → trade 写入 → holding 出现 | 0.5 天 |
| 验证 UI/数据流无 bug(不需要真实成交) | 含上面 |

**总估时: 5-7 天**

---

## 决策依赖图

```
Q1 (C backtest)
  ↓
Q2 (A 软闸门) ───► Q12 (D 日常使用+高置信首单)
  ↓                       ↓
Q3 (A 策略逻辑层)        Q15 (B-min UI banner)
  ↓                       ↓
Q4 (B+脚本 spot-check)   Q14 (A 数据完整性)
  ↓                       ↓
Q6 (B 30 条分层)         Q16 (A 忽略 sanity)
  ↓                       
Q7 (C 分层+边界+异常)    
  ↓                       
Q10 (A 升级 engine) ◄── 关键阻塞(AND/OR 错配)
  ↓                       
Q5 (A 309×5y)            
  ↓                       
Q11 (默认值)             
  ↓                       
Q9 (B 3 轮迭代)          
  ↓                       
Q8 (D spot-check 分类)   
  ↓                       
Q13 (C slice first)      
                           
Q17 (D drafts 累积) → Q18 (A auto-supersede) → Q19 (A Top 5)

Q20 (A ship) ←── 19 决策已饱和
```

---

## 与之前决策的关系

| 之前决策 | 当前审计关系 |
|---|---|
| 2026-06-13 重审 #1 (删 PROMOTE) | 已 ship,确认有效(220 drafts 增长证明闸门已去) |
| 2026-06-13 重审 #2 (合并 EXECUTE+TRADE_ENTRY) | 已 ship,Q12 D 依赖此 |
| 2026-06-13 重审 #3 (保留 backtest) | **当前审计 C 分支全部围绕激活 backtest** |
| 2026-06-13 重审 #4 (watchlist 去闸门) | 已 ship |
| 2026-06-13 重审 #5 (跳过 S6 Docker) | 仍然有效,Q12 D dev 模式即可 |
| 2026-06-13 重审 #6 (draft 全表现 Qiu 排序) | 已 ship,Q19 确认 Top 5 + show all 仍然合理 |
| 2026-06-13 重审 #7B (双层闸门) | **C 分支是 Gate 1(backtest 验证),Q12 D 是 Gate 2(DisciplineChecklistModal)** |

---

## 未覆盖的剩余 blocker(使用中暴露后再 drill)

| Blocker | 当前判断 | 何时 drill |
|---|---|---|
| server_chan 通知通道 | Q15 决策 B-min 不需要 | 30 天无人值守阶段 |
| Scheduler 重启行为 | dev 模式可接受 | 30 天无人值守阶段 |
| 首笔实盘 workflow bug | Q12 D 1-2 周后才触发,E dry-run 同步验证 | 真实首单前 |
| Lixinger token 14 天刷新工作流 | 用户 ops,非 Gojira 内 | 第一次 token expire 后 |
| Backup / 数据持久化 | dev 模式 SQLite WAL 已够 | 30 天稳定运行后 |
| Error recovery / Pipeline 失败重试 | dead_letter 已就位,具体行为未实测 | 第一次 pipeline fail 后 |

---

## 参考

- 项目快照: `docs/progress/STATUS.md`
- 路线图: `docs/active/roadmap.md`
- 上次重审: `docs/reference/specs/2026-06-13-revisit-production-readiness-plan.md`
- 第 6 轮审计: `docs/reports/completed/full-audit-round6-2026-06-11.md`
- CLAUDE.md 三原则: 除真实券商下单外全自动化 / 架构尽可能简化 / 交易系统对齐 invest{1,2,3}.md
