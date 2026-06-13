import { useState } from 'react';
import { Button, Col, Row, Spin } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { PageHeader, EmptyState } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { usePlansQuery, useStrategiesQuery } from './usePlanQueries';
import {
  useCreatePlanMutation,
  useDeletePlanMutation,
  useRunPlanMutation,
  useTogglePlanMutation,
} from './usePlanMutations';
import PlanCard from './components/PlanCard';
import CreatePlanModal from './components/CreatePlanModal';

export default function PlansPage() {
  const [createOpen, setCreateOpen] = useState(false);

  const plansQ = usePlansQuery();
  const strategiesQ = useStrategiesQuery();
  const createM = useCreatePlanMutation();
  const runM = useRunPlanMutation();
  const toggleM = useTogglePlanMutation();
  const deleteM = useDeletePlanMutation();

  return (
    <div>
      <PageHeader
        title="预案"
        enLabel="Plans"
        purpose="预案 = 把一个或多个策略绑到一组股票上，运行后自动产出候选股。是「策略」到「候选池」之间的执行单元。"
        flow={[
          { to: '/strategies', label: '策略库' },
          { label: '预案' },
          { to: '/candidates', label: '候选池' },
          { to: '/trades', label: '成交流水' },
        ]}
        actions={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateOpen(true)}
          >
            新建预案
          </Button>
        }
      />

      <QueryBoundary
        query={plansQ}
        isEmpty={(plans) => plans.length === 0}
        emptyRender={
          <EmptyState
            variant="cold"
            title="还没有预案"
            description="预案 = 把一个或多个策略绑到一组股票上。先去策略库确认有可用策略，再回来创建第一个预案。"
            cta={{
              label: '创建第一个预案',
              onClick: () => setCreateOpen(true),
            }}
          />
        }
      >
        {(plans) => (
          <Spin spinning={runM.isPending || toggleM.isPending || deleteM.isPending}>
            <Row gutter={[16, 16]}>
              {plans.map((p) => (
                <Col key={p.id} xs={24} sm={12} lg={8}>
                  <PlanCard
                    plan={p}
                    strategies={strategiesQ.data ?? []}
                    onRun={() => runM.mutate(p.id)}
                    onToggle={() =>
                      toggleM.mutate({
                        id: p.id,
                        status: p.status === 'active' ? 'paused' : 'active',
                      })
                    }
                    onDelete={() => deleteM.mutate(p.id)}
                  />
                </Col>
              ))}
            </Row>
          </Spin>
        )}
      </QueryBoundary>

      <CreatePlanModal
        open={createOpen}
        strategies={strategiesQ.data}
        submitting={createM.isPending}
        onCancel={() => setCreateOpen(false)}
        onSubmit={async (payload) => {
          await createM.mutateAsync(payload);
          setCreateOpen(false);
        }}
      />
    </div>
  );
}
