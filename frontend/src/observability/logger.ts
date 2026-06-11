import type { TraceLog } from './types';

let _traceCounter = 0;

function generateId(): string {
  _traceCounter += 1;
  const hex = Date.now().toString(16).slice(-8);
  const rand = Math.random().toString(16).slice(2, 6);
  return `fe-${hex}${rand}${_traceCounter}`;
}

export function observeLog(log: Omit<TraceLog, 'ts' | 'source'> & Partial<Pick<TraceLog, 'source'>>): void {
  const entry: TraceLog = {
    ts: new Date().toISOString(),
    source: 'frontend',
    ...log,
  } as TraceLog;

  try {
    console.log(JSON.stringify(entry));
  } catch {
    console.log(JSON.stringify({ ...entry, _serializeError: true }));
  }
}

export { generateId };
