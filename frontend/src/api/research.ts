/**
 * v2 Research API client — LLM Pipeline endpoints.
 *
 * Per decision 24 (REST + shared types): types mirror backend Pydantic schemas
 * in app/routers/research_v2.py. When OpenAPI codegen is wired up (Phase 8),
 * these types can be auto-generated.
 */

import { apiClient } from './client';

// ── Types ────────────────────────────────────────────────────────────────

export type GLMTier = 'sonnet' | 'opus' | 'haiku';
export type Recommendation = 'BUY' | 'HOLD' | 'PASS' | 'SELL' | 'TRIM';
export type EvidenceGrade = 'A' | 'B' | 'C';
export type ReportStatus = 'completed' | 'rejected' | 'conflict' | 'stale';
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
