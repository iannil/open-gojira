/**
 * API client — strategy-driven investment system.
 */

import axios from 'axios';

import type {
  ApiUsageResponse,
  AuditLogEntry,
  AvailableQuantity,
  BrokerFeeConfig,
  BrokerFeeConfigCreate,
  CashAdjustment,
  CashAdjustmentInput,
  CashBalance,
  CleanupPreview,
  CleanupResult,
  CockpitResponse,
  CorpAction,
  ListCorpActionsParams,
  ProcessPendingResult,
  SyncDividendsRequest,
  SyncDividendsResult,
  DataQualityResponse,
  DataStatusOverview,
  DeadLetterStatsResponse,
  DividendRecordResponse,
  DividendSummaryResponse,
  DraftResponse,
  HoldingResponse,
  JobExecutionResponse,
  KlineResponse,
  KlineSyncSummary,
  MarginTradingRecord,
  NorthFlowRecord,
  PipelineHealthResponse,
  PipelineRunDetail,
  PriceBand,
  QiuScoreInput,
  ResourceFlagsUpdate,
  SchedulerJobResponse,
  SchedulerJobUpdate,
  ShareholderRecord,
  StockPoolItem,
  StockResponse,
  StockSearchResult,
  SystemAlert,
  SystemAlertCategory,
  SystemAlertSeverity,
  SyncTaskStatus,
  SyncTriggerResponse,
  ThesisVariable,
  Trade,
  TradeCreateInput,
  TradeListResponse,
  UnresolvedCount,
  RevenueComposition,
  UniverseItem,
  FullUniverseResponse,
  UniverseCoverageStats,
  LLMMetrics,
  LLMTrend,
  PipelineMetrics,
  PortfolioSummary,
  TaskHealthResponse,
  TaskResponse,
  TaskRunDetailResponse,
  TaskRunResponse,
  TaskUpdate,
  TriggerTaskResponse,
} from './types';

import { installTracer } from '../observability/tracer';

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
});

installTracer(apiClient);

// ── Cockpit ───────────────────────────────────────────────────────────

export async function fetchCockpit(): Promise<CockpitResponse> {
  const res = await apiClient.get<CockpitResponse>('/cockpit');
  return res.data;
}

// ── Evaluation ─────────────────────────────────────────────────────────

export interface BenchmarkComparison {
  benchmark_code: string;
  benchmark_name: string;
  period_days: number;
  portfolio_return_pct: number | null;
  benchmark_return_pct: number | null;
  excess_return_pct: number | null;
  start_date: string;
  end_date: string;
}

export interface TradeStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  profit_factor: number;
}

export interface SignalQuality {
  total_executed: number;
  with_slippage_data: number;
  avg_slippage_pct: number;
  max_slippage_pct: number;
  by_side: Record<string, { count: number; avg_slippage_pct: number }>;
}

export interface EngineAttribution {
  quality_screen: { drafts: number; executed: number; total_value: number };
  theme_scan: { drafts: number; executed: number; total_value: number };
  unknown: { drafts: number; executed: number; total_value: number };
}

export interface PortfolioEvaluation {
  benchmark: BenchmarkComparison;
  trade_stats: TradeStats;
  sharpe_ratio: number | null;
  engine_attribution: EngineAttribution;
  signal_quality: SignalQuality;
}

export async function fetchEvaluation(): Promise<PortfolioEvaluation> {
  const res = await apiClient.get<PortfolioEvaluation>('/portfolio/evaluation');
  return res.data;
}

// ── Drafts ────────────────────────────────────────────────────────────

export async function listDrafts(params?: {
  status?: string;
  code?: string;
  limit?: number;
}): Promise<DraftResponse[]> {
  const res = await apiClient.get<DraftResponse[]>('/drafts', { params });
  return res.data;
}

export interface ExecuteDraftPayload {
  /** Actual fill price reported back after the broker order (P0-2). */
  price?: number;
  /** Actual filled quantity. */
  quantity?: number;
  /** Actual fill time (ISO); defaults to now when omitted. */
  filled_at?: string;
}

