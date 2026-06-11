/**
 * Slim ECharts bundle — only the chart types & components the autopilot
 * actually renders are pulled in. Passing the resulting instance to
 * `ReactECharts` via `echarts={...}` lets vite tree-shake the rest.
 *
 * Currently used:
 *  - CandlestickChart + LineChart  → StockDetail K-line tab
 *  - PieChart                       → Cockpit four-quadrant pie
 */
import * as echarts from 'echarts/core';
import { CandlestickChart, LineChart, PieChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  CandlestickChart,
  LineChart,
  PieChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

export default echarts;
