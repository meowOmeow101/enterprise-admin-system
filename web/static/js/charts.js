/* ==========================================================================
   图表封装：基于本地 ECharts，统一配色与自适应
   ========================================================================== */
(function () {
  'use strict';

  const PALETTE = ['#2b6cb0', '#2f855a', '#d69e2e', '#805ad5', '#c53030',
                   '#2c7a7b', '#dd6b20', '#4c51bf', '#38a169', '#718096'];

  const Charts = {
    palette: PALETTE,

    /** 生成一个图表组件：option 变化时自动重绘，窗口缩放时自适应 */
    make: function (name, buildOption) {
      const comp = {
        props: {
          data: { type: [Object, Array], default: null },
          height: { type: String, default: '' },
        },
        data: function () { return { chart: null }; },
        mounted: function () {
          this.chart = echarts.init(this.$refs.el);
          this.render();
          this._resize = () => this.chart && this.chart.resize();
          window.addEventListener('resize', this._resize);
        },
        unmounted: function () {
          window.removeEventListener('resize', this._resize);
          if (this.chart) { this.chart.dispose(); this.chart = null; }
        },
        watch: {
          data: { deep: true, handler: function () { this.render(); } },
        },
        methods: {
          render: function () {
            if (!this.chart) return;
            const opt = buildOption(this.data || {});
            this.chart.setOption(opt, true);
          },
        },
        template: '<div ref="el" class="chart" :style="height ? { height: height } : {}"></div>',
      };
      Charts[name] = comp;
      return comp;
    },
  };

  /* ---------------------------------------------------------- 通用坐标轴样式 */
  const axisStyle = {
    axisLine: { lineStyle: { color: '#e3e8ef' } },
    axisTick: { show: false },
    axisLabel: { color: '#6b7280', fontSize: 11 },
    splitLine: { lineStyle: { color: '#f1f5f9' } },
  };

  const tooltipStyle = {
    backgroundColor: 'rgba(31,41,55,.92)',
    borderWidth: 0,
    textStyle: { color: '#fff', fontSize: 12 },
  };

  /* ---------------------------------------------------------- 饼图 / 环形图 */
  Charts.make('PieChart', function (data) {
    const items = Object.keys(data || {}).map(function (k) { return { name: k, value: data[k] }; });
    return {
      color: PALETTE,
      tooltip: Object.assign({ trigger: 'item', formatter: '{b}：{c}（{d}%）' }, tooltipStyle),
      legend: {
        type: 'scroll', bottom: 0, itemWidth: 9, itemHeight: 9,
        textStyle: { color: '#6b7280', fontSize: 11 },
      },
      series: [{
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold', formatter: '{b}\n{c}' } },
        data: items.length ? items : [{ name: '暂无数据', value: 1, itemStyle: { color: '#edf2f7' } }],
      }],
    };
  });

  /* ---------------------------------------------------------- 柱状图 */
  Charts.make('BarChart', function (data) {
    const keys = Object.keys(data || {});
    const values = keys.map(function (k) { return data[k]; });
    return {
      color: PALETTE,
      tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, tooltipStyle),
      grid: { left: 8, right: 16, top: 20, bottom: 8, containLabel: true },
      xAxis: Object.assign({
        type: 'category',
        data: keys,
        axisLabel: { color: '#6b7280', fontSize: 11, interval: 0, rotate: keys.length > 6 ? 30 : 0 },
      }, { axisLine: axisStyle.axisLine, axisTick: axisStyle.axisTick }),
      yAxis: Object.assign({ type: 'value', minInterval: 1 }, axisStyle),
      series: [{
        type: 'bar',
        data: values,
        barMaxWidth: 34,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#2b6cb0' },
        label: { show: true, position: 'top', color: '#6b7280', fontSize: 11 },
      }],
    };
  });

  /* ---------------------------------------------------------- 折线 / 面积图 */
  Charts.make('LineChart', function (data) {
    const keys = Object.keys(data || {});
    const values = keys.map(function (k) { return data[k]; });
    return {
      color: PALETTE,
      tooltip: Object.assign({ trigger: 'axis' }, tooltipStyle),
      grid: { left: 8, right: 18, top: 22, bottom: 8, containLabel: true },
      xAxis: Object.assign({ type: 'category', boundaryGap: false, data: keys }, axisStyle),
      yAxis: Object.assign({ type: 'value', minInterval: 1 }, axisStyle),
      series: [{
        type: 'line',
        data: values,
        smooth: true,
        symbolSize: 6,
        lineStyle: { width: 2.5, color: '#2b6cb0' },
        itemStyle: { color: '#2b6cb0' },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: 'rgba(43,108,176,.26)' },
                         { offset: 1, color: 'rgba(43,108,176,.02)' }],
          },
        },
      }],
    };
  });

  /* ---------------------------------------------------------- 横向条形图 */
  Charts.make('HBarChart', function (data) {
    const entries = Object.keys(data || {}).map(function (k) { return [k, data[k]]; });
    entries.sort(function (a, b) { return a[1] - b[1]; });     // 小的在下面，视觉更自然
    const names = entries.map(function (e) { return e[0]; });
    const values = entries.map(function (e) { return e[1]; });
    return {
      tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, tooltipStyle),
      grid: { left: 8, right: 30, top: 12, bottom: 8, containLabel: true },
      xAxis: Object.assign({ type: 'value', minInterval: 1 }, axisStyle),
      yAxis: Object.assign({
        type: 'category', data: names,
        axisLabel: { color: '#6b7280', fontSize: 11 },
      }, { axisLine: axisStyle.axisLine, axisTick: axisStyle.axisTick, splitLine: { show: false } }),
      series: [{
        type: 'bar',
        data: values,
        barMaxWidth: 18,
        itemStyle: { borderRadius: [0, 4, 4, 0], color: '#2c7a7b' },
        label: { show: true, position: 'right', color: '#6b7280', fontSize: 11 },
      }],
    };
  });

  window.Charts = Charts;
})();
