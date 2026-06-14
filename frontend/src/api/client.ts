/**
 * API client — strategy-driven investment system.
 */

import axios from 'axios';

import type {
  AnnualReview,
  ApiUsageResponse,
  AuditLogEntry,
  AvailableQuantity,
  BacktestConfig,
  BacktestRun,
  BrokerFeeConfig,
  CandidateResponse,
  CashAdjustment,
  CashAdjustmentInput,
  CashBalance,
  CashflowGoalResponse,
  CashflowGoalUpdate,
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
  DividendSummaryResponse,
  DraftResponse,
  HoldingResponse,
  HoldingRiskRule,
  JobExecutionResponse,
  KlineResponse,
  KlineSyncSummary,
  MarginTradingRecord,
  NorthFlowRecord,
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelUpdate,
  NotificationTestResult,
  PipelineHealthResponse,
  PipelineRunDetail,
  PlanCreate,
  PlanResponse,
  PlanUpdate,
  PriceBand,
  QuarterlyReview,
  QiuScoreInput,
  ReviewResponse,
  RiskRuleCreate,
  RiskRuleUpdate,
  SchedulerJobResponse,
  SchedulerJobUpdate,
  ShareholderRecord,
  StockPoolItem,
  StockResponse,
  StockSearchResult,
  SystemAlert,
  SystemAlertCategory,
  SystemAlertSeverity,
  StrategyCreate,
  StrategyResponse,
  StrategyTestResponse,
  StrategyUpdate,
  SyncTaskStatus,
  SyncTriggerResponse,
  ThemeExposure,
  ThemeItem,
  ThesisVariable,
  Trade,
  TradeCreateInput,
  TradeListResponse,
  UnresolvedCount,
  RevenueComposition,
  UniverseItem,
  FullUniverseResponse,
  UniverseCoverageStats,
  WatchlistGroupResponse,
  BusinessPattern,
  BusinessPatternCreate,
  BusinessPatternUpdate,
  BusinessPatternThesisTemplates,
  InferAllSummary,
} from './types';

import { installTracer } from '../observability/tracer';

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
});

installTracer(apiClient);

// ── Strategies ────────────────────────────────────────────────────────

export async function listStrategies(): Promise<StrategyResponse[]> {
  const res = await apiClient.get<StrategyResponse[]>('/strategies');
  return res.data;
}

export async function createStrategy(payload: StrategyCreate): Promise<StrategyResponse> {
  const res = await apiClient.post<StrategyResponse>('/strategies', payload);
  return res.data;
}

export async function updateStrategy(id: number, payload: StrategyUpdate): Promise<StrategyResponse> {
  const res = await apiClient.put<StrategyResponse>(`/strategies/${id}`, payload);
  return res.data;
}

export async function deleteStrategy(id: number): Promise<void> {
  await apiClient.delete(`/strategies/${id}`);
}

export async function testStrategy(id: number, stockCode: string): Promise<StrategyTestResponse> {
  const res = await apiClient.post(`/strategies/${id}/test`, { stock_code: stockCode });
  return res.data;
}

// ── Plans ─────────────────────────────────────────────────────────────

export async function listPlans(): Promise<PlanResponse[]> {
  const res = await apiClient.get<PlanResponse[]>('/plans');
  return res.data;
}

export async function getPlan(id: number): Promise<PlanResponse> {
  const res = await apiClient.get<PlanResponse>(`/plans/${id}`);
  return res.data;
}

export async function createPlan(payload: PlanCreate): Promise<PlanResponse> {
  const res = await apiClient.post<PlanResponse>('/plans', payload);
  return res.data;
}

export async function updatePlan(id: number, payload: PlanUpdate): Promise<PlanResponse> {
  const res = await apiClient.put<PlanResponse>(`/plans/${id}`, payload);
  return res.data;
}

export async function deletePlan(id: number): Promise<void> {
  await apiClient.delete(`/plans/${id}`);
}

export async function runPlan(id: number): Promise<unknown> {
  const res = await apiClient.post(`/plans/${id}/run`);
  return res.data;
}

// ── Candidates ────────────────────────────────────────────────────────

export async function listCandidates(params?: {
  plan_id?: number;
  status?: string;
}): Promise<CandidateResponse[]> {
  const res = await apiClient.get<CandidateResponse[]>('/candidates', { params });
  return res.data;
}

