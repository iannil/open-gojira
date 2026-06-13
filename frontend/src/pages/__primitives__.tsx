/**
 * DEV-ONLY primitives preview route.
 *
 * Mounted at /__primitives__ in development only (gated in App.tsx by
 * import.meta.env.DEV). Vite tree-shakes this file out of production bundles.
 *
 * Purpose: human verification of the 5 shared primitives + token scales
 * before they're rolled out across the 12 pages.
 */

import { useState } from 'react';
import { Button, Input, Select, Space, Switch, Tag } from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  DownloadOutlined,
} from '@ant-design/icons';

import {
  PageHeader,
  PageSection,
  EmptyState,
  StatCard,
  FilterBar,
} from '../components/primitives';

export default function PrimitivesPreview() {
  const [coldCtaClicked, setColdCtaClicked] = useState(0);
  const [filterCleared, setFilterCleared] = useState(0);

  return (
    <div className="gojira-preview">
      <PageHeader
        title="原语预览"
        enLabel="Primitives Preview"
        purpose="开发期人工验收 5 个共享原语（PageHeader / PageSection / EmptyState / StatCard / FilterBar）+ 字号/间距/数字 token 的视觉效果。此页面仅在 dev 模式可见，prod 构建不含。"
        flow={[
          { label: 'PageHeader' },
          { to: '#section', label: 'PageSection' },
          { to: '#empty', label: 'EmptyState' },
          { to: '#stat', label: 'StatCard' },
          { to: '#filter', label: 'FilterBar' },
        ]}
        actions={
          <Button icon={<PlusOutlined />} type="primary">
            示例主操作
          </Button>
        }
      />

      {/* ── PageHeader variants ────────────────────────────────────── */}
      <section className="gojira-preview-section">
        <h2 className="gojira-preview-heading">PageHeader</h2>
        <p className="gojira-preview-desc">
          页面级头部。title + enLabel + purpose + 可选 flow + 可选 actions。
          purpose 字段是 C 痛点的主治药——必须用通俗语言定义业务概念。
        </p>

        <PageSection variant="plain" title="最小用法（无 flow, 无 actions）">
          <PageHeader
            title="股票池"
            enLabel="Stock Pool"
            purpose="你订阅的所有 A 股的集合，是策略和预案运行的输入。"
          />
        </PageSection>

        <PageSection variant="plain" title="完整用法（含 flow + actions）">
          <PageHeader
            title="候选池"
            enLabel="Candidates"
            purpose="预案运行后产出的「值得买」候选股清单。可手工干预：移入观察、加入持仓、或忽略。"
            flow={[
              { to: '/strategies', label: '策略库' },
              { to: '/plans', label: '预案' },
              { label: '候选池' },
              { to: '/trades', label: '成交流水' },
              { to: '/review', label: '复盘' },
            ]}
            actions={
              <Space>
                <Button icon={<ReloadOutlined />}>刷新</Button>
                <Button type="primary" icon={<PlusOutlined />}>
                  手工添加
                </Button>
              </Space>
            }
          />
        </PageSection>
      </section>

      {/* ── PageSection variants ───────────────────────────────────── */}
      <section className="gojira-preview-section" id="section">
        <h2 className="gojira-preview-heading">PageSection</h2>
        <p className="gojira-preview-desc">
          页内分块。variant='card' 包卡片（默认），variant='plain' 仅标题+内容。
        </p>

        <PageSection
          title="持仓概览"
          subtitle="截至今日收盘"
          extra={<Button size="small" type="text">展开全部</Button>}
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            <StatCard label="市值" value="¥234,592" delta={{ value: '+4.2%', direction: 'up' }} hint="占总资产 68%" />
            <StatCard label="今日盈亏" value="¥+1,243" delta={{ value: '+0.5%', direction: 'up' }} />
            <StatCard label="仓位" value="68.4%" delta={{ value: '+2.1pp', direction: 'up', good: 'down' }} hint="目标 70%" />
          </div>
        </PageSection>

        <PageSection variant="plain" title="plain 变体（无卡片）" subtitle="用于紧密贴合的列表场景">
          <div className="gojira-preview-row">
            <Tag color="blue">标签一</Tag>
            <Tag color="green">标签二</Tag>
            <Tag>标签三</Tag>
          </div>
        </PageSection>
      </section>

      {/* ── EmptyState variants ────────────────────────────────────── */}
      <section className="gojira-preview-section" id="empty">
        <h2 className="gojira-preview-heading">EmptyState</h2>
        <p className="gojira-preview-desc">
          3 个 variant。cold = 从未配置；filter = 筛选无匹配；quiet = 周期性无事件。
        </p>

        <div className="gojira-preview-grid">
          <PageSection title="cold（冷启动）">
            <EmptyState
              variant="cold"
              title="还没有策略"
              description="策略 = 一组买卖规则的集合。先建一个策略，再把策略绑到股票池上构成预案。"
              cta={{
                label: '创建第一个策略',
                onClick: () => setColdCtaClicked((n) => n + 1),
              }}
            />
            <div style={{ textAlign: 'center', marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
              CTA 已点击 {coldCtaClicked} 次
            </div>
          </PageSection>

          <PageSection title="filter（筛选无匹配）">
            <EmptyState
              variant="filter"
              title="无匹配候选"
              description="当前筛选条件下无结果"
              onClearFilter={() => setFilterCleared((n) => n + 1)}
            />
            <div style={{ textAlign: 'center', marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
              清除筛选已点击 {filterCleared} 次
            </div>
          </PageSection>

          <PageSection title="quiet（周期性无事件）">
            <EmptyState
              variant="quiet"
              title="今日无新信号，预案在监控中"
            />
          </PageSection>
        </div>
      </section>

      {/* ── StatCard variants ──────────────────────────────────────── */}
      <section className="gojira-preview-section" id="stat">
        <h2 className="gojira-preview-heading">StatCard</h2>
        <p className="gojira-preview-desc">
          label + value（mono）+ delta（自动染色 up=绿 / down=红 / flat=灰）+ hint。
          delta.good 可翻转好事性（如回撤越低越好）。
        </p>

        <div className="gojira-preview-grid">
          <StatCard label="年度被动现金流" value="¥84,392" delta={{ value: '+12.4% YoY', direction: 'up' }} hint="目标 ¥120k" />
          <StatCard label="加权股息率" value="4.83%" delta={{ value: '+0.21pp', direction: 'up' }} />
          <StatCard label="最大回撤" value="-8.4%" delta={{ value: '-1.2pp', direction: 'down', good: 'down' }} hint="近 12 月" />
          <StatCard label="夏普比率" value="1.42" delta={{ value: '0.00', direction: 'flat' }} hint="基准 1.0" />
          <StatCard label="持仓数" value="12" hint="上限 20" />
          <StatCard label="加载中" value="—" loading />
        </div>
      </section>

      {/* ── FilterBar ──────────────────────────────────────────────── */}
      <section className="gojira-preview-section" id="filter">
        <h2 className="gojira-preview-heading">FilterBar</h2>
        <p className="gojira-preview-desc">
          统一筛选区。左侧控件 + 右侧重置/操作。
        </p>

        <PageSection>
          <FilterBar onReset={() => 0} actions={<Button size="small" icon={<DownloadOutlined />}>导出</Button>}>
            <Select
              placeholder="行业"
              style={{ width: 140 }}
              options={[
                { value: 'finance', label: '金融' },
                { value: 'tech', label: '科技' },
              ]}
            />
            <Select
              placeholder="评级"
              style={{ width: 140 }}
              options={[
                { value: 'aaa', label: 'AAA' },
                { value: 'aa', label: 'AA' },
              ]}
            />
            <Input.Search placeholder="代码 / 名称" style={{ width: 200 }} />
            <Space size={4}>
              <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>仅看持仓</span>
              <Switch size="small" />
            </Space>
          </FilterBar>

          <div style={{ padding: '24px 0', color: 'var(--text-tertiary)', fontSize: 13 }}>
            ↑ FilterBar 下方的页面内容区
          </div>
        </PageSection>
      </section>

      {/* ── Token samples ──────────────────────────────────────────── */}
      <section className="gojira-preview-section">
        <h2 className="gojira-preview-heading">Type Scale（5 档）</h2>
        <p className="gojira-preview-desc">--fs-xs(12) / sm(14) / md(16) / lg(20) / xl(28)</p>

        <PageSection variant="plain">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 'var(--fs-xl)', fontWeight: 'var(--fw-semibold)' }}>28 xl · 页面标题</div>
            <div style={{ fontSize: 'var(--fs-lg)', fontWeight: 'var(--fw-semibold)' }}>20 lg · 子区块标题</div>
            <div style={{ fontSize: 'var(--fs-md)' }}>16 md · 强调正文 / lead</div>
            <div style={{ fontSize: 'var(--fs-sm)' }}>14 sm · body 基准</div>
            <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>12 xs · caption / tag</div>
          </div>
        </PageSection>

        <h2 className="gojira-preview-heading" style={{ marginTop: 32 }}>Numeric Mono</h2>
        <p className="gojira-preview-desc">JetBrains Mono + tabular-nums。数字一律走 .num 类。</p>

        <PageSection variant="plain">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontFamily: 'var(--font-numeric)', fontVariantNumeric: 'tabular-nums' }}>
            <span className="num num-lg">¥1,234,567.89</span>
            <span className="num num-md">4.83%</span>
            <span className="num num-sm">+12.4% YoY</span>
            <span style={{ fontFamily: 'var(--font-sans)' }}>
              对比 sans-serif：<span className="num">1,234,567.89</span> vs 1,234,567.89
            </span>
          </div>
        </PageSection>

        <h2 className="gojira-preview-heading" style={{ marginTop: 32 }}>Spacing Scale（4px 网格, 7 档）</h2>
        <p className="gojira-preview-desc">--sp-1(4) / 2(8) / 3(12) / 4(16) / 6(24) / 8(32) / 12(48)</p>

        <PageSection variant="plain">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {[
              ['sp-1', 'var(--sp-1)'],
              ['sp-2', 'var(--sp-2)'],
              ['sp-3', 'var(--sp-3)'],
              ['sp-4', 'var(--sp-4)'],
              ['sp-6', 'var(--sp-6)'],
              ['sp-8', 'var(--sp-8)'],
              ['sp-12', 'var(--sp-12)'],
            ].map(([name, val]) => (
              <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 12, fontFamily: 'var(--font-numeric)', fontSize: 13 }}>
                <span style={{ width: 60 }}>{name}</span>
                <div style={{ height: 16, background: 'var(--primary-500)', borderRadius: 2, width: val }} />
                <span style={{ color: 'var(--text-tertiary)' }}>{val}</span>
              </div>
            ))}
          </div>
        </PageSection>
      </section>
    </div>
  );
}