export async function executeDraft(
  draftId: number,
  payload?: ExecuteDraftPayload,
): Promise<DraftResponse> {
  const res = await apiClient.post<DraftResponse>(`/drafts/${draftId}/execute`, payload ?? {});
  return res.data;
}

export async function cancelDraft(draftId: number): Promise<DraftResponse> {
  const res = await apiClient.post<DraftResponse>(`/drafts/${draftId}/cancel`);
  return res.data;
}

export async function fetchAuditLog(params?: {
  entity_type?: string;
  entity_id?: string;
  event?: string;
  stock_code?: string;
  limit?: number;
}): Promise<AuditLogEntry[]> {
  const res = await apiClient.get<AuditLogEntry[]>('/audit-log', { params });
  return res.data;
}

// ── Theme Scan ────────────────────────────────────────────────────────

export interface ThemeScanSummary {
  id: number;
  theme: string;
  evidence_grade: string | null;
  status: string;
  created_at: string | null;
}

export interface ThemeScanFull extends ThemeScanSummary {
  system_change: string | null;
  ranked_layers: Array<Record<string, unknown>> | null;
  ranked_candidates: Array<Record<string, unknown>> | null;
  markdown_output: string | null;
  prompt_version: string | null;
}

export async function triggerThemeScan(payload: {
  theme: string;
  model_tier?: string;
  use_web_search?: boolean;
}): Promise<ThemeScanFull> {
  const res = await apiClient.post<ThemeScanFull>('/theme-scan', payload);
  return res.data;
}

export async function listThemeScanReports(limit = 20): Promise<ThemeScanSummary[]> {
  const res = await apiClient.get<ThemeScanSummary[]>('/theme-scan/reports', {
    params: { limit },
  });
  return res.data;
}

export async function getThemeScanReport(reportId: number): Promise<ThemeScanFull> {
  const res = await apiClient.get<ThemeScanFull>(`/theme-scan/${reportId}`);
  return res.data;
}

// ── Engine (双引擎选股) ───────────────────────────────────────────────

export interface LifecycleStockItem {
  stock_code: string;
  name: string | null;
  industry: string | null;
  current_state: string;
  entered_state_at: string | null;
  last_research_at: string | null;
}

export async function listLifecycleStocks(
  state?: string,
  limit = 200,
): Promise<LifecycleStockItem[]> {
  const res = await apiClient.get<LifecycleStockItem[]>('/stocks/lifecycle', {
    params: state ? { state, limit } : { limit },
  });
  return res.data;
}

export interface BatchResearchRequest {
  stock_codes: string[];
  source?: string;
  model_tier?: string;
  use_web_search?: boolean;
  scarcity_score?: number | null;
  failure_conditions?: string[] | null;
}

export interface BatchResearchResponse {
  triggered: string[];
  triggered_count: number;
  skipped: Array<{ code: string; reason: string }>;
  skipped_count: number;
}

export async function triggerBatchResearch(
  payload: BatchResearchRequest,
): Promise<BatchResearchResponse> {
  const res = await apiClient.post<BatchResearchResponse>('/research/batch', payload);
  return res.data;
}

// ── Stock detail ──────────────────────────────────────────────────────

export async function getStock(code: string): Promise<StockResponse> {
  const res = await apiClient.get<StockResponse>(`/stocks/${code}`);
  return res.data;
}

export async function listHoldings(): Promise<HoldingResponse[]> {
  const res = await apiClient.get<HoldingResponse[]>('/portfolio');
  return res.data;
}

export async function fetchPortfolioSummary(): Promise<PortfolioSummary> {
  const res = await apiClient.get<PortfolioSummary>('/portfolio/summary');
  return res.data;
}

export async function fetchShareholders(code: string): Promise<ShareholderRecord[]> {
  const res = await apiClient.get<ShareholderRecord[]>(`/stocks/${code}/shareholders`);
  return res.data;
}

