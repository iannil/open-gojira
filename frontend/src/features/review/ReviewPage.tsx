import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Button,
  DatePicker,
  Empty,
  InputNumber,
  Space,
  Tabs,
  Tooltip,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';

import { PageHeader, PageSection, StatCard, EmptyState } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import {
  useAnnualReviewQuery,
  useMonthlyReviewQuery,
  useQuarterlyReviewQuery,
} from './useReviewQueries';
import type {
  AnnualReview as AnnualReviewType,
  QuarterlyReview as QuarterlyReviewType,
  ReviewByStock,
  ReviewEntry,
  ReviewResponse,
} from '../../api/types';

// ── Label maps ─────────────────────────────────────────────────────────

const ENTITY_LABEL: Record<string, string> = {
  draft: '草稿',
  plan: '预案',
  plan_template: '模板',
  holding: '持仓',
  cashflow_goal: '目标',
  alert: '告警',
  stock: '标的',
};

const EVENT_LABEL: Record<string, string> = {
  triggered: '触发',
  executed: '执行',
  cancelled: '取消',
  created: '创建',
  draft_created: '草稿生成',
  updated: '更新',
  invalidated: '撤销',
  status_changed: '状态变更',
  sold: '卖出',
  blocked_by_portfolio_constraint: '仓位阻断',
};

const EVENT_MARK: Record<string, string> = {
  executed: '◆',
  cancelled: '✕',
  invalidated: '✕',
  sold: '▼',
  created: '▲',
  draft_created: '▲',
  triggered: '●',
  updated: '◆',
  status_changed: '◆',
};

const ACTOR_LABEL: Record<string, string> = {
  user: '用户',
  evaluator: '系统',
  scheduler: '调度',
  plan_evaluator: '调度',
};

// ── Helpers ────────────────────────────────────────────────────────────

function formatPct(decimal: number | null | undefined, digits = 1): string {
  if (decimal == null) return '—';
  return `${(decimal * 100).toFixed(digits)}%`;
}

function getTone(value: number | null | undefined, thresholds: [number, number]): 'pos' | 'warn' | 'neg' | 'none' {
  if (value == null) return 'none';
  if (value >= thresholds[0]) return 'pos';
  if (value >= thresholds[1]) return 'warn';
  return 'neg';
}

function getHitRateVerdict(hr: number | null | undefined): string {
  if (hr == null) return '尚无成交';
  if (hr >= 0.7) return '表现良好';
  if (hr >= 0.3) return '可接受';
  return '需回顾';
}

// ── Hero Stat (single emphasized metric) ───────────────────────────────