export async function updateCandidate(id: number, payload: {
  pinned?: boolean;
  notes?: string;
}): Promise<CandidateResponse> {
  const res = await apiClient.put<CandidateResponse>(`/candidates/${id}`, payload);
  return res.data;
}

export async function removeCandidate(id: number): Promise<void> {
  await apiClient.delete(`/candidates/${id}`);
}

// ── Cockpit ───────────────────────────────────────────────────────────

export async function fetchCockpit(): Promise<CockpitResponse> {
  const res = await apiClient.get<CockpitResponse>('/cockpit');
  return res.data;
}

export async function fetchCashflowGoal(): Promise<CashflowGoalResponse> {
  const res = await apiClient.get<CashflowGoalResponse>('/cashflow-goal');
  return res.data;
}

export async function updateCashflowGoal(
  payload: CashflowGoalUpdate,
): Promise<CashflowGoalResponse> {
  const res = await apiClient.put<CashflowGoalResponse>('/cashflow-goal', payload);
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
  holding_id?: number;
  discipline_checklist?: Record<string, boolean>;
  buy_price?: number;
  quantity?: number;
}

export async function executeDraft(
  draftId: number,
  payloadOrChecklist?: ExecuteDraftPayload | Record<string, boolean> | number,
): Promise<DraftResponse> {
  let body: Record<string, unknown> = {};
  if (typeof payloadOrChecklist === 'number') {
    body.holding_id = payloadOrChecklist;
  } else if (
    payloadOrChecklist &&
    typeof payloadOrChecklist === 'object' &&
    ('buy_price' in payloadOrChecklist || 'quantity' in payloadOrChecklist || 'holding_id' in payloadOrChecklist || 'discipline_checklist' in payloadOrChecklist)
  ) {
    body = { ...payloadOrChecklist };
  } else if (payloadOrChecklist && typeof payloadOrChecklist === 'object') {
    body.discipline_checklist = payloadOrChecklist;
  }
  const res = await apiClient.post<DraftResponse>(`/drafts/${draftId}/execute`, body);
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

export async function fetchMonthlyReview(params?: {
  month?: string;
  entry_limit?: number;
}): Promise<ReviewResponse> {
  const res = await apiClient.get<ReviewResponse>('/review', { params });
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

export async function listWatchlistGroups(): Promise<WatchlistGroupResponse[]> {
  const res = await apiClient.get<WatchlistGroupResponse[]>('/watchlist/groups');
  return res.data;
}

export async function bulkAddWatchlistItems(groupId: number, codes: string[]): Promise<void> {
  await apiClient.post(`/watchlist/groups/${groupId}/items/bulk`, {
    group_id: groupId,
    stock_codes: codes,
  });
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

// ── Themes ────────────────────────────────────────────────────────────

export async function listThemes(): Promise<ThemeItem[]> {
  const res = await apiClient.get<ThemeItem[]>('/themes');
  return res.data;
}

export async function getThemeExposure(): Promise<ThemeExposure> {
  const res = await apiClient.get<ThemeExposure>('/themes/exposure/analysis');
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

// ── Business patterns (生意模式) ─────────────────────────────────────

export async function listBusinessPatterns(
  builtinOnly = false,
): Promise<BusinessPattern[]> {
  const res = await apiClient.get<BusinessPattern[]>('/business-patterns', {
    params: builtinOnly ? { builtin_only: true } : undefined,
  });
  return res.data;
}

export async function createBusinessPattern(
  payload: BusinessPatternCreate,
): Promise<BusinessPattern> {
  const res = await apiClient.post<BusinessPattern>('/business-patterns', payload);
  return res.data;
}

export async function getBusinessPattern(id: number): Promise<BusinessPattern> {
  const res = await apiClient.get<BusinessPattern>(`/business-patterns/${id}`);
  return res.data;
}

export async function updateBusinessPattern(
  id: number,
  payload: BusinessPatternUpdate,
): Promise<BusinessPattern> {
  const res = await apiClient.patch<BusinessPattern>(`/business-patterns/${id}`, payload);
  return res.data;
}

export async function deleteBusinessPattern(id: number): Promise<void> {
  await apiClient.delete(`/business-patterns/${id}`);
}

export async function inferAllBusinessPatterns(force = false): Promise<InferAllSummary> {
  const res = await apiClient.post<InferAllSummary>('/business-patterns/infer-all', null, {
    params: force ? { force: true } : undefined,
  });
  return res.data;
}

export async function getBusinessPatternThesisTemplates(
  patternId: number,
): Promise<BusinessPatternThesisTemplates> {
  const res = await apiClient.get<BusinessPatternThesisTemplates>(
    `/business-patterns/${patternId}/thesis-templates`,
  );
  return res.data;
}

export async function updateStockBusinessPattern(
  code: string,
  patternId: number | null,
): Promise<StockResponse> {
  const res = await apiClient.patch<StockResponse>(
    `/stocks/${code}/business-pattern`,
    { business_pattern_id: patternId },
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

// ── Periodic Review ───────────────────────────────────────────────────

export async function fetchQuarterlyReview(year: number, q: number): Promise<QuarterlyReview> {
  const res = await apiClient.get<QuarterlyReview>('/review/quarterly', { params: { year, q } });
  return res.data;
}

export async function fetchAnnualReview(year: number): Promise<AnnualReview> {
  const res = await apiClient.get<AnnualReview>('/review/annual', { params: { year } });
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

// ── Sync Data Summaries ───────────────────────────────────────────────

export async function fetchKlineSyncSummary(): Promise<KlineSyncSummary[]> {
  const res = await apiClient.get<KlineSyncSummary[]>('/stocks/kline-summary');
  return res.data;
}

export async function fetchDividendSummary(): Promise<DividendSummaryResponse> {
  const res = await apiClient.get<DividendSummaryResponse>('/dividends/summary');
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

// ── Backtests (S4D) ───────────────────────────────────────────────────

export async function submitBacktest(config: BacktestConfig): Promise<BacktestRun> {
  const res = await apiClient.post<BacktestRun>('/backtests', config);
  return res.data;
}

export async function listBacktests(limit = 20): Promise<BacktestRun[]> {
  const res = await apiClient.get<BacktestRun[]>('/backtests', { params: { limit } });
  return res.data;
}

export async function getBacktest(id: number): Promise<BacktestRun> {
  const res = await apiClient.get<BacktestRun>(`/backtests/${id}`);
  return res.data;
}

// ── Notifications (S5.4) ──────────────────────────────────────────────

export async function listNotificationChannels(
  enabledOnly = false,
): Promise<NotificationChannel[]> {
  const res = await apiClient.get<NotificationChannel[]>('/notifications/channels', {
    params: enabledOnly ? { enabled_only: true } : undefined,
  });
  return res.data;
}

export async function createNotificationChannel(
  payload: NotificationChannelCreate,
): Promise<NotificationChannel> {
  const res = await apiClient.post<NotificationChannel>('/notifications/channels', payload);
  return res.data;
}

export async function updateNotificationChannel(
  id: number,
  payload: NotificationChannelUpdate,
): Promise<NotificationChannel> {
  const res = await apiClient.patch<NotificationChannel>(
    `/notifications/channels/${id}`,
    payload,
  );
  return res.data;
}

export async function deleteNotificationChannel(id: number): Promise<void> {
  await apiClient.delete(`/notifications/channels/${id}`);
}

export async function testNotificationChannel(id: number): Promise<NotificationTestResult> {
  const res = await apiClient.post<NotificationTestResult>(`/notifications/test/${id}`);
  return res.data;
}

// ── Holding risk rules (S5.4) ─────────────────────────────────────────

export async function listRiskRules(): Promise<HoldingRiskRule[]> {
  const res = await apiClient.get<HoldingRiskRule[]>('/risk-rules');
  return res.data;
}

export async function getRiskRule(
  stockCode: string,
): Promise<HoldingRiskRule | null> {
  const res = await apiClient.get<HoldingRiskRule | null>(`/risk-rules/${stockCode}`);
  return res.data;
}

export async function createRiskRule(payload: RiskRuleCreate): Promise<HoldingRiskRule> {
  const res = await apiClient.post<HoldingRiskRule>('/risk-rules', payload);
  return res.data;
}

export async function updateRiskRule(
  id: number,
  payload: RiskRuleUpdate,
): Promise<HoldingRiskRule> {
  const res = await apiClient.patch<HoldingRiskRule>(`/risk-rules/${id}`, payload);
  return res.data;
}

export async function deleteRiskRule(id: number): Promise<void> {
  await apiClient.delete(`/risk-rules/${id}`);
}
