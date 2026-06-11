import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';
import { generateId, observeLog } from './logger';
import safeSerialize, { summarizeResponse } from './serializer';

export function installTracer(client: AxiosInstance): void {
  const pending = new Map<string, { start: number; traceId: string; spanId: string }>();

  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const traceId = config.headers?.['X-Request-ID'] as string || generateId();
      const spanId = generateId();
      const start = performance.now();

      pending.set(spanId, { start, traceId, spanId });

      if (config.headers) {
        config.headers['X-Request-ID'] = traceId;
      }

      observeLog({
        trace_id: traceId,
        span_id: spanId,
        event: 'API_Request',
        method: (config.method || 'GET').toUpperCase(),
        url: config.url || '',
        params: safeSerialize(config.params),
        request_body: config.data ? safeSerialize(config.data) : undefined,
      });

      return config;
    },
    (error: unknown) => Promise.reject(error),
  );

  client.interceptors.response.use(
    (response: AxiosResponse) => {
      const spanId = _findSpanId(response.config);
      const pendingEntry = spanId ? pending.get(spanId) : undefined;
      const duration = pendingEntry ? performance.now() - pendingEntry.start : 0;
      const traceId = pendingEntry?.traceId || '';
      const resolvedSpanId = pendingEntry?.spanId || generateId();

      observeLog({
        trace_id: traceId,
        span_id: resolvedSpanId,
        event: 'API_Response',
        method: (response.config.method || 'GET').toUpperCase(),
        url: response.config.url || '',
        status: response.status,
        duration_ms: Math.round(duration * 100) / 100,
        response_summary: summarizeResponse(response.data),
      });

      if (spanId) pending.delete(spanId);
      return response;
    },
    (error: AxiosError) => {
      const spanId = _findSpanId(error.config);
      const pendingEntry = spanId ? pending.get(spanId) : undefined;
      const duration = pendingEntry ? performance.now() - pendingEntry.start : 0;
      const traceId = pendingEntry?.traceId || '';
      const resolvedSpanId = pendingEntry?.spanId || generateId();

      observeLog({
        trace_id: traceId,
        span_id: resolvedSpanId,
        event: 'API_Error',
        method: (error.config?.method || 'GET').toUpperCase(),
        url: error.config?.url || '',
        error_type: error.code || error.name || 'Unknown',
        error_message: error.message,
        stack: error.stack,
        duration_ms: Math.round(duration * 100) / 100,
      });

      if (spanId) pending.delete(spanId);
      return Promise.reject(error);
    },
  );
}

function _findSpanId(config: InternalAxiosRequestConfig | undefined): string | undefined {
  if (!config?.headers) return undefined;
  const traceId = (config.headers as Record<string, string>)['X-Request-ID'];
  return traceId ? `${traceId}-0` : undefined;
}