export async function fetchNorthFlow(code: string): Promise<NorthFlowRecord[]> {
  const res = await apiClient.get<NorthFlowRecord[]>(`/stocks/${code}/north-flow`);
  return res.data;
}

export async function fetchMarginTrading(code: string): Promise<MarginTradingRecord[]> {
  const res = await apiClient.get<MarginTradingRecord[]>(`/stocks/${code}/margin-trading`);
  return res.data;
}

export async function fetchRevenueComposition(
  code: string,
  years = 5,
): Promise<RevenueComposition[]> {
  const res = await apiClient.get<RevenueComposition[]>(
    `/stocks/${code}/revenue-composition`,
    { params: { years } },
  );
  return res.data;
}

export async function fetchKline(
  code: string,
  days = 365,
  freq: 'day' | 'week' | 'month' = 'day',
): Promise<KlineResponse> {
  const res = await apiClient.get<KlineResponse>(`/stocks/${code}/kline`, {
    params: { days, freq },
  });
  return res.data;
}

// ── Thesis variables ──────────────────────────────────────────────────

export async function updateThesisVariables(
  code: string,
  variables: ThesisVariable[],
): Promise<StockResponse> {
  const res = await apiClient.put<StockResponse>(`/stocks/${code}/thesis-variables`, variables);
  return res.data;
}

export async function fetchThesisTemplates(code: string): Promise<{
  industry: string | null;
  templates: { name: string; unit: string; source: string }[];
}> {
  const res = await apiClient.get(`/stocks/${code}/thesis-templates`);
  return res.data;
}

export async function updateStockResourceFlags(
  code: string,
  flags: ResourceFlagsUpdate,
): Promise<StockResponse> {
  const res = await apiClient.patch<StockResponse>(
    `/stocks/${code}/resource-flags`,
    flags,
  );
  return res.data;
}

// ── Universe ──────────────────────────────────────────────────────────

export async function fetchUniverse(): Promise<UniverseItem[]> {
  const res = await apiClient.get<UniverseItem[]>('/stocks/universe');
  return res.data;
}

export async function fetchFullUniverse(params?: {
  page?: number;
  page_size?: number;
  pe_pct_max?: number;
  pb_pct_max?: number;
  dyr_min?: number;
  pe_ttm_min?: number;
  pe_ttm_max?: number;
  pb_min?: number;
  pb_max?: number;
  industry?: string;
  keyword?: string;
}): Promise<FullUniverseResponse> {
  const res = await apiClient.get<FullUniverseResponse>('/stocks/universe/full', { params });
  return res.data;
}

export async function fetchUniverseStats(): Promise<UniverseCoverageStats> {
  const res = await apiClient.get<UniverseCoverageStats>('/stocks/universe/stats');
  return res.data;
}

// ── Qiu Score ─────────────────────────────────────────────────────────

export async function updateQiuScore(
  code: string,
  payload: QiuScoreInput,
): Promise<StockResponse> {
  const res = await apiClient.put<StockResponse>(`/stocks/${code}/qiu-score`, payload);
  return res.data;
}

// ── Scheduler ──────────────────────────────────────────────────────────

export async function listSchedulerJobs(): Promise<SchedulerJobResponse[]> {
  const res = await apiClient.get<SchedulerJobResponse[]>('/scheduler/jobs');
  return res.data;
}

export async function updateSchedulerJob(
  jobId: string,
  payload: SchedulerJobUpdate,
): Promise<SchedulerJobResponse> {
  const res = await apiClient.put<SchedulerJobResponse>(`/scheduler/jobs/${jobId}`, payload);
  return res.data;
}

export async function triggerSchedulerJob(jobId: string): Promise<{
  job: string;
  started_at: string;
  finished_at: string;
  result: Record<string, unknown> | null;
  execution_id: number;
}> {
  const res = await apiClient.post(`/scheduler/jobs/${jobId}/run`);
  return res.data;
}