function HeroStat({
  label,
  value,
  unit,
  meta,
  verdict,
  tone,
}: {
  label: string;
  value: string;
  unit?: string;
  meta: React.ReactNode;
  verdict?: string;
  tone: 'pos' | 'warn' | 'neg' | 'none';
}) {
  return (
    <div className="gojira-stat-hero" data-tone={tone}>
      <div className="gojira-stat-hero-label">{label}</div>
      <div className="gojira-stat-hero-value" data-tone={tone}>
        {value}
        {unit && <span className="gojira-stat-hero-unit">{unit}</span>}
      </div>
      <div className="gojira-stat-hero-meta">
        {meta}
        {verdict && (
          <span className="gojira-stat-hero-verdict" data-tone={tone}>
            {verdict}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Editor's Note ──────────────────────────────────────────────────────

function EditorsNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="gojira-editors-note">
      <div className="gojira-editors-note-mark">※</div>
      <div className="gojira-editors-note-body">
        <em>{children}</em>
        <span className="gojira-editors-note-sig">— Gojira 复盘</span>
      </div>
    </div>
  );
}

// ── Cycle Card ─────────────────────────────────────────────────────────

function CycleCard({ cycle }: { cycle: NonNullable<ReviewResponse['cycle']> }) {
  const positionLabel: Record<string, string> = {
    extreme_low: '极度低估',
    low: '低估',
    mid: '中等',
    high: '偏高',
    extreme_high: '极度高估',
  };
  const pos = cycle.cycle_position;
  const range = cycle.position_range;
  return (
    <div className="gojira-cycle">
      <div className="gojira-cycle-head">
        <span className="gojira-cycle-position" data-pos={pos}>
          {positionLabel[pos] ?? pos}
        </span>
        {cycle.pe_pct_10y != null && (
          <span className="gojira-cycle-pe">
            沪深 300 PE 分位
            <span className="gojira-cycle-pe-num">{cycle.pe_pct_10y.toFixed(1)}%</span>
          </span>
        )}
      </div>
      <div className="gojira-cycle-advice">{cycle.position_advice}</div>
      <div>
        <div className="gojira-cycle-range">
          <span className="gojira-cycle-range-label">建议仓位</span>
          <div className="gojira-cycle-range-bar">
            <div
              className="gojira-cycle-range-fill"
              style={{ left: `${range[0] * 100}%`, right: `${(1 - range[1]) * 100}%` }}
            />
          </div>
        </div>
        <div className="gojira-cycle-range-marks">
          <span>{(range[0] * 100).toFixed(0)}%</span>
          <span>{(range[1] * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}

// ── Alerts List ────────────────────────────────────────────────────────

function AlertsList({ alerts }: { alerts: ReviewResponse['thesis_alerts'] }) {
  return (
    <div>
      {alerts.map((a, i) => (
        <div className="gojira-alerts-row" key={i}>
          <span className="gojira-alerts-stamp" data-severity={a.threshold_type}>
            {a.threshold_type === 'critical' ? '严重' : '警告'}
          </span>
          <Link to={`/stock/${a.code}`} className="gojira-alerts-code">
            {a.code}
          </Link>
          <span className="gojira-alerts-var">{a.variable_name}</span>
          <span className="gojira-alerts-msg">{a.message}</span>
        </div>
      ))}
    </div>
  );
}

// ── Stock Draft List ───────────────────────────────────────────────────

function StockDraftList({ data }: { data: ReviewByStock[] }) {
  if (data.length === 0) {
    return (
      <EmptyState
        variant="quiet"
        title="本月尚无活跃草稿"
      />
    );
  }
  return (
    <div className="gojira-stock-list">
      {data.map((s, idx) => (
        <div className="gojira-stock-row" key={s.stock_code}>
          <span className="gojira-stock-rank">{idx + 1}</span>
          <Link to={`/stock/${s.stock_code}`} className="gojira-stock-code">
            {s.stock_code}
          </Link>
          <div className="gojira-stock-pattern">
            {s.business_pattern_name ? (
              <>
                <span className="gojira-stock-pattern-name">{s.business_pattern_name}</span>
                {s.first_principle_variable && (
                  <Tooltip title={s.first_principle_variable}>
                    <span className="gojira-stock-pattern-var">
                      {s.first_principle_variable}
                    </span>
                  </Tooltip>
                )}
              </>
            ) : (
              <span className="gojira-stock-pattern-name-unlinked">未关联商业模式</span>
            )}
          </div>
          <div>
            <div className="gojira-stock-drafts">{s.drafts_triggered}</div>
            <span className="gojira-stock-drafts-label">drafts</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Ledger ─────────────────────────────────────────────────────────────

function Ledger({ entries }: { entries: ReviewEntry[] }) {
  if (entries.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span style={{ color: 'var(--text-tertiary)' }}>本月无事件</span>
        }
      />
    );
  }
  return (
    <div className="gojira-ledger">
      {entries.map((e) => {
        const day = e.created_at ? dayjs(e.created_at).format('MM-DD') : '—';
        const time = e.created_at ? dayjs(e.created_at).format('HH:mm') : '';
        const mark = EVENT_MARK[e.event] ?? '·';
        return (
          <div className="gojira-ledger-row" key={e.id}>
            <div className="gojira-ledger-time">
              <span className="gojira-ledger-time-day">{day}</span>
              {time && <span className="gojira-ledger-time-time">{time}</span>}
            </div>
            <div className="gojira-ledger-mark" data-event={e.event}>
              {mark}
            </div>
            <div className="gojira-ledger-body">
              <div className="gojira-ledger-head">
                <span className="gojira-ledger-tag">
                  {ENTITY_LABEL[e.entity_type] ?? e.entity_type} ·{' '}
                  {EVENT_LABEL[e.event] ?? e.event}
                </span>
                {e.stock_code && (
                  <Link to={`/stock/${e.stock_code}`} className="gojira-ledger-stock">
                    {e.stock_code}
                  </Link>
                )}
                {e.actor && (
                  <span className="gojira-ledger-actor">— {ACTOR_LABEL[e.actor] ?? e.actor}</span>
                )}
              </div>
              <div className="gojira-ledger-summary">{e.summary}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Monthly Tab ────────────────────────────────────────────────────────

function MonthlyTab() {
  const [month, setMonth] = useState<Dayjs>(dayjs().startOf('month'));
  const monthQ = useMonthlyReviewQuery(month.format('YYYY-MM'));

  const tone = getTone(monthQ.data?.drafts.hit_rate, [0.7, 0.3]);
  const hitRate = monthQ.data?.drafts.hit_rate;
  const displayHitRate = hitRate != null ? (hitRate * 100).toFixed(1) : '—';

  return (
    <>
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          marginBottom: 'var(--sp-4)',
        }}
      >
        <Space>
          <DatePicker
            picker="month"
            value={month}
            allowClear={false}
            onChange={(v) => v && setMonth(v.startOf('month'))}
          />
          <Button onClick={() => monthQ.refetch()} loading={monthQ.isFetching}>
            刷新
          </Button>
        </Space>
      </div>

      <QueryBoundary query={monthQ}>
        {(d: ReviewResponse) => (
          <>
            {/* Hero Stat — hit rate anchored */}
            <div style={{ marginBottom: 'var(--sp-6)' }}>
              <HeroStat
                label="本月命中率 · MONTHLY HIT RATE"
                value={displayHitRate}
                unit={hitRate != null ? '%' : undefined}
                tone={tone}
                verdict={getHitRateVerdict(hitRate)}
                meta={
                  <>
                    <span>
                      <span className="gojira-stat-hero-meta-num">
                        {d.drafts.executed}
                      </span>{' '}
                      已成交
                    </span>
                    <span className="gojira-stat-hero-meta-sep">/</span>
                    <span>
                      <span className="gojira-stat-hero-meta-num">
                        {d.drafts.triggered}
                      </span>{' '}
                      触发
                    </span>
                  </>
                }
              />
            </div>

            {/* Stat strip — at a glance */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 'var(--sp-4)',
                marginBottom: 'var(--sp-6)',
              }}
            >
              <StatCard
                label="买入 / 卖出"
                value={`${d.drafts.buy} / ${d.drafts.sell}`}
                hint="本月触发的草稿方向"
              />
              <StatCard
                label="新建 / 失效预案"
                value={`${d.plans.created} / ${d.plans.invalidated}`}
                hint={`状态变更 ${d.plans.status_changed} 次`}
              />
              <StatCard
                label="持仓买入 / 卖出"
                value={`${d.holdings.created} / ${d.holdings.sold}`}
                hint="真实成交回填"
              />
              <StatCard
                label="现金流目标调整"
                value={d.cashflow_goal_updates}
                hint="本月调整次数"
              />
            </div>

            {/* Cycle + Alerts */}
            {(d.cycle || d.thesis_alerts.length > 0) && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns:
                    d.cycle && d.thesis_alerts.length > 0
                      ? '1fr 1fr'
                      : '1fr',
                  gap: 'var(--sp-4)',
                  marginBottom: 'var(--sp-6)',
                }}
              >
                {d.cycle && (
                  <PageSection title="市场周期" subtitle="Market Cycle Position">
                    <CycleCard cycle={d.cycle} />
                  </PageSection>
                )}
                {d.thesis_alerts.length > 0 && (
                  <PageSection
                    title="论点越界"
                    subtitle={`Thesis Alerts · ${d.thesis_alerts.length} 项`}
                  >
                    <AlertsList alerts={d.thesis_alerts} />
                  </PageSection>
                )}
              </div>
            )}

            {/* Draft Activity + Ledger */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 3fr)',
                gap: 'var(--sp-4)',
                marginBottom: 'var(--sp-6)',
              }}
            >
              <PageSection
                title="本月草稿活动"
                subtitle={`Top ${d.by_stock.length} · Draft Activity`}
              >
                <StockDraftList data={d.by_stock} />
              </PageSection>
              <PageSection
                title="事件流水"
                subtitle={`Ledger · ${d.entries.length} 条`}
              >
                <Ledger entries={d.entries} />
              </PageSection>
            </div>

            <EditorsNote>
              {hitRate == null ? (
                <>
                  本月尚无成交记录,命中率栏位留白。若{' '}
                  <strong>{d.drafts.triggered}</strong> 次触发{' '}
                  <strong>{d.drafts.executed}</strong> 次执行为零,建议检视 gates 是否过严。
                </>
              ) : (
                <>
                  命中率 <strong>{formatPct(hitRate)}</strong>(
                  <strong>
                    {d.drafts.executed}/{d.drafts.triggered}
                  </strong>
                  )。低于 30% 说明 gates 太松或 ladder 阈值过激,应回顾预案;高于 70% 则纪律稳定,可保持。
                </>
              )}
            </EditorsNote>
          </>
        )}
      </QueryBoundary>
    </>
  );
}

// ── Quarterly Tab ──────────────────────────────────────────────────────

function QuarterlyTab() {
  const [year, setYear] = useState(dayjs().year());
  const [q, setQ] = useState(Math.ceil((dayjs().month() + 1) / 3));
  const qQ = useQuarterlyReviewQuery(year, q);

  const psr = qQ.data?.plan_success_rate;
  const tone = getTone(psr, [0.7, 0.4]);

  return (
    <>
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          marginBottom: 'var(--sp-4)',
        }}
      >
        <Space>
          <InputNumber min={2020} max={2030} value={year} onChange={(v) => v && setYear(v)} />
          <Space size={4}>
            {[1, 2, 3, 4].map((i) => (
              <Button
                key={i}
                size="small"
                type={q === i ? 'primary' : 'default'}
                onClick={() => setQ(i)}
              >
                Q{i}
              </Button>
            ))}
          </Space>
          <Button onClick={() => qQ.refetch()} loading={qQ.isFetching}>
            刷新
          </Button>
        </Space>
      </div>

      <QueryBoundary query={qQ}>
        {(data: QuarterlyReviewType) => (
          <>
            <div style={{ marginBottom: 'var(--sp-6)' }}>
              <HeroStat
                label={`本季预案成功率 · Q${q} ${year}`}
                value={psr != null ? (psr * 100).toFixed(1) : '—'}
                unit={psr != null ? '%' : undefined}
                tone={tone}
                meta={
                  <>
                    <span>
                      执行{' '}
                      <span className="gojira-stat-hero-meta-num">
                        {data.drafts_executed}
                      </span>
                    </span>
                    <span className="gojira-stat-hero-meta-sep">·</span>
                    <span>
                      取消{' '}
                      <span className="gojira-stat-hero-meta-num">
                        {data.drafts_cancelled}
                      </span>
                    </span>
                  </>
                }
              />
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 'var(--sp-4)',
                marginBottom: 'var(--sp-6)',
              }}
            >
              <StatCard
                label="预案成功率"
                value={`${((data.plan_success_rate ?? 0) * 100).toFixed(1)}%`}
                hint="Plan Success Rate"
              />
              <StatCard
                label="执行 / 取消"
                value={`${data.drafts_executed} / ${data.drafts_cancelled}`}
                hint="草稿流转"
              />
              <StatCard
                label="纪律评分"
                value={`${((data.discipline_score ?? 0) * 100).toFixed(1)}%`}
                hint={`${data.discipline_total} 项检查`}
              />
              <StatCard
                label="主题对齐"
                value={`${(data.theme_alignment_pct ?? 0).toFixed(1)}%`}
                hint="Theme Alignment"
              />
            </div>

            <EditorsNote>
              本季度共执行 <strong>{data.drafts_executed}</strong> 笔草稿,取消{' '}
              <strong>{data.drafts_cancelled}</strong> 笔,纪律评分{' '}
              <strong>{((data.discipline_score ?? 0) * 100).toFixed(1)}%</strong>。季末是回顾 gates
              与 ladder 阈值的最佳时机。
            </EditorsNote>
          </>
        )}
      </QueryBoundary>
    </>
  );
}

// ── Annual Tab ─────────────────────────────────────────────────────────

function AnnualTab() {
  const [year, setYear] = useState(dayjs().year());
  const q = useAnnualReviewQuery(year);

  const gp = q.data?.goal_progress_pct;
  const tone = getTone(gp, [0.7, 0.4]);
  const maxExec = Math.max(1, ...q.data?.quarters.map((qr) => qr.drafts_executed ?? 0) ?? [1]);

  return (
    <>
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          marginBottom: 'var(--sp-4)',
        }}
      >
        <Space>
          <InputNumber min={2020} max={2030} value={year} onChange={(v) => v && setYear(v)} />
          <Button onClick={() => q.refetch()} loading={q.isFetching}>
            刷新
          </Button>
        </Space>
      </div>

      <QueryBoundary query={q}>
        {(data: AnnualReviewType) => (
          <>
            <div style={{ marginBottom: 'var(--sp-6)' }}>
              <HeroStat
                label={`年度目标进度 · ${year}`}
                value={gp != null ? (gp * 100).toFixed(1) : '—'}
                unit={gp != null ? '%' : undefined}
                tone={tone}
                meta={
                  <>
                    <span>
                      股息收入{' '}
                      <span className="gojira-stat-hero-meta-num">
                        ¥{data.dividend_income_estimate.toFixed(0)}
                      </span>
                    </span>
                    <span className="gojira-stat-hero-meta-sep">·</span>
                    <span>
                      <span className="gojira-stat-hero-meta-num">
                        {data.dividend_records_count}
                      </span>{' '}
                      条股息记录
                    </span>
                  </>
                }
              />
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 'var(--sp-4)',
                marginBottom: 'var(--sp-6)',
              }}
            >
              <StatCard
                label="目标进度"
                value={`${((data.goal_progress_pct ?? 0) * 100).toFixed(1)}%`}
                hint="Goal Progress"
              />
              <StatCard
                label="执行 / 取消"
                value={`${data.total_executed} / ${data.total_cancelled}`}
                hint="全年累计"
              />
              <StatCard
                label="股息记录"
                value={data.dividend_records_count}
                hint="到账次数"
              />
              <StatCard
                label="股息收入"
                value={`¥${data.dividend_income_estimate.toFixed(0)}`}
                hint="估算总额"
              />
            </div>

            <PageSection
              title="季度分布"
              subtitle={`Quarterly Breakdown · ${year}`}
              variant="card"
            >
              <div className="gojira-quarterly-bars">
                {data.quarters.map((qr, idx) => {
                  const exec = qr.drafts_executed ?? 0;
                  const ratio = exec / maxExec;
                  const barTone =
                    exec === 0
                      ? 'none'
                      : ratio >= 0.66
                        ? 'pos'
                        : ratio >= 0.33
                          ? 'warn'
                          : 'neg';
                  return (
                    <div className="gojira-quarterly-bar" key={idx}>
                      <div className="gojira-quarterly-bar-label">{qr.period}</div>
                      <div className="gojira-quarterly-bar-track">
                        <div
                          className="gojira-quarterly-bar-fill"
                          data-tone={barTone}
                          style={{ width: `${(exec / maxExec) * 100}%` }}
                        />
                      </div>
                      <div className="gojira-quarterly-bar-num">{exec}</div>
                      <div className="gojira-quarterly-bar-meta">
                        成功率{' '}
                        {qr.plan_success_rate != null
                          ? `${(qr.plan_success_rate * 100).toFixed(0)}%`
                          : '—'}
                      </div>
                    </div>
                  );
                })}
              </div>
            </PageSection>

            <EditorsNote>
              {year} 年累计执行 <strong>{data.total_executed}</strong> 笔,取消{' '}
              <strong>{data.total_cancelled}</strong> 笔。股息到账{' '}
              <strong>{data.dividend_records_count}</strong> 次,估算总额{' '}
              <strong>¥{data.dividend_income_estimate.toFixed(2)}</strong>。年末回顾主线对齐度与持仓
              tier 分布是否需要再平衡。
            </EditorsNote>
          </>
        )}
      </QueryBoundary>
    </>
  );
}

// ── Page Shell ─────────────────────────────────────────────────────────

export default function ReviewPage() {
  return (
    <div>
      <PageHeader
        title="复盘"
        enLabel="Review"
        purpose="事后审计：草稿命中率、预案表现、市场周期、论点告警。命中率 < 30% 说明 gates 太松，需要调预案。"
        flow={[
          { to: '/trades', label: '成交流水' },
          { label: '复盘' },
          { to: '/backtest', label: '回测' },
        ]}
      />
      <Tabs
        defaultActiveKey="monthly"
        items={[
          { key: 'monthly', label: '月度', children: <MonthlyTab /> },
          { key: 'quarterly', label: '季度', children: <QuarterlyTab /> },
          { key: 'annual', label: '年度', children: <AnnualTab /> },
        ]}
      />
    </div>
  );
}
