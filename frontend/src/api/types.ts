/**
 * Type definitions — autopilot edition.
 *
 * Mirrors the lean backend surface we kept after the Step 4 cleanup.
 */

// ── Stock / kline ─────────────────────────────────────────────────────

export interface StockResponse {
  code: string;
  name: string;
  industry: string | null;
  listed_date: string | null;
  quadrant?: string | null;
  qiu_score?: number;
  qiu_detail?: {
    upstream_power: number;
    downstream_power: number;
    government_power: number;
    evidence?: Record<string, string>;
  } | null;
  security_theme?: string | null;
  tier?: string | null;
  notes?: string | null;
  thesis_variables?: ThesisVariable[];
  business_pattern_id?: number | null;
  business_pattern_inferred_at?: string | null;
  business_pattern_name?: string | null;
  business_pattern_first_principle_variable?: string | null;
  business_pattern_power_tier?: number | null;
  // G2/G4/B2 resource flags (manual override via PATCH /stocks/{code}/resource-flags)
  is_cost_leader?: boolean | null;
  has_mine?: boolean | null;
  domestic_leader?: boolean | null;
  expansion_outlook?: boolean | null;
  geo_risk?: boolean | null;
  // G3 forward DYR (预期股息率) — computed backend-side
  forward_dyr?: number | null;
}

export interface ResourceFlagsUpdate {
  cost_leader?: boolean;
  has_mine?: boolean;
  domestic_leader?: boolean;
  expansion_outlook?: boolean;
  geo_risk?: boolean;
}

export interface KlinePoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface KlineResponse {
  stock_code: string;
  freq: 'day' | 'week' | 'month';
  points: KlinePoint[];
}

// ── Stock detail data sources ─────────────────────────────────────────

export interface ShareholderRecord {
  date: string;
  holder_name: string;
  holder_type: string | null;
  holding_quantity: number | null;
  holding_ratio: number | null;
}

export interface NorthFlowRecord {
  date: string;
  net_buy_amount: number | null;
  holding_quantity: number | null;
  holding_ratio: number | null;
}

export interface MarginTradingRecord {
  date: string;
  financing_balance: number | null;
  securities_balance: number | null;
  net_financing: number | null;
}

// ── Watchlist + holdings (portfolio backend kept) ────────────────────

export interface WatchlistGroupResponse {
  id: number;
  name: string;
  description: string | null;
}

export interface HoldingResponse {
  id: number;
  stock_code: string;
  stock_name?: string | null;
  stock_industry?: string | null;
  stock_tier?: string | null;
  buy_date: string;
  buy_price: number;
  quantity: number;
  sell_date?: string | null;
  sell_price?: number | null;
  stop_profit_price: number;
  trade_rationale?: string | null;
  sell_thesis?: string | null;
  current_value?: number | null;
  pnl?: number | null;
  pnl_pct?: number | null;
  annualized_return_pct?: number | null;
  weight_pct?: number | null;
}

export interface PortfolioSummary {
  total_cost: number;
  total_value: number;
  total_pnl: number | null;
  total_pnl_pct: number | null;
  position_count: number;
  holdings: HoldingResponse[];
  warnings: string[];
  cash_reserve: number;
  cash_ratio_pct: number;
  portfolio_weighted_dyr: number | null;
  target_weighted_dyr: number;
  portfolio_annualized_pct: number | null;
}

export interface CashflowGoalResponse {
  annual_expense: number;
  goal_multiple: number;
  currency: string;
  notes: string | null;
  cash_reserve: number;
  target_annual_cashflow: number;
  updated_at: string | null;
}

export interface CashflowGoalUpdate {
  annual_expense?: number;
  goal_multiple?: number;
  currency?: string;
  notes?: string | null;
  cash_reserve?: number;
}

export interface AuditLogEntry {
  id: number;
  entity_type: string;
  entity_id: string | null;
  event: string;
  actor: string;
  stock_code: string | null;
  summary: string;
  payload: Record<string, unknown> | null;
  created_at: string | null;
}

export type PlanStatus = 'active' | 'paused' | 'archived';

export interface BuyTrigger {
  kind: 'price_le' | 'dyr_ge' | 'drawdown_from_last_buy' | 'pe_pct_le';
  value: number;
}

export interface SellTrigger {
  kind:
    | 'profit_pct_ge'
    | 'dyr_le'
    | 'dyr_fwd_le'
    | 'pe_pct_ge'
    | 'cycle_position_ge';  // B1 (G1 v2)
  value: number | string;  // cycle_position_ge uses CycleBuyMax string
}

export interface InvalidationRule {
  kind: 'ocf_to_ni_3y_lt' | 'dividend_cut_pct_ge' | 'thesis_manual_revoke';
  value: number;
}

export interface BuyStep {
  trigger: BuyTrigger;
  add_pct: number;
}

export interface SellStep {
  trigger: SellTrigger;
  reduce_pct_of_position: number;
}

export interface TradingRules {
  buy_ladder: BuyStep[];
  sell_ladder: SellStep[];
  invalidation: InvalidationRule[];
  cooldown_days: number;
}

export interface StrategyComposition {
  strategy_ids: number[];
  logic: 'AND' | 'OR';
}

export interface ScanScope {
  type: 'all_stocks' | 'industries' | 'index' | 'watchlist' | 'custom';
  values: string[];
}

export type CycleBuyMax = 'extreme_low' | 'low' | 'mid' | 'high' | 'extreme_high';