export async function listJobExecutions(
  jobId?: string,
  limit = 50,
): Promise<JobExecutionResponse[]> {
  const url = jobId
    ? `/scheduler/jobs/${jobId}/executions`
    : '/scheduler/executions';
  const res = await apiClient.get<JobExecutionResponse[]>(url, { params: { limit } });
  return res.data;
}

// ── Tasks ──────────────────────────────────────────────────────────────

export async function listTasks(): Promise<TaskResponse[]> {
  const res = await apiClient.get<TaskResponse[]>('/tasks');
  return res.data;
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  const res = await apiClient.get<TaskResponse>(`/tasks/${taskId}`);
  return res.data;
}

export async function updateTask(
  taskId: string,
  payload: TaskUpdate,
): Promise<TaskResponse> {
  const res = await apiClient.put<TaskResponse>(`/tasks/${taskId}`, payload);
  return res.data;
}

export async function triggerTask(taskId: string): Promise<TriggerTaskResponse> {
  const res = await apiClient.post<TriggerTaskResponse>(`/tasks/${taskId}/trigger`);
  return res.data;
}

export async function pauseTask(taskId: string): Promise<TaskResponse> {
  const res = await apiClient.post<TaskResponse>(`/tasks/${taskId}/pause`);
  return res.data;
}

export async function resumeTask(taskId: string): Promise<TaskResponse> {
  const res = await apiClient.post<TaskResponse>(`/tasks/${taskId}/resume`);
  return res.data;
}

export async function listTaskRuns(params?: {
  task_id?: string;
  status?: string;
  limit?: number;
}): Promise<TaskRunResponse[]> {
  const res = await apiClient.get<TaskRunResponse[]>('/tasks/runs/list', {
    params,
  });
  return res.data;
}

export async function getTaskRun(runId: number): Promise<TaskRunDetailResponse> {
  const res = await apiClient.get<TaskRunDetailResponse>(`/tasks/runs/${runId}`);
  return res.data;
}

export async function cancelTaskRun(runId: number): Promise<{ run_id: number; status: string }> {
  const res = await apiClient.post(`/tasks/runs/${runId}/cancel`);
  return res.data;
}

export async function retryTaskRun(runId: number): Promise<TriggerTaskResponse> {
  const res = await apiClient.post<TriggerTaskResponse>(`/tasks/runs/${runId}/retry`);
  return res.data;
}

export async function taskHealth(): Promise<TaskHealthResponse> {
  const res = await apiClient.get<TaskHealthResponse>('/tasks/health');
  return res.data;
}

// ── Sync Data Summaries ───────────────────────────────────────────────

export async function fetchKlineSyncSummary(): Promise<KlineSyncSummary[]> {
  const res = await apiClient.get<KlineSyncSummary[]>('/stocks/kline-summary');
  return res.data;
}

export async function fetchDividendSummary(): Promise<DividendSummaryResponse> {
  const res = await apiClient.get<DividendSummaryResponse>('/dividends/summary');
  return res.data;
}

export async function listDividendRecords(stockCode?: string): Promise<DividendRecordResponse[]> {
  const params = stockCode ? { stock_code: stockCode } : undefined;
  const res = await apiClient.get<DividendRecordResponse[]>('/dividends', { params });
  return res.data;
}

// ── Data Management ──────────────────────────────────────────────────────

export async function fetchStockPool(): Promise<StockPoolItem[]> {
  const res = await apiClient.get<StockPoolItem[]>('/data-management/universe');
  return res.data;
}

export async function searchStocks(keyword: string): Promise<StockSearchResult[]> {
  const res = await apiClient.post<StockSearchResult[]>('/data-management/universe/search', null, {
    params: { keyword },
  });
  return res.data;
}

export async function addToStockPool(stockCodes: string[]): Promise<{ added: number }> {
  const res = await apiClient.post<{ added: number }>('/data-management/universe/add', {
    stock_codes: stockCodes,
  });
  return res.data;
}

