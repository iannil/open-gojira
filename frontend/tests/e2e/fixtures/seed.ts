// Test-data hygiene: ensures the golden-path spec starts from a known state.
// Removes user-generated artifacts from prior runs (holdings, dividends, alerts, journal, checks)
// but preserves the seeded stock universe copied from gojira.db into gojira.e2e.db.

const API = 'http://localhost:3001/api';

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) return [] as unknown as T;
  return r.json();
}

async function del(path: string): Promise<void> {
  try {
    await fetch(`${API}${path}`, { method: 'DELETE' });
  } catch {
    /* swallow */
  }
}

export async function resetE2EArtifacts(): Promise<void> {
  // Holdings (sell-and-purge: backend cascades alerts).
  const holdings = await getJson<Array<{ id: number }>>('/portfolio');
  for (const h of holdings) await del(`/portfolio/${h.id}`);

  // Alerts: remove any leftover rules + events.
  const rules = await getJson<Array<{ id: number }>>('/alerts/rules');
  for (const r of rules) await del(`/alerts/rules/${r.id}`);

  // Dividends.
  const divs = await getJson<Array<{ id: number }>>('/dividends');
  for (const d of divs) await del(`/dividends/${d.id}`);

  // Discipline checks + journal.
  const checks = await getJson<Array<{ id: number }>>('/discipline/checks');
  for (const c of checks) await del(`/discipline/checks/${c.id}`);
  const journal = await getJson<Array<{ id: number }>>('/discipline/journal');
  for (const j of journal) await del(`/discipline/journal/${j.id}`);

  // Analyses: no DELETE endpoint — leave intact; the golden path tolerates
  // pre-existing reports because it always opens "+ 新建" and saves fresh.
}
