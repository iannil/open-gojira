import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Input, Popconfirm, Progress, Space, Table, Tag, Typography, Statistic } from 'antd';
import { PlusOutlined, DeleteOutlined, CopyOutlined, SyncOutlined, SearchOutlined, CloudServerOutlined } from '@ant-design/icons';

import { startPipelineRun } from '../../api/client';
import type { StockPoolItem, UniverseCoverageStats } from '../../api/types';
import { DATA_TYPE_LABELS, type DataTypeKey } from './constants';
import { useStockPool } from './hooks/useStockPool';
import { useAntdStatic } from '../../hooks/useAntdStatic';

const { Text } = Typography;

interface Props {
  refreshKey: number;
  coverageStats?: UniverseCoverageStats | null;
}

const TIER_MAP: Record<string, { label: string; color: string }> = {
  core: { label: '核心', color: 'gold' },
  watch: { label: '关注', color: 'blue' },
  focus: { label: '重点', color: 'green' },
};

export default function StockPoolManagement({ refreshKey, coverageStats }: Props) {
  const { message } = useAntdStatic();
  const {
    pool, loading, searchResults, searching,
    selectedRowKeys, setSelectedRowKeys,
    loadPool, doSearch, doAdd, doRemove,
  } = useStockPool();

  const [keyword, setKeyword] = useState('');
  const isFullCoverage = coverageStats?.mode === 'full_coverage';

  useEffect(() => { loadPool(); }, [loadPool, refreshKey]);

  const handleSearch = useCallback(() => {
    doSearch(keyword);
  }, [doSearch, keyword]);

  const handleAdd = useCallback((code: string) => {
    doAdd([code]);
  }, [doAdd]);

  const handleBatchRemove = useCallback(async () => {
    if (selectedRowKeys.length === 0) return;
    await doRemove(selectedRowKeys);
  }, [selectedRowKeys, doRemove]);

  const handleBatchSync = useCallback(async (dtype: DataTypeKey) => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择股票');
      return;
    }
    try {
      await startPipelineRun(dtype, { stock_codes: selectedRowKeys });
      message.success(`已启动 ${DATA_TYPE_LABELS[dtype]} 同步 (${selectedRowKeys.length} 只)`);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || '启动同步失败');
    }
  }, [selectedRowKeys]);

  const handleCopy = useCallback(() => {
    const codes = selectedRowKeys.length > 0 ? selectedRowKeys : pool.map((s) => s.code);
    navigator.clipboard.writeText(codes.join(', '));
    message.success(`已复制 ${codes.length} 个代码`);
  }, [selectedRowKeys, pool]);

  const completenessPct = (item: StockPoolItem) => {
    const c = item.data_completeness;
    const total = 4;
    const done = [c.has_valuation, c.has_financial, c.has_kline, c.has_dividend].filter(Boolean).length;
    return Math.round((done / total) * 100);
  };

  const completeCount = pool.filter((s) => {
    const c = s.data_completeness;
    return c.has_valuation && c.has_financial && c.has_kline && c.has_dividend;
  }).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {isFullCoverage && coverageStats && (
        <Card size="small">
          <Space size={32}>
            <Statistic
              title="全市场股票"
              value={coverageStats.total_stocks}
              prefix={<CloudServerOutlined />}
              valueStyle={{ fontSize: 20 }}
            />
            <Statistic
              title="今日估值覆盖"
              value={coverageStats.valuation_coverage}
              suffix={`/ ${coverageStats.total_stocks}`}
              valueStyle={{ fontSize: 20 }}
            />
            <Statistic
              title="覆盖率"
              value={coverageStats.coverage_pct}
              suffix="%"
              valueStyle={{ fontSize: 20, color: coverageStats.coverage_pct > 90 ? '#16A34A' : '#D97706' }}
            />
          </Space>
        </Card>
      )}

      {!isFullCoverage && (
        <Card title="搜索添加" size="small">
          <Space>
            <Input.Search
              placeholder="输入股票代码或名称"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={handleSearch}
              loading={searching}
              style={{ width: 300 }}
              enterButton={<SearchOutlined />}
            />
          </Space>
          {searchResults.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">搜索结果（点击添加）：</Text>
              <div style={{ marginTop: 4 }}>
                {searchResults.map((s) => (
                  <Tag
                    key={s.code}
                    style={{ cursor: 'pointer', marginBottom: 4 }}
                    onClick={() => handleAdd(s.code)}
                  >
                    <PlusOutlined /> {s.code} {s.name}
                  </Tag>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      <Card
        title={
          <Space>
            <span>{isFullCoverage ? '全市场股票' : '股票池'}</span>
            <Text type="secondary">{pool.length} 只，{completeCount} 只数据完整</Text>
          </Space>
        }
        size="small"
        extra={
          <Space>
            {selectedRowKeys.length > 0 && (
              <>
                <Text>{selectedRowKeys.length} 已选</Text>
                <Popconfirm title={`移除 ${selectedRowKeys.length} 只股票？`} onConfirm={handleBatchRemove}>
                  <Button size="small" danger icon={<DeleteOutlined />}>批量移除</Button>
                </Popconfirm>
                <Button size="small" icon={<SyncOutlined />} onClick={() => handleBatchSync('valuations')}>批量同步估值</Button>
                <Button size="small" icon={<CopyOutlined />} onClick={handleCopy}>复制代码</Button>
              </>
            )}
          </Space>
        }
      >
        <Table
          dataSource={pool}
          rowKey="code"
          loading={loading}
          size="small"
          pagination={{ pageSize: 15, showSizeChanger: true }}
          rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]) }}
          scroll={{ x: 800 }}
          columns={[
            {
              title: '代码',
              dataIndex: 'code',
              width: 100,
              sorter: (a, b) => a.code.localeCompare(b.code),
              render: (v: string) => <Text code style={{ cursor: 'pointer' }}>{v}</Text>,
            },
            {
              title: '名称',
              dataIndex: 'name',
              width: 100,
              sorter: (a, b) => a.name.localeCompare(b.name),
            },
            {
              title: '行业',
              dataIndex: 'industry',
              width: 120,
              ellipsis: true,
            },
            {
              title: '等级',
              dataIndex: 'tier',
              width: 70,
              render: (v: string | null) => {
                const t = TIER_MAP[v ?? ''];
                return t ? <Tag color={t.color}>{t.label}</Tag> : '-';
              },
            },
            {
              title: '数据完整度',
              width: 150,
              render: (_: unknown, r: StockPoolItem) => {
                const pct = completenessPct(r);
                return <Progress percent={pct} size="small" />;
              },
            },
            {
              title: '添加时间',
              dataIndex: 'added_at',
              width: 150,
              render: (v: string | null) => v ? new Date(v).toLocaleDateString('zh-CN') : '-',
            },
          ]}
        />
      </Card>
    </div>
  );
}
