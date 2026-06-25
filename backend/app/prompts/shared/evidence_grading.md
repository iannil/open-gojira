# Evidence Grading (serenity 证据分级)

> **分级层次**：本文件定义**条目级**评分（每一条 evidence 的来源质量：strong/medium/weak/lead）+ **统一来源优先级清单**。
> **包级**评分（整份研究信息丰富度 A/B/C）见 `defense_methodology.md`。两者不同粒度、互不替代：一条 medium 证据可以出现在一份 A 级研究里。

## 证据强度（4 级，条目级）

| 级别 | 标准 | 适用 |
|------|------|------|
| **strong** | 一手资料 + 多源一致 + 可量化验证 | filing / 交易所文件 / 公司 IR / 电话会 / 监管文件 / 专利 / 标准 / 官方订单 |
| **medium** | 二手资料但可信 + 单一来源 + 部分可验证 | 主流财经媒体 / 专业研报 / 行业协会数据 |
| **weak** | 推测或推断 + 无直接证据 + 依赖类比 | 招聘信息 / 供应链 rumor / 行业专家观点 |
| **unverified lead** | 仅线索 + 无法验证 + 待考证 | 社交媒体 / 论坛 / 个人博客 |

## 来源优先级（统一清单，全 Pipeline 唯一权威）

调用 `web_search` 选取证据、以及数字字段取数时，按此优先级（与上方 4 级一致）：

1. **一手/强证据**：监管文件 / 交易所文件 / 公司公告(filing) / 公司 IR / 电话会(transcript) / 专利 / 标准 / 官方订单
2. **结构化数据源**：Lixinger（理杏仁，本项目财务/估值底座；关键数字优先取此并与一手交叉验证）
3. **二手/中等**：主流财经媒体 / 专业研报 / 行业协会数据
4. **弱**：招聘信息 / 供应链 rumor / 行业专家观点
5. **仅线索**：社交媒体 / 论坛 / 个人博客

> `system_base.md` 与 `defense_methodology.md` 不再各自重述来源优先级，统一引用本清单。

## 当前股价相关声明的特殊规则

任何关于「当前价格 / 最新财报 / 近期公告」的声明，**禁止仅依赖训练知识**（训练数据有截止日期）。

必须通过 `web_search` tool 获取实时信息，并在 `evidence` 数组中提供：
- `claim`：声明内容
- `source_url`：来源 URL（来自 web_search 结果）
- `grade`：strong / medium / weak / unverified lead
- `verified_at`：验证时间戳

## 产业链卡点判断（serenity 工作流）

对于「产业链位置」和「稀缺层」判断：

1. **稀缺层特征**：低供应商数量 + 长认证周期 + 难扩张 + 关键 know-how + 高纯度/规格要求 + 客户认证 + 长交期 + 产能预订
2. **优先级排序**：先排产业链层级，再排公司。**让用户看到系统逻辑，再看到 ticker 列表**
3. **失败条件**：对每个推荐，明确「什么情况说明这个判断错了」——覆盖替代、对手扩产、需求转弱、稀释、毛利恶化、治理风险、客户流失、估值已 price in 成功

## 输出契约

每个 evidence 条目必须包含：
```json
{
  "claim": "...",
  "source_url": "...",
  "source_type": "filing | exchange | ir | transcript | regulator | patent | standard | order | media | research | social",
  "grade": "strong | medium | weak | unverified_lead",
  "verified_at": "ISO timestamp",
  "notes": "可选，补充说明"
}
```
