import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Col,
  Row,
  Spin,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  message,
} from 'antd';
import { PlusOutlined, ExperimentOutlined } from '@ant-design/icons';
import { PageHeader, EmptyState } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import {
  archiveResearchTheme,
  createResearchTheme,
  listResearchThemes,
} from '../../api/client';
import type { ResearchTheme, ResearchThemeCreate } from '../../api/types';

const MARKET_OPTIONS = [
  { value: 'A_SHARE', label: 'A 股' },
  { value: 'HK', label: '港股' },
  { value: 'US', label: '美股' },
];
const FREQ_OPTIONS = [
  { value: 'manual', label: '手动' },
  { value: 'weekly', label: '每周一 8am (Asia/Shanghai)' },
  { value: 'monthly', label: '每月 1 号 8am' },
];

export default function ResearchThemesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm<ResearchThemeCreate>();

  const themesQ = useQuery({
    queryKey: ['research-themes'],
    queryFn: () => listResearchThemes(),
  });

  const createM = useMutation({
    mutationFn: (payload: ResearchThemeCreate) => createResearchTheme(payload),
    onSuccess: (theme) => {
      message.success(`已创建研究方向: ${theme.name}`);
      queryClient.invalidateQueries({ queryKey: ['research-themes'] });
      setCreateOpen(false);
      form.resetFields();
      navigate(`/research/${theme.id}`);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : '创建失败';
      message.error(msg);
    },
  });

  const archiveM = useMutation({
    mutationFn: (themeId: number) => archiveResearchTheme(themeId),
    onSuccess: () => {
      message.success('已归档');
      queryClient.invalidateQueries({ queryKey: ['research-themes'] });
    },
  });

  return (
    <div>
      <PageHeader
        title="研究方向"
        enLabel="Research"
        purpose="基于 serenity-skill 方法论的研究工作流。LLM 抓取 ≥25 sources,产出:系统变化 → 价值链 → 稀缺层 → 公司宇宙 → 证据分级 → Top 3-7 排名 → 失败条件 → 下一步验证。"
        flow={[
          { label: '研究方向' },
          { label: '候选股 (导出)' },
          { to: '/watchlist', label: '自选股' },
        ]}
        actions={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateOpen(true)}
          >
            新建研究方向
          </Button>
        }
      />

      <QueryBoundary
        query={themesQ}
        isEmpty={(themes: ResearchTheme[]) => themes.length === 0}
        emptyRender={
          <EmptyState
            variant="cold"
            title="还没有研究方向"
            description="研究方向 = serenity 工作流的输入(例如 'AI 半导体' / 'CPO 光模块')。LLM 会基于主题抓 25+ sources 并产出结构化报告。"
            cta={{
              label: '创建第一个研究方向',
              onClick: () => setCreateOpen(true),
            }}
          />
        }
      >
        {(themes: ResearchTheme[]) => (
          <Spin spinning={archiveM.isPending}>
            <Row gutter={[16, 16]}>
              {themes.map((t) => (
                <Col key={t.id} xs={24} sm={12} lg={8} xl={6}>
                  <ThemeCard
                    theme={t}
                    onClick={() => navigate(`/research/${t.id}`)}
                    onArchive={() => archiveM.mutate(t.id)}
                  />
                </Col>
              ))}
            </Row>
          </Spin>
        )}
      </QueryBoundary>

      <Modal
        title="新建研究方向"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createM.isPending}
        okText="创建"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(vals) => createM.mutate(vals)}
          initialValues={{ market: 'A_SHARE', auto_refresh_freq: 'manual' }}
        >
          <Form.Item
            name="name"
            label="研究方向"
            rules={[{ required: true, message: '请输入研究方向名称' }]}
          >
            <Input placeholder="例如:AI 半导体 / CPO / HBM" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea
              rows={2}
              placeholder="研究范围 / 重点关注的产业链层 / 时间窗"
            />
          </Form.Item>
          <Form.Item name="market" label="市场">
            <Select options={MARKET_OPTIONS} />
          </Form.Item>
          <Form.Item name="auto_refresh_freq" label="自动重跑频率">
            <Select options={FREQ_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}


// ── Theme card ─────────────────────────────────────────────────────────

function ThemeCard({
  theme,
  onClick,
  onArchive,
}: {
  theme: ResearchTheme;
  onClick: () => void;
  onArchive: () => void;
}) {
  const statusColor =
    theme.status === 'active' ? 'green' :
    theme.status === 'archived' ? 'default' : 'orange';
  const runStatusColor =
    theme.last_run_status === 'completed' ? 'green' :
    theme.last_run_status === 'failed' ? 'red' :
    theme.last_run_status === 'running' ? 'blue' : 'default';

  return (
    <div
      style={{
        background: '#FFFFFF',
        border: '1px solid #E7E5E4',
        borderRadius: 6,
        padding: 16,
        cursor: 'pointer',
        height: '100%',
      }}
      onClick={onClick}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ExperimentOutlined style={{ color: '#4F6D93' }} />
          <strong style={{ fontSize: 15 }}>{theme.name}</strong>
        </div>
        <Tag color={statusColor}>{theme.status}</Tag>
      </div>
      <div style={{ marginTop: 8, color: '#57534E', fontSize: 13, minHeight: 36 }}>
        {theme.description ?? <em style={{ color: '#A8A29E' }}>无描述</em>}
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <Tag>{theme.market}</Tag>
        <Tag color="purple">{theme.auto_refresh_freq}</Tag>
        {theme.last_run_status && (
          <Tag color={runStatusColor}>last: {theme.last_run_status}</Tag>
        )}
      </div>
      {theme.last_run_at && (
        <div style={{ marginTop: 8, fontSize: 12, color: '#78716C' }}>
          最近: {new Date(theme.last_run_at).toLocaleString('zh-CN')}
        </div>
      )}
      <div style={{ marginTop: 12, textAlign: 'right' }}>
        <Button
          type="link"
          danger
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            onArchive();
          }}
        >
          归档
        </Button>
      </div>
    </div>
  );
}
