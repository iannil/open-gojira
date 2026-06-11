const MAX_DEPTH = 4;
const MAX_STR_LEN = 500;
const MAX_ITEMS = 50;

function safeSerialize(value: unknown, depth = 0): unknown {
  if (depth > MAX_DEPTH) return '<max_depth>';

  if (value === null || value === undefined) return value;

  switch (typeof value) {
    case 'boolean':
    case 'number':
    case 'bigint':
      return value;
    case 'string':
      return value.length > MAX_STR_LEN ? value.slice(0, MAX_STR_LEN) : value;
    case 'symbol':
      return `<symbol:${value.description}>`;
    case 'function':
      return `<func:${value.name || 'anonymous'}>`;
    case 'object':
      break;
    default:
      return String(value).slice(0, MAX_STR_LEN);
  }

  if (Array.isArray(value)) {
    return value.slice(0, MAX_ITEMS).map((item) => safeSerialize(item, depth + 1));
  }

  if (value instanceof Error) {
    return `<Error:${value.message}>`;
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (value instanceof File || value instanceof Blob) {
    return `<File:${(value as File).name || 'blob'}>`;
  }

  if (value instanceof FormData) {
    return '<FormData>';
  }

  if (value instanceof HTMLElement) {
    return `<Element:${value.tagName}>`;
  }

  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>).slice(0, MAX_ITEMS);
    const result: Record<string, unknown> = {};
    for (const [k, v] of entries) {
      result[k] = safeSerialize(v, depth + 1);
    }
    return result;
  }

  return String(value).slice(0, MAX_STR_LEN);
}

export function summarizeResponse(data: unknown): string {
  if (data === null || data === undefined) return `${data}`;
  if (Array.isArray(data)) return `[Array:${data.length}]`;
  if (typeof data === 'object') {
    const keys = Object.keys(data as Record<string, unknown>);
    return `{keys: [${keys.slice(0, 20).join(', ')}], len: ${keys.length}}`;
  }
  const s = String(data);
  return s.length > 100 ? `${s.slice(0, 100)}...` : s;
}

export default safeSerialize;
