import { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Empty, Radio, Space, Spin } from 'antd';
import echarts from '../../lib/echarts';
import { fetchKline } from '../../api/client';
import type { KlinePoint } from '../../api/types';

interface Props {
  stockCode: string;
}

const DAYS_OPTIONS = [
  { value: 90, label: '3M' },
  { value: 180, label: '6M' },
  { value: 365, label: '1Y' },
  { value: 365 * 3, label: '3Y' },
  { value: 365 * 5, label: '5Y' },
];

function computeMA(closes: (number | null)[], window: number): (number | null)[] {
  const out: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < window - 1) {
      out.push(null);
      continue;
    }
    let sum = 0;
    let valid = true;
    for (let j = 0; j < window; j++) {
      const v = closes[i - j];
      if (v == null) {
        valid = false;
        break;
      }
      sum += v;
    }
    out.push(valid ? Number((sum / window).toFixed(2)) : null);
  }
  return out;
}

export default function KlineChart({ stockCode }: Props) {
  const chartRef = useRef<ReactECharts>(null);
  const [days, setDays] = useState(365);
  const [loading, setLoading] = useState(false);
  const [points, setPoints] = useState<KlinePoint[]>([]);

  useEffect(() => {
    if (!stockCode) return;
    setLoading(true);
    fetchKline(stockCode, days)
      .then((r) => setPoints(r.points))
      .catch(() => setPoints([]))
      .finally(() => setLoading(false));
  }, [stockCode, days]);

  const option = useMemo(() => {
    if (!points.length) return null;
    const dates = points.map((p) => p.date);
    // ECharts candlestick expects [open, close, low, high]
    const candles = points.map((p) => [p.open ?? 0, p.close ?? 0, p.low ?? 0, p.high ?? 0]);
    const closes = points.map((p) => p.close);
    const volumes = points.map((p) => p.volume ?? 0);
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis' as const,
        axisPointer: { type: 'cross' as const },
      },
      legend: { data: ['K', 'MA5', 'MA20', 'MA60'], top: 0 },
      grid: [
        { left: '8%', right: '4%', top: '10%', height: '60%' },
        { left: '8%', right: '4%', top: '76%', height: '14%' },
      ],
      xAxis: [
        {
          type: 'category' as const,
          data: dates,
          gridIndex: 0,
          axisLabel: { show: false },
          axisTick: { show: false },
        },
        {
          type: 'category' as const,
          data: dates,
          gridIndex: 1,
          axisLabel: { fontSize: 10, color: '#78716C' },
        },
      ],
      yAxis: [
        { type: 'value' as const, scale: true, gridIndex: 0, splitLine: { lineStyle: { color: '#E7E5E4' } } },
        { type: 'value' as const, gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
      ],
      dataZoom: [
        { type: 'inside' as const, xAxisIndex: [0, 1], start: 60, end: 100 },
        { type: 'slider' as const, xAxisIndex: [0, 1], top: '93%', height: 18, start: 60, end: 100 },
      ],
      series: [
        {
          name: 'K',
          type: 'candlestick' as const,
          data: candles,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: {
            color: '#c73e3a',
            color0: '#3da06a',
            borderColor: '#c73e3a',
            borderColor0: '#3da06a',
          },
        },
        { name: 'MA5', type: 'line' as const, xAxisIndex: 0, yAxisIndex: 0, data: computeMA(closes, 5), showSymbol: false, lineStyle: { width: 1, color: '#4F6D93' } },
        { name: 'MA20', type: 'line' as const, xAxisIndex: 0, yAxisIndex: 0, data: computeMA(closes, 20), showSymbol: false, lineStyle: { width: 1, color: '#d4a044' } },
        { name: 'MA60', type: 'line' as const, xAxisIndex: 0, yAxisIndex: 0, data: computeMA(closes, 60), showSymbol: false, lineStyle: { width: 1, color: '#7c6cbf' } },
        {
          name: '成交量',
          type: 'bar' as const,
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          itemStyle: { color: '#a8a29e' },
        },
      ],
    };
  }, [points]);

  useEffect(() => {
    const onResize = () => chartRef.current?.getEchartsInstance()?.resize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Radio.Group
          size="small"
          value={days}
          onChange={(e) => setDays(e.target.value)}
          options={DAYS_OPTIONS}
          optionType="button"
        />
      </Space>
      {loading ? (
        <div style={{ padding: 64, textAlign: 'center' }}>
          <Spin />
        </div>
      ) : option ? (
        <ReactECharts echarts={echarts} ref={chartRef} option={option} style={{ height: 540 }} notMerge />
      ) : (
        <Empty description="无 K 线数据" />
      )}
    </div>
  );
}
