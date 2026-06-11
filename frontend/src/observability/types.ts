export type ObservabilityEvent =
  | 'API_Request'
  | 'API_Response'
  | 'API_Error'
  | 'Component_Mount'
  | 'Component_Unmount'
  | 'User_Action';

export interface TraceLog {
  ts: string;
  trace_id: string;
  span_id: string;
  parent_span_id?: string;
  source: 'frontend';
  event: ObservabilityEvent;
  [key: string]: unknown;
}

export interface APIRequestLog extends TraceLog {
  event: 'API_Request';
  method: string;
  url: string;
  params?: Record<string, unknown>;
  request_body?: unknown;
}

export interface APIResponseLog extends TraceLog {
  event: 'API_Response';
  method: string;
  url: string;
  status: number;
  duration_ms: number;
  response_summary?: string;
}

export interface APIErrorLog extends TraceLog {
  event: 'API_Error';
  method: string;
  url: string;
  error_type: string;
  error_message: string;
  stack?: string;
  duration_ms: number;
}
