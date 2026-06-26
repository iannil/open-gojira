# 边界判断任务

判断以下股票是否值得进入观察池（watchlist）。

## 股票

- 代码: {{stock_code}}
- 名称: {{stock_name}}

## 规则评估结果（{{failed_count}} 项未通过）

{{rule_results}}

## 你的判断

基于以上规则和该股票的具体情况，回答：
1. 这是不是临时性问题（如周期性低谷）还是结构性问题？
2. 这个股票值不值得花 LLM 资源做深度研究？
3. 通过：true / false
4. 理由：1-2 句

通过 submit_result 提交。