export async function removeFromStockPool(stockCodes: string[]): Promise<{ removed: number }> {
  const res = await apiClient.post<{ removed: number }>('/data-management/universe/batch-remove', {
    stock_codes: stockCodes,
  });
  return res.data;
}

export async function fetchDataStatus(): Promise<DataStatusOverview> {
  const res = await apiClient.get<DataStatusOverview>('/data-management/status');
  return res.data;
}

export async function triggerDataSync(
  dataType: string,
  stockCodes?: string[],
  years?: number,
): Promise<SyncTriggerResponse> {
  const res = await apiClient.post<SyncTriggerResponse>(`/data-management/sync/${dataType}`, {
    stock_codes: stockCodes ?? null,
    years: years ?? 5,
  });
  return res.data;
}

export async function fetchSyncTaskStatus(taskId: string): Promise<SyncTaskStatus> {
  const res = await apiClient.get<SyncTaskStatus>(`/data-management/sync/${taskId}/status`);
  return res.data;
}

export async function previewCleanup(
  dataType: string,
  params?: { before_date?: string; after_date?: string; stock_codes?: string[] },
): Promise<CleanupPreview> {
  const res = await apiClient.get<CleanupPreview>(`/data-management/cleanup/${dataType}/preview`, {
    params,
  });
  return res.data;
}

export async function executeCleanup(
  dataType: string,
  params?: { before_date?: string; after_date?: string; stock_codes?: string[] },
): Promise<CleanupResult> {
  const res = await apiClient.post<CleanupResult>(`/data-management/cleanup/${dataType}`, {
    stock_codes: params?.stock_codes ?? null,
    before_date: params?.before_date ?? null,
    after_date: params?.after_date ?? null,
  });
  return res.data;
}

// ── Pipeline ─────────────────────────────────────────────────────────────

export async function startPipelineRun(
  pipelineType: string,
  params?: { stock_codes?: string[]; force_full?: boolean; years?: number },
): Promise<{ run_id: string; pipeline_type: string; stock_count: number; status: string }> {
  const res = await apiClient.post(`/data-management/pipeline/${pipelineType}/start`, {
    stock_codes: params?.stock_codes ?? null,
    force_full: params?.force_full ?? false,
    years: params?.years ?? 5,
  });
  return res.data;
}

export async function listPipelineRuns(params?: {
  pipeline_type?: string;
  status?: string;
  limit?: number;
}): Promise<PipelineRunDetail[]> {
  const res = await apiClient.get<{ runs: PipelineRunDetail[] }>('/data-management/pipeline/runs', { params });
  return res.data.runs;
}

export async function getPipelineRun(runId: string): Promise<PipelineRunDetail> {
  const res = await apiClient.get<PipelineRunDetail>(`/data-management/pipeline/runs/${runId}`);
  return res.data;
}

export async function retryPipelineRun(runId: string): Promise<{ run_id: string; pipeline_type: string; stock_count: number; status: string }> {
  const res = await apiClient.post(`/data-management/pipeline/runs/${runId}/retry`);
  return res.data;
}

export async function cancelPipelineRun(runId: string): Promise<void> {
  await apiClient.post(`/data-management/pipeline/runs/${runId}/cancel`);
}

export async function fetchPipelineHealth(): Promise<PipelineHealthResponse> {
  const res = await apiClient.get<PipelineHealthResponse>('/data-management/health');
  return res.data;
}

export async function fetchApiUsage(): Promise<ApiUsageResponse> {
  const res = await apiClient.get<ApiUsageResponse>('/data-management/api-usage');
  return res.data;
}

export async function fetchDeadLetterStats(pipelineType?: string): Promise<DeadLetterStatsResponse> {
  const res = await apiClient.get<DeadLetterStatsResponse>('/data-management/dead-letters/stats', {
    params: pipelineType ? { pipeline_type: pipelineType } : undefined,
  });
  return res.data;
}

export async function fetchDataQuality(): Promise<DataQualityResponse> {
  const res = await apiClient.get<DataQualityResponse>('/data-management/quality');
  return res.data;
}

