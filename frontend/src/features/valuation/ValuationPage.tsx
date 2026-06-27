import { useState } from 'react';
import {
  Card,
  Col,
  Input,
  Row,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  BarChartOutlined,
  SearchOutlined,
  PieChartOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';

import { fetchValuationDashboard, fetchValuationPercentile } from '../../api/client';
import type { ValuationSnapshotItem } from '../../api/client';
import { PageHeader } from '../../components/primitives';
import PageSection from '../../components/primitives/PageSection';
import QueryBoundary from '../../components/QueryBoundary';

const { Text } = Typography;

function fmtPct(v: number | null): string {
  return v !== null && v !== undefined ? `${v.toFixed(1)}%` : '—';
}

function fmtDecimal(v: number | null, digits = 2): string {
  return v !== null && v !== undefined ? v.toFixed(digits) : '—';
}

function PctBadge({ value }: { value: number | null }) {
  if (value === null || value === undefined) return <Tag>—</Tag>;
  const color = value < 15 ? 'green' : value < 30 ? 'lime' : value < 70 ? 'orange' : 'red';
  return <Tag color={color}>{value.toFixed(1)}%</Tag>;
}

export default function ValuationPage() {
  const [code, setCode] = useState<string>('');
  const [searchCode, setSearchCode] = useState<string>('');

  const dashQ = useQuery({
    queryKey: ['valuation', 'dashboard', searchCode],
    queryFn: () => fetchValuationDashboard(searchCode),
    enabled: searchCode.length >= 4,
    refetchInterval: 60_000,
  });

  const pctQ = useQuery({
    queryKey: ['valuation', 'percentile', searchCode],
    queryFn: () => fetchValuationPercentile(searchCode, 10),
    enabled: searchCode.length >= 4,
  });

  const handleSearch = () => {
    if (code.trim().length >= 4) {
      setSearchCode(code.trim());
    }
  };

  const snapshotColumns: ColumnsType<ValuationSnapshotItem> = [
    { title: '日期', dataIndex: 'date', width: 100 },
    { title: 'PE_TTM', dataIndex: 'pe_ttm', width: 100, align: 'right',
      render: (v: number | null) => fmtDecimal(v) },
    { title: 'PB', dataIndex: 'pb', width: 100, align: 'right',
      render: (v: number | null) => fmtDecimal(v) },
    { title: 'PE百分位(10y)', dataIndex: 'pe_percentile_10y', width: 120, align: 'right',
      render: (v: number | null) => <PctBadge value={v} /> },
    { title: 'PB百分位(10y)', dataIndex: 'pb_percentile_10y', width: 120, align: 'right',
      render: (v: number | null) => <PctBadge value={v} /> },
    { title: '股息率', dataIndex: 'dividend_yield', width: 100, align: 'right',
      render: (v: number | null) => fmtPct(v) },
  ];

  return (
    <div>
      <PageHeader
        title="估值分析"
        enLabel="Valuation"
        purpose="个股估值仪表盘：PE/PB 历史百分位、估值快照、预期股息率。"
      />

      {/* 搜索 */}
      <PageSection title={<><SearchOutlined /> 搜索股票</>}>
        <Input.Search
          placeholder="输入股票代码（如 600519）"
          enterButton="分析"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onSearch={handleSearch}
          style={{ maxWidth: 400 }}
        />
      </PageSection>

      {searchCode && (
        <QueryBoundary query={dashQ} isEmpty={(d) => !d.latest_snapshot && d.snapshots.length === 0}>
          {() => {
            const dash = dashQ.data!;
            const pct = pctQ.data;

            return (
              <>
                {/* 当前估值卡片 */}
                <PageSection title={<><BarChartOutlined /> 当前估值 ({searchCode})</>}>
                  <Row gutter={16}>
                    <Col span={4}>
                      <Card>
                        <Statistic title="当前价" value={dash.current_price ?? '—'} precision={2} prefix="¥" />
                      </Card>
                    </Col>
                    <Col span={4}>
                      <Card>
                        <Statistic title="PE_TTM" value={dash.current_pe ?? '—'} precision={2} />
                        {pct && <Text type="secondary" style={{ fontSize: 12 }}>
                          百分位: <PctBadge value={pct.current_pe_percentile} />
                        </Text>}
                      </Card>
                    </Col>
                    <Col span={4}>
                      <Card>
                        <Statistic title="PB" value={dash.current_pb ?? '—'} precision={2} />
                        {pct && <Text type="secondary" style={{ fontSize: 12 }}>
                          百分位: <PctBadge value={pct.current_pb_percentile} />
                        </Text>}
                      </Card>
                    </Col>
                    <Col span={4}>
                      <Card>
                        <Statistic title="股息率" value={dash.dividend_yield ? `${dash.dividend_yield.toFixed(2)}%` : '—'} />
                      </Card>
                    </Col>
                    <Col span={4}>
                      <Card>
                        <Statistic title="市值"
                          value={dash.market_cap !== null && dash.market_cap !== undefined ? `¥${(dash.market_cap / 1e8).toFixed(1)}亿` : '—'} />
                      </Card>
                    </Col>
                    <Col span={4}>
                      <Card>
                        <Statistic title="PE百分位" value={pct?.current_pe_percentile?.toFixed(1) ?? '—'} suffix="%" />
                      </Card>
                    </Col>
                  </Row>
                </PageSection>

                {/* 估值历史快照 */}
                <PageSection
                  title={<><PieChartOutlined /> 估值历史</>}
                  subtitle={`${dash.snapshots.length} 条记录`}
                >
                  <Table<ValuationSnapshotItem>
                    columns={snapshotColumns}
                    dataSource={dash.snapshots}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 10, size: 'small' }}
                  />
                </PageSection>
              </>
            );
          }}
        </QueryBoundary>
      )}
    </div>
  );
}
