import { Link } from 'react-router-dom';
import { Card, Col, Row, Statistic, Table, Typography } from 'antd';
import {
  DollarOutlined,
  HistoryOutlined,
  PieChartOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import type { ColumnsType } from 'antd/es/table';

import { fetchDividendSummary, listDividendRecords } from '../../api/client';
import type { DividendRecordResponse, DividendSummaryResponse } from '../../api/types';
import { PageHeader } from '../../components/primitives';
import PageSection from '../../components/primitives/PageSection';
import QueryBoundary from '../../components/QueryBoundary';

const { Text } = Typography;

function fmtCurrency(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`;
}

const RECORD_COLUMNS: ColumnsType<DividendRecordResponse> = [
  {
    title: '股票',
    dataIndex: 'stock_code',
    width: 90,
    render: (code: string) => <Link to={`/stock/${code}`}><Text code>{code}</Text></Link>,
  },
  { title: '名称', dataIndex: 'stock_name', width: 120, ellipsis: true },
  { title: '除息日', dataIndex: 'ex_date', width: 100 },
  {
    title: '每股股息',
    dataIndex: 'amount_per_share',
    width: 100,
    align: 'right',
    render: (v: number) => fmtCurrency(v),
  },
  {
    title: '持有数量',
    dataIndex: 'quantity_held',
    width: 100,
    align: 'right',
    render: (q: number) => q.toLocaleString('zh-CN'),
  },
  {
    title: '实收金额',
    dataIndex: 'total_received',
    width: 120,
    align: 'right',
    render: (v: number) => <Text strong>{fmtCurrency(v)}</Text>,
  },
  {
    title: '再投资',
    dataIndex: 'reinvested',
    width: 80,
    render: (v: boolean | null) => v ? '是' : '否',
  },
];

function YearSummary({ summary }: { summary: DividendSummaryResponse }) {
  const yearCols: ColumnsType<{ year: number; total_received: number; count: number }> = [
    { title: '年份', dataIndex: 'year', width: 80 },
    { title: '实收总额', dataIndex: 'total_received', width: 120, align: 'right',
      render: (v: number) => fmtCurrency(v) },
    { title: '次数', dataIndex: 'count', width: 60, align: 'right' },
  ];

  const stockCols: ColumnsType<{ stock_code: string; stock_name: string | null; total_received: number; count: number; annual_yield: number | null }> = [
    { title: '股票', dataIndex: 'stock_code', width: 90,
      render: (code: string) => <Link to={`/stock/${code}`}><Text code>{code}</Text></Link> },
    { title: '名称', dataIndex: 'stock_name', width: 120, ellipsis: true },
    { title: '累计股息', dataIndex: 'total_received', width: 120, align: 'right',
      render: (v: number) => fmtCurrency(v) },
    { title: '次数', dataIndex: 'count', width: 60, align: 'right' },
    { title: '年化收益率', dataIndex: 'annual_yield', width: 100, align: 'right',
      render: (v: number | null) => v !== null ? `${v.toFixed(2)}%` : '—' },
  ];

  return (
    <>
      <PageSection title={<><PieChartOutlined /> 年度汇总</>}>
        <Table
          columns={yearCols}
          dataSource={summary.by_year}
          rowKey="year"
          size="small"
          pagination={false}
        />
      </PageSection>

      <PageSection title={<><HistoryOutlined /> 个股汇总</>}>
        <Table
          columns={stockCols}
          dataSource={summary.by_stock}
          rowKey="stock_code"
          size="small"
          pagination={false}
        />
      </PageSection>
    </>
  );
}

export default function DividendPage() {
  const summaryQ = useQuery({
    queryKey: ['dividends', 'summary'],
    queryFn: fetchDividendSummary,
    refetchInterval: 60_000,
  });

  const recordsQ = useQuery({
    queryKey: ['dividends', 'records'],
    queryFn: () => listDividendRecords(),
    refetchInterval: 60_000,
  });

  return (
    <div>
      <PageHeader
        title="股息红利"
        enLabel="Dividends"
        purpose="记录所有收到的股息分红，按年度和个股汇总统计。"
      />

      <QueryBoundary query={summaryQ}>
        {() => {
          const summary = summaryQ.data!;
          return (
            <>
              {/* 总览统计 */}
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={8}>
                  <Card>
                    <Statistic
                      title="累计股息收入"
                      value={summary.total_cumulative}
                      precision={2}
                      prefix={<DollarOutlined />}
                      suffix="元"
                    />
                  </Card>
                </Col>
                <Col span={8}>
                  <Card>
                    <Statistic
                      title="分红股票数"
                      value={summary.by_stock.length}
                      prefix={<PieChartOutlined />}
                    />
                  </Card>
                </Col>
                <Col span={8}>
                  <Card>
                    <Statistic
                      title="分红年度数"
                      value={summary.by_year.length}
                      prefix={<HistoryOutlined />}
                    />
                  </Card>
                </Col>
              </Row>

              {/* 年度 + 个股汇总 */}
              <YearSummary summary={summary} />
            </>
          );
        }}
      </QueryBoundary>

      {/* 分红明细记录 */}
      <PageSection
        title={<><HistoryOutlined /> 分红明细</>}
        extra={
          <Text type="secondary">
            {recordsQ.data?.length ?? 0} 条记录
          </Text>
        }
      >
        <QueryBoundary query={recordsQ} isEmpty={(data) => data.length === 0}>
          {() => (
            <Table<DividendRecordResponse>
              columns={RECORD_COLUMNS}
              dataSource={recordsQ.data!}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 20, size: 'small' }}
              scroll={{ x: 800 }}
            />
          )}
        </QueryBoundary>
      </PageSection>
    </div>
  );
}