export interface PlanResponse {
  id: number;
  name: string;
  slug: string;
  description: string;
  status: PlanStatus;
  strategy_composition: StrategyComposition;
  scan_scope: ScanScope;
  schedule_cron: string;
  trading_rules: TradingRules | null;
  cycle_buy_max: CycleBuyMax;
  disable_midstream_filter: boolean;
  last_run_at: string | null;
  last_run_summary: Record<string, unknown> | null;
  is_builtin: boolean;
  candidate_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PlanCreate {
  name: string;
  slug: string;
  description?: string;
  strategy_composition: StrategyComposition;
  scan_scope: ScanScope;
  schedule_cron?: string;
  trading_rules?: TradingRules | null;
  cycle_buy_max?: CycleBuyMax;
  disable_midstream_filter?: boolean;
}

export interface PlanUpdate {
  name?: string;
  description?: string;
  status?: PlanStatus;
  strategy_composition?: StrategyComposition;
  scan_scope?: ScanScope;
  schedule_cron?: string;
  trading_rules?: TradingRules | null;
  cycle_buy_max?: CycleBuyMax;
  disable_midstream_filter?: boolean;
}

export const CYCLE_BUY_MAX_OPTIONS: { value: CycleBuyMax; label: string }[] = [
  { value: 'extreme_low', label: '极度低估（可重仓）' },
  { value: 'low', label: '低估（积极配置）' },
  { value: 'mid', label: '中等（默认，正常持有）' },
  { value: 'high', label: '高估（主动减仓）' },
  { value: 'extreme_high', label: '极度高估（尽量空仓）' },
];

export interface DraftResponse {
  id: number;
  plan_id: number | null;
  code: string;
  side: 'BUY' | 'SELL';
  status: 'pending' | 'executed' | 'cancelled' | 'superseded';
  step_kind: string;
  step_index: number;
  add_pct: number | null;
  reduce_pct_of_position: number | null;
  suggested_quantity: number | null;
  reason: string;
  source: string;
  /** Phase 5 draft_generator fields */
  research_report_id: number | null;
  target_price: number | null;
  strategy_tier: 'aggressive' | 'steady' | null;
  sizing_logic: string | null;
  thesis_status: 'healthy' | 'invalidated' | null;
  expires_at: string | null;
  serenity_thesis: string | null;
  triggered_at: string | null;
  executed_at: string | null;
}

// ── Cockpit DTO ───────────────────────────────────────────────────────

export interface CockpitCashflow {
  annual_expense: number;
  goal_multiple: number;
  target_annual_cashflow: number;
  weighted_dyr: number | null;
  annual_passive_cashflow: number;
  goal_progress: number | null;
  total_portfolio_value: number;
  currency: string;
}

export interface CockpitDraft {
  id: number;
  plan_id: number;
  code: string;
  stock_name?: string | null;
  side: 'BUY' | 'SELL';
  status: string;
  step_kind: string;
  step_index: number;
  add_pct: number | null;
  reduce_pct_of_position: number | null;
  suggested_quantity?: number | null;
  qiu_score?: number | null;
  reason: string;
  source?: string;
  triggered_at: string | null;
}

export interface CockpitHoldingItem {
  id: number;
  stock_code: string;
  stock_name?: string | null;
  stock_industry?: string | null;
  stock_tier?: string | null;
  buy_date?: string | null;
  buy_price: number;
  quantity: number;
  sell_date?: string | null;
  sell_price?: number | null;
  stop_profit_price?: number;
  trade_rationale?: string | null;
  sell_thesis?: string | null;
  current_value?: number | null;
  pnl?: number | null;
  pnl_pct?: number | null;
  annualized_return_pct?: number | null;
  weight_pct?: number | null;
}

export interface CockpitQuadrant {
  quadrant: string;
  value: number;
  weight_pct: number;
  count: number;
  stock_codes: string[];
}

export interface CockpitAlertItem {
  id: number;
  rule_id: number;
  stock_code: string | null;
  level: string;
  message: string;
  triggered_at: string | null;
}

export interface CockpitPlanRunSummary {
  passed?: number;
  scanned?: number;
  drafts_emitted?: number;
  filtered_midstream_non_leader?: number;
  cycle_buy_blocked?: number;
  cycle_unavailable_skipped?: boolean;
  cycle_position?: string | null;
  errors?: string[];
}

export interface CockpitPlanSummary {
  id: number;
  slug: string;
  name: string;
  status: PlanStatus;
  description: string;
  is_builtin: boolean;
  cycle_buy_max?: CycleBuyMax;
  disable_midstream_filter?: boolean;
  last_run_at?: string | null;
  last_run_summary?: CockpitPlanRunSummary | null;
}

export interface CycleAssessment {
  pe_pct_10y: number | null;
  pb_pct_10y: number | null;
  dyr_index: number | null;
  cycle_position: string;
  position_range: [number, number];
  position_advice: string;
}

export interface DividendProjection {
  next_12m_expected: number;
  by_holding: {
    code: string;
    name: string;
    quantity: number;
    expected_per_share: number;
    expected_total: number;
    expected_ex_month: number | null;
    yield_pct: number | null;
  }[];
  annual_passive_target: number | null;
  dividend_gap: number | null;
  dividend_coverage: number | null;
  trailing_12m_actual: number;
  projection_basis: string;
}

export interface ThesisAlert {
  code: string;
  stock_name: string;
  variable_name: string;
  current_value: number | null;
  threshold_type: string;
  threshold_value: number;
  direction: string;
  message: string;
}

// ── v2 信号优先 cockpit (decision 19) ─────────────────────────────────────

export interface CockpitReportItem {
  id: number;
  stock_code: string;
  pipeline_type: string;
  overall_score: number | null;
  recommendation: string | null;
  evidence_grade: string | null;
  status: string;
  created_at: string | null;
}

export interface CockpitAlertV2 {
  id: number;
  severity: string;
  category: string;
  message: string;
  created_at: string | null;
}

export interface CockpitResponse {
  as_of: string;
  // 顶部：待办信号
  drafts: CockpitDraft[];
  drafts_pending_count: number;
  signal_alerts: CockpitAlertV2[];
  signal_alerts_count: number;
  // 中部：持仓概览
  portfolio: {
    summary: Record<string, number | null>;
    holdings: CockpitHoldingItem[];
  };
  // 底部：候选池 + 观察池（lifecycle 状态计数）
  pipeline_counts: Record<string, number>;
  // 应用内通知
  alerts: {
    items: CockpitAlertV2[];
    critical_count: number;
  };
  // 信号 + 报告
  recent_reports: CockpitReportItem[];
  // 任务调度
  task_health: {
    running_tasks: number;
    queued_tasks: number;
    failed_tasks_24h: number;
    last_run_at: string | null;
    last_run_status: string | null;
  };
  errors: string[];
}

/**
 * D4 (2026-06-17 invest-alignment audit): invest2 §7 平方差魔咒实时指标。
 * Cockpit "组合风险" 卡片数据源。has_holdings=false 时其他字段为 null。
 */
export interface PortfolioRisk {
  has_holdings: boolean;
  holdings_count: number;
  window_days: number;
  annual_volatility: number | null;
  max_drawdown_30d: number | null;
  max_drawdown_90d: number | null;
  sharpe_proxy: number | null;
  errors: string[];
}

export interface SerenityMonthlySpend {
  month: string;
  spend_cny: number;
  budget_cny: number;
  remaining_cny: number;
  run_count: number;
  over_budget: boolean;
}

export interface SerenityCockpitSummary {
  theme_id: number;
  theme_name: string;
  run_id: number;
  started_at: string;
  system_change_excerpt: string;
  token_input: number;
  token_output: number;
  search_count: number;
  top_rankings: Array<{
    rank: number;
    stock_code: string;
    constrains_what: string;
    main_risk_md: string;
  }>;
}

// ── Monthly review ────────────────────────────────────────────────────

export interface ReviewByStock {
  stock_code: string;
  drafts_triggered: number;
  business_pattern_name?: string | null;
  first_principle_variable?: string | null;
}

export interface ReviewEntry {
  id: number;
  entity_type: string;
  entity_id: string | null;
  event: string;
  actor: string;
  stock_code: string | null;
  summary: string;
  payload: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ReviewResponse {
  month: string;
  drafts: {
    triggered: number;
    executed: number;
    cancelled: number;
    hit_rate: number | null;
    buy: number;
    sell: number;
  };
  plans: {
    created: number;
    invalidated: number;
    status_changed: number;
  };
  holdings: {
    created: number;
    sold: number;
  };
  cashflow_goal_updates: number;
  by_stock: ReviewByStock[];
  entries: ReviewEntry[];
  cycle: CycleAssessment | null;
  thesis_alerts: ThesisAlert[];
}

// ── Plan templates ────────────────────────────────────────────────────

export interface PlanTemplateSpecCore {
  buy_ladder: BuyStep[];
  sell_ladder: SellStep[];
  invalidation: InvalidationRule[];
  cooldown_days: number;
}

export interface PlanTemplateResponse {
  id: number;
  name: string;
  description: string;
  is_builtin: boolean;
  spec_core: PlanTemplateSpecCore;
  created_at: string | null;
  updated_at: string | null;
}

export interface PlanTemplateCreate {
  name: string;
  description?: string;
  spec_core: PlanTemplateSpecCore;
}

// ── Theme system ─────────────────────────────────────────────────────

export interface ThemeItem {
  id: number;
  name: string;
  description?: string | null;
  target_weight_pct: number;
}

export interface ThemeTarget {
  theme: string;
  target_pct: number;
  actual_pct: number;
  drift_pct: number;
  warning: string | null;
}

export interface ThemeExposureItem {
  theme: string;
  weight_pct: number;
  value: number;
  count: number;
  stock_codes: string[];
}

export interface ThemeExposureAnalysis {
  exposure: ThemeExposureItem[];
  targets: ThemeTarget[];
  warnings: string[];
}

/** @deprecated kept for backward-compat; new code should use ThemeExposureAnalysis */
export interface ThemeExposure {
  themes: ThemeItem[];
  targets: ThemeTarget[];
  warnings: string[];
}

// ── Thesis variables ────────────────────────────────────────────────

export interface ThesisVariable {
  name: string;
  current_value: number | null;
  target_condition: string | null;
  unit: string | null;
  source?: string | null;
  synced_at?: string | null;
}

// ── BusinessPattern (生意模式) ──────────────────────────────────────

export interface ThesisVariableTemplate {
  name: string;
  unit: string | null;
  source: string; // 'manual' | 'lixinger'
  current_value?: number | null;
  target_condition?: string | null;
}

export interface BusinessPattern {
  id: number;
  name: string;
  theme_id?: number | null;
  description?: string | null;
  first_principle_variable?: string | null;
  power_tier_baseline: number;
  thesis_variables: ThesisVariableTemplate[];
  lixinger_industries: string[];
  source_ref?: string | null;
  is_builtin: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BusinessPatternCreate {
  name: string;
  theme_id?: number | null;
  description?: string | null;
  first_principle_variable?: string | null;
  power_tier_baseline?: number;
  thesis_variables?: ThesisVariableTemplate[];
  lixinger_industries?: string[];
}

export interface BusinessPatternUpdate {
  name?: string;
  theme_id?: number | null;
  description?: string | null;
  first_principle_variable?: string | null;
  power_tier_baseline?: number;
  thesis_variables?: ThesisVariableTemplate[];
  lixinger_industries?: string[];
  source_ref?: string | null;
}

export interface BusinessPatternThesisTemplates {
  pattern_id: number;
  pattern_name: string;
  templates: ThesisVariableTemplate[];
}

export interface InferAllSummary {
  total: number;
  updated: number;
  protected: number;
  cleared: number;
}

// ── Revenue ────────────────────────────────────────────────────────

export interface RevenueSegment {
  name: string | null;
  category: string | null;
  revenue: number | null;
  ratio: number | null;
}

export interface RevenueComposition {
  date: string;
  segments: RevenueSegment[];
}

// ── Rebalancing suggestions ─────────────────────────────────────────

export interface RebalanceSuggestion {
  level: 'position' | 'quadrant' | 'theme';
  code?: string;
  quadrant?: string;
  theme?: string;
  current_pct: number;
  target_pct: number;
  drift_pct: number;
  action: string;
  priority: 'high' | 'medium' | 'low';
}

// ── Universe ──────────────────────────────────────────────────────────

export interface UniverseItem {
  code: string;
  name: string;
  tier: string | null;
  security_theme: string | null;
  industry: string | null;
  qiu_score: number;
  has_plan: boolean;
  plan_status: string | null;
  candidate_count?: number;
  is_held: boolean;
  weight_pct: number | null;
  latest_pe_pct: number | null;
  latest_dyr: number | null;
}

export interface FullUniverseItem {
  code: string;
  name: string;
  industry: string | null;
  latest_pe_pct: number | null;
  latest_pb_pct: number | null;
  latest_dyr: number | null;
  latest_pe_ttm: number | null;
  latest_pb: number | null;
}

export interface FullUniverseResponse {
  items: FullUniverseItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface UniverseCoverageStats {
  total_stocks: number;
  valuation_coverage: number;
  coverage_pct: number;
  mode: 'manual' | 'full_coverage';
}

// ── Qiu Score ─────────────────────────────────────────────────────────

export interface QiuScoreInput {
  upstream_power: number;
  downstream_power: number;
  government_power: number;
  evidence: Record<string, string>;
}

// ── Periodic Review ───────────────────────────────────────────────────

export interface QuarterlyReview {
  period: string;
  plan_success_rate: number | null;
  plans_completed: number;
  plans_invalidated: number;
  plans_expired: number;
  drafts_executed: number;
  drafts_cancelled: number;
  discipline_score: number | null;
  discipline_with_checklist: number;
  discipline_total: number;
  theme_alignment_pct: number;
  tier_distribution: Record<string, number>;
  holdings_count: number;
}

export interface AnnualReview {
  period: string;
  quarters: QuarterlyReview[];
  total_executed: number;
  total_cancelled: number;
  goal_progress_pct: number | null;
  dividend_records_count: number;
  dividend_income_estimate: number;
  holdings_count: number;
}

// ── Strategy system ───────────────────────────────────────────────────

export type StrategyField =
  | 'dyr'
  | 'pe_pct_10y'
  | 'pb_pct_10y'
  | 'dividend_sustainability'
  | 'ocf_to_ni'
  | 'qiu_score'
  | 'industry_in'
  | 'security_theme_in'
  | 'bank_blind_box'
  | 'price_drop_pct'
  | 'hq_region_tier'
  | 'market_temperature';

export interface StrategyCondition {
  field: StrategyField;
  op: '>=' | '<=' | '==' | 'in';
  value: number | string | string[];
}

export interface StrategyRule {
  logic: 'AND' | 'OR';
  conditions: StrategyCondition[];
}

export interface StrategyTestConditionResult {
  field: StrategyField;
  passed: boolean;
  detail: string;
}

export interface StrategyTestResponse {
  stock_code: string;
  stock_name: string;
  passed: boolean;
  conditions: StrategyTestConditionResult[];
}

export interface StrategyResponse {
  id: number;
  name: string;
  slug: string;
  description: string;
  kind: 'builtin' | 'custom';
  rule: StrategyRule;
  is_builtin: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface StrategyCreate {
  name: string;
  slug: string;
  description?: string;
  rule: StrategyRule;
}

export interface StrategyUpdate {
  name?: string;
  description?: string;
  rule?: StrategyRule;
}

// ── Scheduler ──────────────────────────────────────────────────────────

export interface SchedulerJobResponse {
  job_id: string;
  cron_expr: string;
  enabled: boolean;
  description: string | null;
  next_run_time: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
  last_duration_ms: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SchedulerJobUpdate {
  cron_expr?: string;
  enabled?: boolean;
}

export interface JobExecutionResponse {
  id: number;
  job_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  result_summary: string | null;
  error_message: string | null;
}

// ── Tasks ──────────────────────────────────────────────────────────────

export interface TaskResponse {
  task_id: string;
  type: string;
  status: string;
  trigger_type: string;
  cron_expr: string | null;
  event_source: string | null;
  depends_on: string[] | null;
  retry_config: Record<string, unknown> | null;
  timeout_seconds: number | null;
  mutex_enabled: boolean;
  enabled: boolean;
  tags: string[] | null;
  description: string | null;
  next_run_time: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
  last_duration_ms: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskUpdate {
  cron_expr?: string;
  enabled?: boolean;
  timeout_seconds?: number;
  retry_config?: Record<string, unknown>;
  description?: string;
}

export interface TaskRunResponse {
  id: number;
  task_id: string;
  status: string;
  progress: number;
  progress_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  retry_count: number;
  max_retries: number;
  last_error: string | null;
  result_summary: string | null;
  worker_id: string | null;
  triggered_by: string;
  trace_id: string | null;
  created_at: string | null;
}

export interface TriggerTaskResponse {
  task_id: string;
  run_id: number;
  status: string;
  message: string;
}

export interface TaskHealthResponse {
  engine_running: boolean;
  running_tasks: number;
  queued_tasks: number;
  failed_tasks_24h: number;
  workers_active: number;
  uptime_seconds: number | null;
}

export interface TaskRunDetailResponse extends TaskRunResponse {
  task: TaskResponse | null;
}

// ── Sync Data Summaries ───────────────────────────────────────────────

export interface KlineSyncSummary {
  stock_code: string;
  stock_name: string;
  earliest_date: string | null;
  latest_date: string | null;
  total_bars: number;
}

export interface DividendRecordResponse {
  id: number;
  stock_code: string;
  stock_name: string | null;
  ex_date: string | null;
  amount_per_share: number;
  quantity_held: number;
  total_received: number;
  reinvested: boolean | null;
  created_at: string | null;
}

export interface DividendYearSummary {
  year: number;
  total_received: number;
  count: number;
}

export interface DividendStockSummary {
  stock_code: string;
  stock_name: string | null;
  total_received: number;
  count: number;
  annual_yield: number | null;
}

export interface DividendSummaryResponse {
  total_cumulative: number;
  by_year: DividendYearSummary[];
  by_stock: DividendStockSummary[];
}

// ── Candidate system ──────────────────────────────────────────────────

export interface CandidateResponse {
  id: number;
  plan_id: number;
  plan_name: string;
  stock_code: string;
  stock_name: string;
  stock_industry: string | null;
  stock_security_theme: string | null;
  stock_quadrant: string | null;
  stock_tier: string | null;
  stock_qiu_score: number;
  stock_hq_region: string | null;
  dividend_payout_commitment_pct: number | null;
  status: 'active' | 'removed';
  first_seen_at: string | null;
  last_confirmed_at: string | null;
  last_eval: Record<string, { passed: boolean; details: string[] }> | null;
  pinned: boolean;
  notes: string | null;
  source: 'rule_based' | 'serenity';
}

export interface DataCompleteness {
  has_valuation: boolean;
  has_financial: boolean;
  has_kline: boolean;
  has_dividend: boolean;
}

export interface StockPoolItem {
  code: string;
  name: string;
  industry: string | null;
  tier: string | null;
  security_theme: string | null;
  added_at: string | null;
  data_completeness: DataCompleteness;
}

export interface StockSearchResult {
  code: string;
  name: string;
  industry: string | null;
  listed_date: string | null;
}

export interface DataTypeStatus {
  total_records: number;
  stock_count: number;
  latest_date: string | null;
  earliest_date: string | null;
}

export interface DataStatusOverview {
  valuations: DataTypeStatus;
  financials: DataTypeStatus;
  klines: DataTypeStatus;
  dividends: DataTypeStatus;
}

export interface SyncTriggerResponse {
  run_id: string;
  pipeline_type: string;
  stock_count: number;
  status: string;
}

export interface SyncTaskStatus {
  run_id: string;
  pipeline_type: string;
  status: string;
  config: Record<string, unknown> | null;
  total_items: number;
  completed_items: number;
  failed_items: number;
  progress: number;
  started_at: string | null;
  finished_at: string | null;
  summary: Record<string, unknown> | null;
  created_at: string | null;
}

export interface CleanupPreview {
  data_type: string;
  record_count: number;
  date_range: string | null;
}

export interface CleanupResult {
  data_type: string;
  deleted_count: number;
}

// ── Pipeline & Quality ─────────────────────────────────────────────────

export interface PipelineRunDetail {
  run_id: string;
  pipeline_type: string;
  status: 'pending' | 'running' | 'completed' | 'completed_with_errors' | 'failed' | 'cancelled';
  config: { stock_codes?: string[]; force_full?: boolean; years?: number } | null;
  total_items: number;
  completed_items: number;
  failed_items: number;
  progress: number;
  started_at: string | null;
  finished_at: string | null;
  summary: {
    total?: number;
    completed?: number;
    failed?: number;
    failed_codes?: string[];
    failed_errors?: Record<string, string>;
    duration_seconds?: number | null;
  } | null;
  created_at: string;
}

export interface PipelineHealthResponse {
  [dataType: string]: {
    records: number;
    stocks: number;
    latest_date: string | null;
    fresh: boolean;
  };
}

export interface ApiUsageResponse {
  today: {
    date: string;
    total_calls: number;
    total_cached_hits: number;
    total_errors: number;
    cache_hit_rate: number;
    endpoints: Array<{
      endpoint: string;
      calls: number;
      cached_hits: number;
      errors: number;
      avg_ms: number | null;
    }>;
  };
  month: {
    year: number;
    month: number;
    total_calls: number;
    total_cached: number;
    total_errors: number;
    budget: number;
    budget_used_pct: number;
  };
  trend: Array<{ date: string; calls: number; cached: number }>;
}

export interface DeadLetterStatsResponse {
  total: number;
  pending: number;
  retrying: number;
  exhausted: number;
  resolved: number;
}

export interface DataQualityResponse {
  overall_score: number;
  data_types: {
    [dataType: string]: {
      completeness_rate: number;
      freshness: 'fresh' | 'stale' | 'missing';
      gap_count: number;
      anomaly_count: number;
      validation_pass_rate: number;
      details: {
        total_stocks: number;
        covered_stocks: number;
        latest_date: string | null;
        earliest_date: string | null;
      };
    };
  };
  recommendations: string[];
}

// ── Trades ────────────────────────────────────────────────────────────

export type TradeSide = 'BUY' | 'SELL' | 'DIVIDEND' | 'CORP_ACTION';
export type TradeSource =
  | 'manual'
  | 'csv_import'
  | 'broker_api'
  | 'corp_action'
  | 'migration'
  | 'reversal';

export interface Trade {
  id: number;
  stock_code: string;
  side: TradeSide;
  price: number;
  quantity: number;
  filled_at: string;
  commission: number;
  stamp_duty: number;
  transfer_fee: number;
  total_value: number;
  source: TradeSource;
  source_ref: string | null;
  fee_source: 'auto' | 'manual_override';
  note: string | null;
  created_at: string;
  reversed_by_trade_id: number | null;
}

export interface TradeListResponse {
  items: Trade[];
  total: number;
}

export interface TradeCreateInput {
  stock_code: string;
  side: TradeSide;
  price: number;
  quantity: number;
  filled_at: string;
  source?: TradeSource;
  source_ref?: string;
  commission_override?: number;
  note?: string;
}

// ── Cash ──────────────────────────────────────────────────────────────

export interface CashBalance {
  balance: number;
  as_of_at: string;
  last_trade_id: number | null;
  last_adjustment_id: number | null;
}

export interface CashAdjustment {
  id: number;
  amount: number;
  happened_at: string;
  reason: 'deposit' | 'withdrawal' | 'dividend' | 'other';
  note: string | null;
  created_at: string;
}

export interface CashAdjustmentInput {
  amount: number;
  happened_at: string;
  reason: 'deposit' | 'withdrawal' | 'dividend' | 'other';
  note?: string;
}

// ── Broker fee configs ────────────────────────────────────────────────

// ── Price band / available quantity (S2 UI validation) ────────────────

export interface PriceBand {
  code: string;
  low: number | null;
  high: number | null;
  prev_close: number | null;
  board: string;
  is_st: boolean;
  is_suspended: boolean;
  listing_status: string | null;
}

export interface AvailableQuantity {
  code: string;
  available: number;
  frozen: number;
  total: number;
}

export interface BrokerFeeConfig {
  id: number;
  broker_name: string;
  commission_rate: number;
  commission_min: number;
  stamp_duty_rate: number;
  transfer_fee_rate: number;
  effective_from: string;
  is_active: boolean;
}

export interface BrokerFeeConfigCreate {
  broker_name: string;
  commission_rate: number;
  commission_min: number;
  stamp_duty_rate: number;
  transfer_fee_rate: number;
  effective_from: string;
  is_active?: boolean;
}

// ── Valuation ──────────────────────────────────────────────────────────

export interface PercentileBand {
  percentile: number;
  value: number;
}

export interface PercentileResponse {
  pe_bands: PercentileBand[];
  pb_bands: PercentileBand[];
  current_pe: number | null;
  current_pb: number | null;
  current_pe_percentile: number | null;
  current_pb_percentile: number | null;
}

export interface ValuationSnapshot {
  id: number;
  stock_code: string;
  date: string | null;
  pe_ttm: number | null;
  pb: number | null;
  pe_percentile_10y: number | null;
  pb_percentile_10y: number | null;
  dividend_yield: number | null;
  created_at: string | null;
}

export interface ForwardDyrResponse {
  stock_code: string;
  forward_dyr: number | null;
  payout_ratio_avg_3y: number | null;
  eps: number | null;
  current_price: number | null;
  trailing_dyr: number | null;
  basis_note: string;
}

export interface ValuationDashboard {
  stock_code: string;
  latest_snapshot: ValuationSnapshot | null;
  snapshots: ValuationSnapshot[];
  current_pe: number | null;
  current_pb: number | null;
  current_price: number | null;
  dividend_yield: number | null;
  market_cap: number | null;
}

// ── System alerts (S3 infra-level alerts) ─────────────────────────────

export type SystemAlertSeverity = 'info' | 'warning' | 'critical';
export type SystemAlertCategory = 'data' | 'scheduler' | 'api' | 'db' | 'token';

export interface SystemAlert {
  id: number;
  severity: SystemAlertSeverity;
  category: SystemAlertCategory;
  message: string;
  detail_json: Record<string, unknown> | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface UnresolvedCount {
  count: number;
}

// ── Corporate actions (S4A) ───────────────────────────────────────────

export type CorpActionType =
  | 'cash_dividend'
  | 'stock_dividend'
  | 'capitalization'
  | 'rights_issue'
  | 'delist'
  | 'merger'
  | 'code_change';

export type CorpActionStatus = 'pending' | 'processed';

export interface CorpAction {
  id: number;
  stock_code: string;
  ex_date: string;
  action_type: CorpActionType;
  params_json: Record<string, unknown>;
  source: string;
  created_at: string;
  processed_at: string | null;
  applied_trade_id: number | null;
  note: string | null;
}

export interface ListCorpActionsParams {
  stock_code?: string;
  action_type?: CorpActionType;
  source?: string;
  status?: CorpActionStatus;
  limit?: number;
}

export interface ProcessPendingResult {
  processed_count: number;
  skipped_count: number;
}

export interface SyncDividendsRequest {
  stock_codes: string[];
  start_date?: string;
  end_date?: string;
}

export interface SyncDividendsResult {
  new_count: number;
  failed_codes: string[];
}

// ── Backtests (S4D) ───────────────────────────────────────────────────

export type BacktestRuleAction = 'BUY' | 'SELL';

export interface BacktestRule {
  metric: string;
  operator: '<' | '>' | '<=' | '>=' | '==';
  threshold: number;
  action: BacktestRuleAction;
  target_pct?: number;
}

export interface BacktestConfig {
  stock_codes: string[];
  start_date: string;
  end_date: string;
  initial_capital: number;
  slippage_bps: number;
  strategy_rules: BacktestRule[];
}

export interface BacktestMetrics {
  cagr: number;
  total_return: number;
  sharpe: number;
  max_drawdown: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  trade_count: number;
  benchmark_return: number | null;
  alpha: number | null;
}

export interface EquityPoint {
  date: string;
  value: number;
}

export interface TradeRecord {
  side: TradeSide;
  code: string;
  qty: number;
  price: number;
  total: number;
  realized_pnl?: number;
  date?: string | null;
  per_share?: number;
}

export interface FinalPosition {
  quantity: number;
  avg_cost: number;
}

export interface BacktestResult {
  metrics: BacktestMetrics;
  equity_curve: EquityPoint[];
  monthly_returns: Record<string, number>;
  trades_log: TradeRecord[];
  final_cash: number;
  final_positions: Record<string, FinalPosition>;
}

export type BacktestStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface BacktestRun {
  id: number;
  status: BacktestStatus;
  config_json: BacktestConfig;
  result_json: BacktestResult | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// ── Notifications (S5.4) ──────────────────────────────────────────────

export type NotificationChannelType =
  | 'in_app'
  | 'server_chan'
  | 'email'
  | 'dingtalk_webhook'
  | 'telegram_bot';

export type NotificationSeverityFilter = 'all' | 'warning_and_above' | 'critical_only';

export interface NotificationChannel {
  id: number;
  name: string;
  type: NotificationChannelType;
  config_json: Record<string, unknown>;
  enabled: boolean;
  severity_filter: NotificationSeverityFilter;
  created_at: string | null;
  updated_at: string | null;
}

export interface NotificationChannelCreate {
  name: string;
  type: NotificationChannelType;
  config_json: Record<string, unknown>;
  enabled?: boolean;
  severity_filter?: NotificationSeverityFilter;
}

export interface NotificationChannelUpdate {
  config_json?: Record<string, unknown>;
  enabled?: boolean;
  severity_filter?: NotificationSeverityFilter;
}

export interface NotificationTestResult {
  success: boolean;
  error: string | null;
}

// ── Holding risk rules (S5.4) ─────────────────────────────────────────

export type StopLossType = 'pct_from_cost' | 'fixed_price' | 'trailing';
export type TakeProfitType = 'pct_from_cost';

export interface HoldingRiskRule {
  id: number;
  stock_code: string;
  stop_loss_pct: number | null;
  stop_loss_type: StopLossType;
  take_profit_pct: number | null;
  take_profit_type: TakeProfitType;
  peak_price: number | null;
  enabled: boolean;
  triggered_at: string | null;
  trigger_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RiskRuleCreate {
  stock_code: string;
  stop_loss_pct?: number | null;
  stop_loss_type?: StopLossType;
  take_profit_pct?: number | null;
  take_profit_type?: TakeProfitType;
  enabled?: boolean;
}

export interface RiskRuleUpdate {
  stop_loss_pct?: number | null;
  stop_loss_type?: StopLossType;
  take_profit_pct?: number | null;
  take_profit_type?: TakeProfitType;
  enabled?: boolean;
  peak_price?: number | null;
}

// ── Serenity Research ──────────────────────────────────────────────────

export type ResearchMarket = 'A_SHARE' | 'HK' | 'US' | 'TW' | 'JP' | 'KR' | 'EU' | 'GLOBAL';
export type ResearchAutoRefreshFreq = 'manual' | 'weekly' | 'monthly';
export type ResearchRunStatus = 'running' | 'completed' | 'failed';
export type ResearchEvidenceGrade = 'strong' | 'medium' | 'weak' | 'lead';

export interface ResearchTheme {
  id: number;
  name: string;
  description: string | null;
  market: string;
  status: string;
  auto_refresh_freq: string;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_error: string | null;
  parent_theme_id: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface ResearchThemeCreate {
  name: string;
  description?: string;
  market?: ResearchMarket;
  auto_refresh_freq?: ResearchAutoRefreshFreq;
  parent_theme_id?: number | null;
}

export interface ResearchThemeUpdate {
  name?: string;
  description?: string;
  market?: ResearchMarket;
  status?: 'active' | 'archived';
  auto_refresh_freq?: ResearchAutoRefreshFreq;
  parent_theme_id?: number | null;
}

export interface ValueChainLayer {
  id: number;
  layer_index: number;
  name: string;
  description: string | null;
}

export interface ScarceLayer {
  id: number;
  rank: number;
  layer_ref_id: number;
  layer_name?: string | null;
  scarcity_reason_md: string;
  expansion_difficulty: 'high' | 'medium' | 'low';
}

export interface ResearchCompanyUniverseRow {
  id: number;
  stock_code: string;
  classification: 'controls' | 'supplies' | 'benefits' | 'weak' | 'story';
  layer_ref_id: number | null;
  layer_name?: string | null;
  note: string | null;
}

export interface ResearchEvidenceRow {
  id: number;
  stock_code: string | null;
  source_type: string;
  source_url: string;
  source_title: string;
  published_at: string | null;
  grade: ResearchEvidenceGrade;
  summary_md: string;
}

export interface ResearchCompanyRankingRow {
  id: number;
  rank: number;
  stock_code: string;
  constrains_what: string;
  chain_position: string;
  rank_reason_md: string;
  evidence_summary_md: string;
  main_risk_md: string;
}

export interface ResearchRun {
  id: number;
  research_theme_id: number;
  status: ResearchRunStatus;
  scope_market: string;
  scope_time_window: string;
  triggered_by: 'manual' | 'scheduler';
  llm_provider: string;
  llm_token_input: number;
  llm_token_output: number;
  llm_search_count: number;
  attempt_count: number;
  system_change_md: string | null;
  failure_conditions_md: string | null;
  next_steps_md: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  value_chain_layers?: ValueChainLayer[];
  scarce_layers?: ScarceLayer[];
  company_universe?: ResearchCompanyUniverseRow[];
  evidence?: ResearchEvidenceRow[];
  company_ranking?: ResearchCompanyRankingRow[];
}

export interface ResearchRunSummary {
  id: number;
  research_theme_id: number;
  status: ResearchRunStatus;
  triggered_by: 'manual' | 'scheduler';
  llm_provider: string;
  llm_token_input: number;
  llm_token_output: number;
  llm_search_count: number;
  started_at: string;
  completed_at: string | null;
  company_count: number;
  evidence_count: number;
  ranking_count: number;
}

export interface ResearchExportResponse {
  exported_count: number;
  skipped_codes: string[];
  target: 'watchlist' | 'candidate';
  target_id: number | null;
}

export interface StockResearchAppearance {
  research_theme_id: number;
  research_theme_name: string;
  run_id: number;
  run_started_at: string;
  rank: number | null;
  classification: string | null;
  constrains_what: string | null;
  main_risk_md: string | null;
}

// ── Phase 2 #10: Run diff ───────────────────────────────────────────────

export interface ResearchRunDiffRef {
  id: number;
  started_at: string;
  status: ResearchRunStatus;
}

export interface ResearchClaimSnapshot {
  predicate: string;
  signal: string | null;
  outcome: string;
  stock_codes: string[];
  layer_index: number | null;
}

export interface ResearchRankingDiffItem {
  stock_code: string;
  name: string;
  rank_from: number | null;
  rank_to: number | null;
  delta: number | null;
  category: 'promoted' | 'demoted' | 'new_in' | 'dropped' | 'unchanged';
}

export interface ResearchRankingDiff {
  promoted: ResearchRankingDiffItem[];
  demoted: ResearchRankingDiffItem[];
  new_in: ResearchRankingDiffItem[];
  dropped: ResearchRankingDiffItem[];
  unchanged: ResearchRankingDiffItem[];
}

export interface ResearchClaimDiffItem {
  subject: string;
  claim_from: ResearchClaimSnapshot | null;
  claim_to: ResearchClaimSnapshot | null;
  signal_changed: boolean;
  category: 'new_risk' | 'resolved' | 'tightened' | 'loosened' | 'unchanged';
}

export interface ResearchClaimsDiff {
  new_risks: ResearchClaimDiffItem[];
  resolved: ResearchClaimDiffItem[];
  tightened: ResearchClaimDiffItem[];
  loosened: ResearchClaimDiffItem[];
  unchanged: ResearchClaimDiffItem[];
}

export interface ResearchScarceLayerDiffItem {
  layer_index: number;
  layer_name: string;
  rank_from: number | null;
  rank_to: number | null;
  category: 'entered' | 'exited' | 'reranked' | 'unchanged';
}

export interface ResearchScarceLayerDiff {
  entered: ResearchScarceLayerDiffItem[];
  exited: ResearchScarceLayerDiffItem[];
  reranked: ResearchScarceLayerDiffItem[];
  unchanged: ResearchScarceLayerDiffItem[];
}

export interface ResearchRunDiffSummary {
  ranking: { promoted: number; demoted: number; new_in: number; dropped: number; unchanged: number };
  claims: { new_risks: number; resolved: number; tightened: number; loosened: number; unchanged: number };
  scarce_layers: { entered: number; exited: number; reranked: number; unchanged: number };
}

export interface ResearchRunDiff {
  run_a: ResearchRunDiffRef;
  run_b: ResearchRunDiffRef;
  summary: ResearchRunDiffSummary;
  ranking_diff: ResearchRankingDiff;
  claims_diff: ResearchClaimsDiff | null;
  scarce_layers_diff: ResearchScarceLayerDiff;
  degradations: string[];
}

// ── Phase 2 #9 阶段 B v2: Research claim variables ─────────────────────

export type BreachWhen = 'lt' | 'gt';
export type ClaimVariableStatus = 'proposed' | 'active' | 'rejected';

export interface ResearchClaimVariable {
  id: number;
  research_claim_id: number;
  stock_code: string;
  variable_name: string;
  threshold_critical: number;
  breach_when: BreachWhen;
  unit: string | null;
  source: string;
  window_periods: number | null;
  status: ClaimVariableStatus;
  proposed_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  review_note: string | null;
  last_alerted_at: string | null;
}

export interface ClaimVariablesByStatus {
  proposed: ResearchClaimVariable[];
  active: ResearchClaimVariable[];
  rejected: ResearchClaimVariable[];
}

export interface ClaimVariableApproveRequest {
  threshold_critical?: number;
  breach_when?: BreachWhen;
  unit?: string;
  window_periods?: number;
  note?: string;
}

export interface ClaimVariablePatchRequest {
  threshold_critical?: number;
  breach_when?: BreachWhen;
  unit?: string;
  window_periods?: number;
  note?: string;
}

export interface ClaimVariablePatchResponse {
  id: number;
  status: ClaimVariableStatus;
  updated_fields: string[];
  before: Record<string, unknown>;
  after: ResearchClaimVariable;
}

export interface CockpitClaimVariablesPending {
  count: number;
  by_stock: { stock_code: string; count: number }[];
  last_proposal: {
    status: 'ok' | 'partial' | 'failed';
    run_id: number | null;
    at: string | null;
    summary: string;
  } | null;
}

// ── Phase 6 Metrics (Tier 1) ────────────────────────────────────────────────

export interface PipelineMetrics {
  period_days: number;
  pipelines: Record<string, {
    total: number;
    success: number;
    failed: number;
    running: number;
    other: number;
    success_rate_pct: number;
    avg_duration_ms: number;
  }>;
  overall: {
    total: number;
    success_rate_pct: number;
  };
}

export interface LLMMetrics {
  period_days: number;
  total_calls: number;
  total_cost_usd: number;
  total_tokens_in: number;
  total_tokens_out: number;
  avg_latency_ms: number;
  success_rate_pct: number;
  conflict_rate_pct: number;
  by_pipeline: Record<string, {
    calls: number;
    cost_usd: number;
    tokens_in: number;
    tokens_out: number;
    conflict_rate_pct: number;
  }>;
  monthly_cost: {
    month: string;
    total_usd: number;
    soft_warning_usd: number;
    hard_cap_usd: number;
    by_model: Record<string, number>;
    by_pipeline: Record<string, number>;
    call_count: number;
    over_soft: boolean;
    over_hard: boolean;
  };
}

export interface LLMTrend {
  labels: string[];
  cost_usd: number[];
  tokens_in: number[];
  tokens_out: number[];
  call_count: number[];
}