// ── Trades ────────────────────────────────────────────────────────────

export async function listTrades(params?: {
  code?: string;
  side?: string;
  source?: string;
  limit?: number;
  offset?: number;
}): Promise<TradeListResponse> {
  const res = await apiClient.get<TradeListResponse>('/trades', { params });
  return res.data;
}

export async function getTrade(id: number): Promise<Trade> {
  const res = await apiClient.get<Trade>(`/trades/${id}`);
  return res.data;
}

export async function createTrade(payload: TradeCreateInput): Promise<Trade> {
  const res = await apiClient.post<Trade>('/trades', payload);
  return res.data;
}

export async function reverseTrade(id: number): Promise<Trade> {
  const res = await apiClient.post<Trade>(`/trades/${id}/reverse`);
  return res.data;
}

// ── Cash ──────────────────────────────────────────────────────────────

export async function getCashBalance(): Promise<CashBalance> {
  const res = await apiClient.get<CashBalance>('/cash/balance');
  return res.data;
}

export async function listCashAdjustments(limit = 100): Promise<CashAdjustment[]> {
  const res = await apiClient.get<CashAdjustment[]>('/cash/adjustments', {
    params: { limit },
  });
  return res.data;
}

export async function createCashAdjustment(
  payload: CashAdjustmentInput,
): Promise<CashAdjustment> {
  const res = await apiClient.post<CashAdjustment>('/cash/adjustments', payload);
  return res.data;
}

// ── Broker fee configs ────────────────────────────────────────────────

export async function listFeeConfigs(brokerName?: string): Promise<BrokerFeeConfig[]> {
  const res = await apiClient.get<BrokerFeeConfig[]>('/fee-configs', {
    params: brokerName ? { broker_name: brokerName } : undefined,
  });
  return res.data;
}

export async function createFeeConfig(payload: BrokerFeeConfigCreate): Promise<BrokerFeeConfig> {
  const res = await apiClient.post<BrokerFeeConfig>('/fee-configs', payload);
  return res.data;
}

export async function updateFeeConfig(configId: number, payload: Partial<BrokerFeeConfigCreate>): Promise<BrokerFeeConfig> {
  const res = await apiClient.patch<BrokerFeeConfig>(`/fee-configs/${configId}`, payload);
  return res.data;
}

export async function deleteFeeConfig(configId: number): Promise<void> {
  await apiClient.delete(`/fee-configs/${configId}`);
}

// ── Market indices ─────────────────────────────────────────────────────

export interface MarketIndexItem {
  code: string;
  name: string;
  close: number | null;
  change_pct: number | null;
}

export async function fetchMarketIndices(): Promise<MarketIndexItem[]> {
  const res = await apiClient.get<MarketIndexItem[]>('/market/indices');
  return res.data;
}

export async function fetchIndexKline(code: string, days = 365): Promise<{
  stock_code: string;
  points: Array<{ date: string; open: number | null; high: number | null; low: number | null; close: number | null; volume: number | null }>;
}> {
  const res = await apiClient.get(`/market/index/${code}/kline`, { params: { days } });
  return res.data;
}

// ── Valuation ──────────────────────────────────────────────────────────

