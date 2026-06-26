/**
 * Phase 6 Tier 1 — Metrics Dashboard Tab
 *
 * 展示 Pipeline 成功率、LLM 成本/Token/冲突率、月度预算。
 * 使用 ECharts 做 sparkline + 指标卡片。
 */
import { useEffect, useState } from 'react';

import {
  Alert,
  Card,
  Col,
  Row,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  DollarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import echarts from '../../../lib/echarts';

import { fetchLLMMetrics, fetchLLMTrend, fetchPipelineMetrics } from '../../../api/client';
import type { LLMMetrics, LLMTrend, PipelineMetrics } from '../../../api/types';

const { Title, Text } = Typography;

function formatUsd(v: number): string {
  return `$${v.toFixed(2)}`;
}

function pct(v: number): string {
  return `${v.toFixed(1)}%`;
}

export default function MetricsTab() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineMetrics | null>(null);
  const [llm, setLLM] = useState<LLMMetrics | null>(null);
  const [trend, setTrend] = useState<LLMTrend | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      fetchPipelineMetrics(30),
      fetchLLMMetrics(30),
      fetchLLMTrend(30),
    ])
      .then(([p, l, t]) => {
        if (!cancelled) {
          setPipeline(p);
          setLLM(l);
          setTrend(t);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message || '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <Spin tip="加载 Metrics…" style={{ display: 'block', marginTop: 48 }} />;
  if (error) return <Alert type="error" message={error} />;

  return (
    <div>
      {/* ── Pipeline 成功概览 ──────────────────────────────────────────────── */}
      <Title level={5}>
        <ThunderboltOutlined /> Pipeline 运营健康
      </Title>
      {pipeline && (
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} sm={8}>
            <Card size="small">
              <Statistic
                title="Pipeline 总执行次数（近 30 天）"
                value={pipeline.overall.total}
                suffix="次"
              />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card size="small">
              <Statistic
                title="总体成功率"
                value={pipeline.overall.success_rate_pct}
                suffix="%"
                precision={1}
                valueStyle={{ color: pipeline.overall.success_rate_pct >= 90 ? '#3f8600' : '#cf1322' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card size="small">
              <Statistic
                title="Pipeline 类型数"
                value={Object.keys(pipeline.pipelines).length}
                suffix="种"
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* ── Pipeline 明细表 ─────────────────────────────────────────────────── */}
      {pipeline && Object.keys(pipeline.pipelines).length > 0 && (
        <Table
          dataSource={Object.entries(pipeline.pipelines).map(([type, stats]) => ({
            key: type,
            type,
            total: stats.total,
            success: stats.success,
            failed: stats.failed,
            running: stats.running,
            other: stats.other,
            success_rate_pct: stats.success_rate_pct,
            avg_duration_ms: stats.avg_duration_ms,
          }))}
          columns={[
            { title: 'Pipeline', dataIndex: 'type', key: 'type' },
            { title: '总次数', dataIndex: 'total', key: 'total', width: 80 },
            {
              title: '成功率', dataIndex: 'success_rate_pct', key: 'rate', width: 100,
              render: (v: number) => (
                <Tag color={v >= 90 ? 'green' : v >= 70 ? 'orange' : 'red'}>{pct(v)}</Tag>
              ),
            },
            { title: '成功', dataIndex: 'success', key: 'success', width: 60 },
            { title: '失败', dataIndex: 'failed', key: 'failed', width: 60 },
            { title: '运行中', dataIndex: 'running', key: 'running', width: 60 },
            { title: '平均耗时(ms)', dataIndex: 'avg_duration_ms', key: 'duration', width: 120 },
          ]}
          size="small"
          pagination={false}
        />
      )}
      {pipeline && Object.keys(pipeline.pipelines).length === 0 && (
        <Text type="secondary">近 30 天无 Pipeline 执行记录</Text>
      )}

      {/* ── LLM 费用概览 ────────────────────────────────────────────────────── */}
      <Title level={5} style={{ marginTop: 32 }}>
        <DollarOutlined /> LLM 费用 & Token 消耗
      </Title>
      {llm && (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={8}>
              <Card size="small">
                <Statistic
                  title="本月 LLM 费用"
                  value={formatUsd(llm.monthly_cost.total_usd)}
                  suffix={`/ ${formatUsd(llm.monthly_cost.hard_cap_usd)}`}
                  valueStyle={{
                    color: llm.monthly_cost.over_hard ? '#cf1322'
                      : llm.monthly_cost.over_soft ? '#d48806' : '#3f8600',
                  }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card size="small">
                <Statistic
                  title="近 30 天调用次数"
                  value={llm.total_calls}
                  suffix="次"
                />
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card size="small">
                <Statistic
                  title="冲突率 (data_conflict)"
                  value={llm.conflict_rate_pct}
                  suffix="%"
                  precision={1}
                  valueStyle={{ color: llm.conflict_rate_pct > 20 ? '#cf1322' : '#3f8600' }}
                />
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} sm={6}>
              <Card size="small">
                <Statistic
                  title="Total Tokens In"
                  value={llm.total_tokens_in.toLocaleString()}
                />
              </Card>
            </Col>
            <Col xs={24} sm={6}>
              <Card size="small">
                <Statistic
                  title="Total Tokens Out"
                  value={llm.total_tokens_out.toLocaleString()}
                />
              </Card>
            </Col>
            <Col xs={24} sm={6}>
              <Card size="small">
                <Statistic
                  title="LLM 成功率"
                  value={llm.success_rate_pct}
                  suffix="%"
                  precision={1}
                  valueStyle={{ color: llm.success_rate_pct >= 95 ? '#3f8600' : '#cf1322' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={6}>
              <Card size="small">
                <Statistic
                  title="平均延迟"
                  value={(llm.avg_latency_ms / 1000).toFixed(1)}
                  suffix="s"
                />
              </Card>
            </Col>
          </Row>

          {/* ⚠️ 预算告警 */}
          {llm.monthly_cost.over_hard && (
            <Alert
              type="error"
              message={`🚨 LLM 月度预算硬熔断！本月已花费 $${llm.monthly_cost.total_usd.toFixed(2)}，非关键 Pipeline 已暂停`}
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}
          {llm.monthly_cost.over_soft && !llm.monthly_cost.over_hard && (
            <Alert
              type="warning"
              message={`⚠️ LLM 月度预算接近上限：$${llm.monthly_cost.total_usd.toFixed(2)} / $${llm.monthly_cost.hard_cap_usd.toFixed(2)}`}
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          {/* ── LLM By Pipeline 明细 ─────────────────────────────────────── */}
          <Title level={5}>按 Pipeline 明细</Title>
          {Object.keys(llm.by_pipeline).length > 0 ? (
            <Table
              dataSource={Object.entries(llm.by_pipeline).map(([type, stats]) => ({
                key: type, type,
                calls: stats.calls,
                cost_usd: stats.cost_usd,
                tokens_in: stats.tokens_in,
                tokens_out: stats.tokens_out,
                conflict_rate_pct: stats.conflict_rate_pct,
              }))}
              columns={[
                { title: 'Pipeline', dataIndex: 'type', key: 'type' },
                { title: '调用次数', dataIndex: 'calls', key: 'calls', width: 80 },
                { title: '费用 (USD)', dataIndex: 'cost_usd', key: 'cost', width: 100, render: formatUsd },
                { title: 'Tokens In', dataIndex: 'tokens_in', key: 'tokens_in', width: 100, render: (v: number) => v.toLocaleString() },
                { title: 'Tokens Out', dataIndex: 'tokens_out', key: 'tokens_out', width: 100, render: (v: number) => v.toLocaleString() },
                {
                  title: '冲突率', dataIndex: 'conflict_rate_pct', key: 'conflict_rate', width: 80,
                  render: (v: number) => (
                    <Tag color={v > 20 ? 'red' : v > 5 ? 'orange' : 'green'}>{pct(v)}</Tag>
                  ),
                },
              ]}
              size="small"
              pagination={false}
            />
          ) : (
            <Text type="secondary">无数据</Text>
          )}
        </>
      )}

      {/* ── LLM 费用趋势 ────────────────────────────────────────────────────── */}
      {trend && trend.labels.length > 0 && (
        <>
          <Title level={5} style={{ marginTop: 32 }}>日级别费用趋势</Title>
          <ReactEChartsCore
            echarts={echarts}
            option={{
              tooltip: { trigger: 'axis' },
              grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
              xAxis: {
                type: 'category',
                data: (trend.labels || []).map((d: string) => d.slice(5)), // MM-DD
              },
              yAxis: { type: 'value', name: 'USD' },
              series: [
                {
                  name: '费用 (USD)',
                  type: 'line',
                  data: trend.cost_usd,
                  smooth: true,
                  areaStyle: { opacity: 0.15 },
                  itemStyle: { color: '#1677ff' },
                },
              ],
            }}
            style={{ height: 240 }}
          />
        </>
      )}
      {trend && trend.labels.length === 0 && (
        <Text type="secondary">近 30 天无 LLM 调用记录</Text>
      )}
    </div>
  );
}
