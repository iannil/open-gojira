/**
 * v2 Research API client — LLM Pipeline endpoints.
 *
 * Per decision 24 (REST + shared types): types mirror backend Pydantic schemas
 * in app/routers/research_v2.py. When OpenAPI codegen is wired up (Phase 8),
 * these types can be auto-generated.
 *
 * Unified file: contains both v2 research pipeline functions and
 * serenity theme/run/claim-variable functions (moved from client.ts).
 */

import { apiClient } from './client';

// ── Types (serenity + v2) ──────────────────────────────────────────────

import type {
  ClaimVariableApproveRequest,
  ClaimVariablePatchRequest,
  ClaimVariablePatchResponse,
  ClaimVariablesByStatus,
  CockpitClaimVariablesPending,
  ResearchClaimVariable,
  ResearchExportResponse,
  ResearchRun,
  ResearchRunDiff,
  ResearchRunSummary,
  ResearchTheme,
  ResearchThemeCreate,
  ResearchThemeUpdate,
  StockResearchAppearance,
} from './types';

export type GLMTier = 'sonnet' | 'opus' | 'haiku';
export type Recommendation = 'BUY' | 'HOLD' | 'PASS' | 'SELL' | 'TRIM';
export type EvidenceGrade = 'A' | 'B' | 'C';
export type ReportStatus =
  | 'running'
  | 'completed'
  | 'rejected'
  | 'conflict'
  | 'stale'
  | 'failed';

// Statuses that mean the report is final (no longer running).
export const TERMINAL_STATUSES: ReadonlySet<ReportStatus> = new Set([
  'completed',
  'rejected',
  'conflict',
  'stale',
  'failed',
]);
export type PipelineType =
  | 'deep_research'
  | 'thesis_tracker'
  | 'news_pulse'
  | 'earnings_review'
  | 'quality_screen';

export interface ResearchTriggerRequest {
  force?: boolean;
  model_tier?: GLMTier;
  use_web_search?: boolean;
}

export interface ResearchReportSummary {
  id: number;
  stock_code: string;
  stock_name: string | null;
  pipeline_type: PipelineType;
  overall_score: number | null;
  recommendation: Recommendation | null;
  evidence_grade: EvidenceGrade | null;
  status: ReportStatus;
  created_at: string | null;
  expires_at: string | null;
}

export interface ResearchReportFull extends ResearchReportSummary {
  markdown_output: string | null;
  data_conflict: Array<{
    field: string;
    llm_value?: number | string;
    db_value?: number | string;
    diff_pct?: number;
    source?: string;
  }> | null;
  red_line_hit: Array<{
    red_line_type: string;
    severity: string;
    evidence?: Record<string, unknown>;
    action_taken?: string;
  }> | null;
  prompt_version: string | null;
}

export interface MonthlySpend {
  month: string;
  total_usd: number;
  soft_warning_usd: number;
  hard_cap_usd: number;
  by_model: Record<string, number>;
  by_pipeline: Record<string, number>;
  call_count: number;
  over_soft: boolean;
  over_hard: boolean;
}

export interface LifecycleCounts {
  candidate: number;
  exited: number;
  holding: number;
  researched: number;
  signaled: number;
  universe: number;
  watchlist: number;
}

export interface ResearchHealth {
  spend: MonthlySpend;
  lifecycle_counts: LifecycleCounts;
}

// ── API functions ────────────────────────────────────────────────────────

export async function triggerResearch(
  stockCode: string,
  payload: ResearchTriggerRequest = {},
): Promise<ResearchReportFull> {
  const res = await apiClient.post<ResearchReportFull>(
    `/research/${stockCode}`,
    payload,
  );
  return res.data;
}

export async function getLatestReport(
  stockCode: string,
): Promise<ResearchReportFull | null> {
  const res = await apiClient.get<ResearchReportFull | null>(
    `/research/${stockCode}/latest`,
  );
  return res.data;
}

export async function getReportHistory(
  stockCode: string,
  limit = 20,
): Promise<ResearchReportSummary[]> {
  const res = await apiClient.get<ResearchReportSummary[]>(
    `/research/${stockCode}/history`,
    { params: { limit } },
  );
  return res.data;
}

export async function listRecentReports(
  pipelineType?: PipelineType,
  limit = 50,
): Promise<ResearchReportSummary[]> {
  const res = await apiClient.get<ResearchReportSummary[]>(`/research/reports`, {
    params: pipelineType ? { pipeline_type: pipelineType, limit } : { limit },
  });
  return res.data;
}

