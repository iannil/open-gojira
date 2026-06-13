import { useState } from 'react';
import { Button, Col, Empty, Row, Spin } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import PageHeader from '../../components/PageHeader';
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
        title="筛选预案"
        enLabel="Plans"
        extra={
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
        emptyRender={<Empty description="暂无预案" />}
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
