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

// ── Autopilot ─────────────────────────────────────────────────────────

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
  kind: 'profit_pct_ge' | 'dyr_le' | 'pe_pct_ge';
  value: number;
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
}

export interface PlanUpdate {
  name?: string;
  description?: string;
  status?: PlanStatus;
  strategy_composition?: StrategyComposition;
  scan_scope?: ScanScope;
  schedule_cron?: string;
  trading_rules?: TradingRules | null;
}

export interface DraftResponse {
  id: number;
  plan_id: number;
  code: string;
  side: 'BUY' | 'SELL';
  status: 'pending' | 'executed' | 'cancelled';
  step_kind: string;
  step_index: number;
  add_pct: number | null;
  reduce_pct_of_position: number | null;
  reason: string;
  source: string;
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

export interface CockpitPlanSummary {
  id: number;
  slug: string;
  name: string;
  status: PlanStatus;
  description: string;
  is_builtin: boolean;
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

export interface CockpitResponse {
  as_of: string;
  cashflow: CockpitCashflow;
  drafts: CockpitDraft[];
  holdings: {
    items: CockpitHoldingItem[];
    warnings: string[];
    summary?: string | null;
  };
  quadrant: CockpitQuadrant[];
  alerts: {
    items: CockpitAlertItem[];
    unacked_count: number;
  };
  plans: CockpitPlanSummary[];
  errors: string[];
  market_temperature?: number | null;
  rebalance_suggestions?: RebalanceSuggestion[];
  cycle?: CycleAssessment;
  theme_exposure?: ThemeExposure[];
  dividend_projection?: DividendProjection;
  thesis_alerts?: ThesisAlert[];
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

// ── Sync Data Summaries ───────────────────────────────────────────────

export interface KlineSyncSummary {
  stock_code: string;
  stock_name: string;
  earliest_date: string | null;
  latest_date: string | null;
  total_bars: number;
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
  status: 'active' | 'removed';
  first_seen_at: string | null;
  last_confirmed_at: string | null;
  last_eval: Record<string, { passed: boolean; details: string[] }> | null;
  pinned: boolean;
  notes: string | null;
}

// ── Data Management ──────────────────────────────────────────────────────

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
