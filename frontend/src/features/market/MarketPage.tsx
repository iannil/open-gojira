import { useState } from 'react';

import { Card, Col, Row, Statistic, Tag } from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  LineChartOutlined,
  MinusOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import ReactEChartsCore from 'echarts-for-react/esm/core';
import type { EChartsOption } from 'echarts';

import { fetchIndexKline, fetchMarketIndices } from '../../api/client';
import type { MarketIndexItem } from '../../api/client';
import echarts from '../../lib/echarts';
import { PageHeader } from '../../components/primitives';
import PageSection from '../../components/primitives/PageSection';
import QueryBoundary from '../../components/QueryBoundary';

const INDEX_NAMES: Record<string, string> = {
  '000001': '上证指数',
  '399001': '深证成指',
  '399006': '创业板指',
  '000688': '科创50',
  '000300': '沪深300',
  '000905': '中证500',
  '000016': '上证50',
  '399852': '中证1000',
};

function fmtPct(v: number | null): string {
  if (v === null || v === undefined) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function IndexCard({ item }: { item: MarketIndexItem }) {
  const isUp = (item.change_pct ?? 0) >= 0;
  const ArrowIcon = item.change_pct === null ? MinusOutlined : isUp ? ArrowUpOutlined : ArrowDownOutlined;
  const color = item.change_pct === null ? undefined : isUp ? '#cf1322' : '#3f8600';

  return (
    <Col span={6}>
      <Card hoverable>
        <Statistic
          title={item.name || item.code}
          value={item.close ?? 0}
          precision={2}
          prefix={<ArrowIcon style={{ color }} />}
          suffix={
            <span style={{ color, fontSize: 14 }}>{fmtPct(item.change_pct)}</span>
          }
          valueStyle={{ fontSize: 22 }}
        />
      </Card>
    </Col>
  );
}

export default function MarketPage() {
  const [selectedCode, setSelectedCode] = useState<string>('000001');

  const indicesQ = useQuery({
    queryKey: ['market', 'indices'],
    queryFn: fetchMarketIndices,
    refetchInterval: 60_000,
  });

  const klineQ = useQuery({
    queryKey: ['market', 'kline', selectedCode],
    queryFn: () => fetchIndexKline(selectedCode, 120),
    enabled: !!selectedCode,
  });

  const indices = indicesQ.data ?? [];

  return (
    <div>
      <PageHeader
        title="市场指数"
        enLabel="Market"
        purpose="主要 A 股指数实时行情与历史走势。"
      />

      {/* 指数行情卡片 */}
      <PageSection title={<><LineChartOutlined /> 指数行情</>}>
        <QueryBoundary query={indicesQ} isEmpty={(d) => d.length === 0}>
          {() => (
            <Row gutter={[16, 16]}>
              {indices.map((item) => (
                <IndexCard key={item.code} item={item} />
              ))}
            </Row>
          )}
        </QueryBoundary>
      </PageSection>

      {/* 指数选择 + K线简要展示 */}
      <PageSection
        title={<><LineChartOutlined /> 指数详情</>}
        subtitle="选择指数查看近期走势"
      >
        <div style={{ marginBottom: 16 }}>
          {Object.entries(INDEX_NAMES).map(([code, name]) => (
            <Tag
              key={code}
              color={selectedCode === code ? 'blue' : 'default'}
              style={{ cursor: 'pointer', marginBottom: 4 }}
              onClick={() => setSelectedCode(code)}
            >
              {name}
            </Tag>
          ))}
        </div>

        <QueryBoundary query={klineQ} isEmpty={(d) => d.points.length === 0}>
          {() => {
            const pts = klineQ.data?.points ?? [];
            // points come newest-first from API; reverse to chronological
            const sorted = [...pts].reverse();

            const dates = sorted.map((p) => p.date);
            // ECharts candlestick expects [open, close, low, high]
            const candlestickData = sorted.map(
              (p) => [p.open ?? 0, p.close ?? 0, p.low ?? 0, p.high ?? 0] as [number, number, number, number],
            );
            const volumeData = sorted.map((p) => p.volume ?? 0);

            const option: EChartsOption = {
              animation: false,
              tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' },
              },
              grid: [
                { left: '8%', right: '8%', top: 48, height: '50%' },
                { left: '8%', right: '8%', top: '72%', height: '18%' },
              ],
              xAxis: [
                {
                  type: 'category',
                  data: dates,
                  gridIndex: 0,
                  axisLine: { onZero: false },
                  axisLabel: { show: false },
                },
                {
                  type: 'category',
                  data: dates,
                  gridIndex: 1,
                  axisLabel: { rotate: 45, fontSize: 11 },
                },
              ],
              yAxis: [
                { type: 'value', gridIndex: 0, scale: true, splitNumber: 5 },
                { type: 'value', gridIndex: 1, splitNumber: 3, axisLabel: { show: true } },
              ],
              dataZoom: [
                {
                  type: 'inside',
                  xAxisIndex: [0, 1],
                  start: Math.max(0, 100 - (120 / dates.length) * 100),
                  end: 100,
                },
                {
                  type: 'slider',
                  xAxisIndex: [0, 1],
                  start: Math.max(0, 100 - (120 / dates.length) * 100),
                  end: 100,
                  bottom: 4,
                  height: 16,
                },
              ],
              series: [
                {
                  name: 'K线',
                  type: 'candlestick',
                  xAxisIndex: 0,
                  yAxisIndex: 0,
                  data: candlestickData,
                  itemStyle: {
                    color: '#cf1322',
                    color0: '#3f8600',
                    borderColor: '#cf1322',
                    borderColor0: '#3f8600',
                  },
                },
                {
                  name: '成交量',
                  type: 'bar',
                  xAxisIndex: 1,
                  yAxisIndex: 1,
                  data: volumeData,
                  itemStyle: {
                    color: (params: { dataIndex: number }) => {
                      const p = sorted[params.dataIndex];
                      return p && (p.close ?? 0) >= (p.open ?? 0) ? '#cf1322' : '#3f8600';
                    },
                  },
                },
              ],
            };

            return (
              <ReactEChartsCore
                echarts={echarts}
                option={option}
                style={{ height: 520 }}
                notMerge
              />
            );
          }}
        </QueryBoundary>
      </PageSection>
    </div>
  );
}
