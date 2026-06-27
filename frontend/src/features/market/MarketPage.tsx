import { useState } from 'react';
import { Card, Col, Row, Statistic, Table, Typography, Tag } from 'antd';
import {
  LineChartOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';

import { fetchMarketIndices, fetchIndexKline } from '../../api/client';
import type { MarketIndexItem } from '../../api/client';
import { PageHeader } from '../../components/primitives';
import PageSection from '../../components/primitives/PageSection';
import QueryBoundary from '../../components/QueryBoundary';

const { Text } = Typography;

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
            const recent = pts.slice(-30).reverse();

            const columns: ColumnsType<{ date: string; open: number | null; high: number | null; low: number | null; close: number | null; volume: number | null }> = [
              { title: '日期', dataIndex: 'date', width: 100 },
              { title: '开盘', dataIndex: 'open', width: 90, align: 'right', render: (v: number | null) => v?.toFixed(2) ?? '—' },
              { title: '最高', dataIndex: 'high', width: 90, align: 'right', render: (v: number | null) => v?.toFixed(2) ?? '—' },
              { title: '最低', dataIndex: 'low', width: 90, align: 'right', render: (v: number | null) => v?.toFixed(2) ?? '—' },
              { title: '收盘', dataIndex: 'close', width: 90, align: 'right', render: (v: number | null) => <Text strong>{v?.toFixed(2) ?? '—'}</Text> },
              { title: '成交量', dataIndex: 'volume', width: 100, align: 'right', render: (v: number | null) => v?.toLocaleString('zh-CN') ?? '—' },
            ];

            return (
              <Table
                columns={columns}
                dataSource={recent}
                rowKey="date"
                size="small"
                pagination={false}
              />
            );
          }}
        </QueryBoundary>
      </PageSection>
    </div>
  );
}