export async function getResearchHealth(): Promise<ResearchHealth> {
  const res = await apiClient.get<ResearchHealth>(`/research/health`);
  return res.data;
}

// ── Serenity: Themes ─────────────────────────────────────────────────────

export async function listResearchThemes(status?: string): Promise<ResearchTheme[]> {
  const params = status ? { status } : {};
  const res = await apiClient.get<ResearchTheme[]>('/research/themes', { params });
  return res.data;
}

export async function createResearchTheme(payload: ResearchThemeCreate): Promise<ResearchTheme> {
  const res = await apiClient.post<ResearchTheme>('/research/themes', payload);
  return res.data;
}

export async function getResearchTheme(themeId: number): Promise<ResearchTheme> {
  const res = await apiClient.get<ResearchTheme>(`/research/themes/${themeId}`);
  return res.data;
}

export async function updateResearchTheme(
  themeId: number,
  payload: ResearchThemeUpdate,
): Promise<ResearchTheme> {
  const res = await apiClient.put<ResearchTheme>(`/research/themes/${themeId}`, payload);
  return res.data;
}

export async function archiveResearchTheme(themeId: number): Promise<void> {
  await apiClient.delete(`/research/themes/${themeId}`);
}

// ── Serenity: Runs ───────────────────────────────────────────────────────

export async function triggerResearchRun(
  themeId: number,
  payload?: { market?: string; time_window?: string },
): Promise<ResearchRunSummary> {
  const res = await apiClient.post<ResearchRunSummary>(
    `/research/themes/${themeId}/run`,
    payload ?? {},
  );
  return res.data;
}

export async function listResearchRuns(themeId: number, limit = 20): Promise<ResearchRunSummary[]> {
  const res = await apiClient.get<ResearchRunSummary[]>(
    `/research/themes/${themeId}/runs`,
    { params: { limit } },
  );
  return res.data;
}

export async function getResearchRun(runId: number): Promise<ResearchRun> {
  const res = await apiClient.get<ResearchRun>(`/research/runs/${runId}`);
  return res.data;
}

export async function exportResearchRun(
  runId: number,
  payload: { target: 'watchlist'; rank_max?: number; watchlist_group_id: number },
): Promise<ResearchExportResponse> {
  const res = await apiClient.post<ResearchExportResponse>(
    `/research/runs/${runId}/export`,
    payload,
  );
  return res.data;
}

export async function getResearchRunDiff(
  runA: number,
  runB: number,
): Promise<ResearchRunDiff> {
  const res = await apiClient.get<ResearchRunDiff>(
    `/research/runs/diff`,
    { params: { run_a: runA, run_b: runB } },
  );
  return res.data;
}

export async function listResearchAppearances(stockCode: string): Promise<StockResearchAppearance[]> {
  const res = await apiClient.get<StockResearchAppearance[]>(
    `/research/appearances/${stockCode}`,
  );
  return res.data;
}

// ── Claim Variables ──────────────────────────────────────────────────────

export async function listClaimVariables(
  stockCode?: string,
): Promise<ClaimVariablesByStatus> {
  const res = await apiClient.get<ClaimVariablesByStatus>(
    `/research/claim-variables`,
    { params: stockCode ? { stock_code: stockCode } : {} },
  );
  return res.data;
}

export async function approveClaimVariable(
  id: number,
  payload: ClaimVariableApproveRequest,
): Promise<ResearchClaimVariable> {
  const res = await apiClient.post<ResearchClaimVariable>(
    `/research/claim-variables/${id}/approve`,
    payload,
  );
  return res.data;
}

export async function rejectClaimVariable(
  id: number,
  note?: string,
): Promise<ResearchClaimVariable> {
  const res = await apiClient.post<ResearchClaimVariable>(
    `/research/claim-variables/${id}/reject`,
    { note },
  );
  return res.data;
}

export async function patchClaimVariable(
  id: number,
  payload: ClaimVariablePatchRequest,
): Promise<ClaimVariablePatchResponse> {
  const res = await apiClient.patch<ClaimVariablePatchResponse>(
    `/research/claim-variables/${id}`,
    payload,
  );
  return res.data;
}

export async function getCockpitClaimVariablesPending(): Promise<CockpitClaimVariablesPending> {
  const res = await apiClient.get<CockpitClaimVariablesPending>(
    `/cockpit/claim-variables-pending`,
  );
  return res.data;
}