export interface ValuationSnapshotItem {
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

export interface ValuationDashboardData {
  stock_code: string;
  latest_snapshot: ValuationSnapshotItem | null;
  snapshots: ValuationSnapshotItem[];
  current_pe: number | null;
  current_pb: number | null;
  current_price: number | null;
  dividend_yield: number | null;
  market_cap: number | null;
}

export async function fetchValuationDashboard(code: string): Promise<ValuationDashboardData> {
  const res = await apiClient.get<ValuationDashboardData>(`/valuation/${code}/dashboard`);
  return res.data;
}

export async function fetchValuationPercentile(code: string, years = 10): Promise<{
  pe_bands: Array<{ percentile: number; value: number }>;
  pb_bands: Array<{ percentile: number; value: number }>;
  current_pe: number | null;
  current_pb: number | null;
  current_pe_percentile: number | null;
  current_pb_percentile: number | null;
}> {
  const res = await apiClient.get(`/valuation/${code}/percentile`, { params: { years } });
  return res.data;
}

export async function fetchForwardDyr(code: string): Promise<{
  stock_code: string;
  forward_dyr: number | null;
  payout_ratio_avg_3y: number | null;
  eps: number | null;
  current_price: number | null;
  trailing_dyr: number | null;
  basis_note: string;
}> {
  const res = await apiClient.get(`/valuation/${code}/forward-dyr`);
  return res.data;
}

// ── Price band / available quantity (S2 UI validation) ────────────────

export async function getPriceBand(code: string): Promise<PriceBand> {
  const res = await apiClient.get<PriceBand>(`/stocks/${code}/price-band`);
  return res.data;
}

export async function getAvailableQuantity(code: string): Promise<AvailableQuantity> {
  const res = await apiClient.get<AvailableQuantity>(`/portfolio/${code}/available`);
  return res.data;
}

// ── System alerts (S3 infra-level alerts) ──────────────────────────────

export async function listSystemAlerts(params?: {
  severity?: SystemAlertSeverity;
  category?: SystemAlertCategory;
  unresolved_only?: boolean;
  limit?: number;
}): Promise<SystemAlert[]> {
  const res = await apiClient.get<SystemAlert[]>('/system-alerts', { params });
  return res.data;
}

export async function getUnresolvedCriticalCount(): Promise<number> {
  const res = await apiClient.get<UnresolvedCount>('/system-alerts/unresolved-count');
  return res.data.count;
}

export async function resolveSystemAlert(
  id: number,
  resolvedBy = 'manual',
): Promise<SystemAlert> {
  const res = await apiClient.post<SystemAlert>(
    `/system-alerts/${id}/resolve`,
    { resolved_by: resolvedBy },
  );
  return res.data;
}

// ── Corporate actions (S4A.4) ─────────────────────────────────────────

export async function listCorpActions(
  params?: ListCorpActionsParams,
): Promise<CorpAction[]> {
  const res = await apiClient.get<CorpAction[]>('/corp-actions', { params });
  return res.data;
}

export async function listPendingCorpActions(
  limit = 100,
): Promise<CorpAction[]> {
  const res = await apiClient.get<CorpAction[]>('/corp-actions/pending', {
    params: { limit },
  });
  return res.data;
}

export async function getCorpAction(id: number): Promise<CorpAction> {
  const res = await apiClient.get<CorpAction>(`/corp-actions/${id}`);
  return res.data;
}

export async function processCorpAction(id: number): Promise<CorpAction> {
  const res = await apiClient.post<CorpAction>(`/corp-actions/${id}/process`);
  return res.data;
}

export async function processPendingCorpActions(): Promise<ProcessPendingResult> {
  const res = await apiClient.post<ProcessPendingResult>(
    '/corp-actions/process-pending',
  );
  return res.data;
}

export async function syncDividends(
  payload: SyncDividendsRequest,
): Promise<SyncDividendsResult> {
  const res = await apiClient.post<SyncDividendsResult>(
    '/corp-actions/sync-dividends',
    payload,
  );
  return res.data;
}

// ── Phase 6 Metrics (Tier 1) ────────────────────────────────────────────────

export async function fetchPipelineMetrics(days = 30): Promise<PipelineMetrics> {
  const res = await apiClient.get<PipelineMetrics>(`/metrics/pipelines?days=${days}`);
  return res.data;
}

export async function fetchLLMMetrics(days = 30): Promise<LLMMetrics> {
  const res = await apiClient.get<LLMMetrics>(`/metrics/llm?days=${days}`);
  return res.data;
}

export async function fetchLLMTrend(days = 30): Promise<LLMTrend> {
  const res = await apiClient.get<LLMTrend>(`/metrics/llm/trend?days=${days}`);
  return res.data;
}
