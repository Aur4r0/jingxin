/* 历史交易交互；日期筛选和图表只使用本地页面数据。 */
(function () {
  const $ = id => document.getElementById(id);
  function storage(get, key, value) {
    try { return get ? sessionStorage.getItem(key) : sessionStorage.setItem(key, value); } catch (_) { return null; }
  }
  function updateDates(form) {
    const custom = form.querySelector('input[name="period"]:checked')?.value === 'custom';
    const dates = form.querySelector('#customDates');
    if (dates) dates.hidden = !custom;
    form.querySelectorAll('input[type="date"]').forEach(input => { input.required = custom; });
  }
  function submitFilters(form) {
    updateDates(form);
    if (form.reportValidity()) form.requestSubmit();
  }
  function drawDailyChart() {
    const root = $('dailyChart'), data = $('dailyChartData');
    if (!root || !data) return;
    let points;
    try { points = JSON.parse(data.textContent); } catch (_) { root.textContent = '图表数据暂时不可用，明细仍可查看。'; return; }
    root.replaceChildren();
    if (!points.length) {
      const empty = document.createElement('p'); empty.className = 'tdb-empty';
      empty.textContent = '暂无已入库成交，无法绘制盈亏。无记录不代表零盈亏。'; root.append(empty); return;
    }
    const scale = Math.max(...points.map(p => p.net === null ? 0 : Math.abs(Number(p.net))), 0.0001);
    const scaleLine = document.createElement('div'); scaleLine.className = 'tdb-chart-scale';
    scaleLine.textContent = `净交易盈亏 · USDT　　刻度 ±${scale.toFixed(4)}`; root.append(scaleLine);
    const scroller = document.createElement('div'); scroller.className = 'tdb-chart-scroll';
    const bars = document.createElement('div'); bars.className = 'tdb-bars';
    const spacer = document.createElement('div'); spacer.className = 'tdb-chart-labels';
    const tip = document.createElement('div'); tip.className = 'tdb-tooltip'; tip.hidden = true; tip.id = 'dailyChartTooltip'; tip.setAttribute('role', 'tooltip');
    for (const point of points) {
      const missing = point.net === null, value = missing ? 0 : Number(point.net);
      const state = missing ? (point.count ? '数据待核实' : '无已入库记录') : `净交易盈亏 ${point.net} USDT`;
      const bar = document.createElement('button'); bar.type = 'button'; bar.className = 'tdb-bar';
      bar.setAttribute('aria-label', `${point.date}，${state}，成交明细 ${point.count} 笔`);
      bar.setAttribute('aria-describedby', 'dailyChartTooltip');
      if (missing || value === 0) {
        const mark = document.createElement('span'); mark.className = missing ? 'tdb-bar-missing' : 'tdb-bar-zero';
        mark.textContent = missing ? '—' : ''; bar.append(mark);
      } else {
        const shape = document.createElement('span'); shape.className = `tdb-bar-value ${value > 0 ? 'positive' : 'negative'}`;
        const height = Math.max(0.7, Math.abs(value) / scale * 42);
        shape.style.height = height + '%';
        shape.style.top = (value > 0 ? 50 - height : 50) + '%';
        bar.append(shape);
      }
      const label = document.createElement('span'); label.className = 'tdb-bar-label'; label.textContent = point.date.slice(5); bar.append(label);
      const show = () => {
        tip.replaceChildren();
        const title = document.createElement('strong'); title.textContent = `${point.date} · 北京时间`; tip.append(title);
        const entries = [['已实现盈亏', point.gross], ['手续费净支出', point.fees_cost], ['净交易盈亏', point.net], ['成交明细', `${point.count} 笔`]];
        for (const [name, amount] of entries) {
          const row = document.createElement('div'), key = document.createElement('span'), content = document.createElement('span');
          key.textContent = name; content.textContent = amount === null ? (point.count ? '待核实' : '无记录') : String(amount);
          row.append(key, content); tip.append(row);
        }
        tip.hidden = false;
        const rect = bar.getBoundingClientRect(), parent = root.getBoundingClientRect();
        tip.style.left = Math.max(0, Math.min(rect.left - parent.left, parent.width - tip.offsetWidth)) + 'px';
      };
      const hide = () => { tip.hidden = true; };
      bar.addEventListener('mouseenter', show); bar.addEventListener('mouseleave', hide);
      bar.addEventListener('focus', show); bar.addEventListener('blur', hide);
      bar.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
      bars.append(bar);
    }
    scroller.append(bars, spacer); root.append(scroller, tip);
  }
  function initialize() {
    const form = $('tradeFilters'); if (form) updateDates(form);
    const details = $('tradeDetails');
    if (details && storage(true, 'jingxin-trade-details') === 'closed') details.open = false;
    drawDailyChart();
  }
  window.renderTradeChart = initialize;
  document.addEventListener('toggle', event => {
    if (event.target.id === 'tradeDetails') storage(false, 'jingxin-trade-details', event.target.open ? 'open' : 'closed');
  }, true);
  document.addEventListener('change', event => {
    const form = event.target.closest('form'); if (!form) return;
    if (form.id === 'tradeFilters') {
      updateDates(form);
      if (event.target.name === 'period' && event.target.value === 'custom') return;
      if (event.target.name === 'period' || event.target.name === 'symbol') submitFilters(form);
    } else if (form.classList.contains('tdb-page-size')) form.requestSubmit();
  });
  document.addEventListener('click', async event => {
    const button = event.target.closest('#syncFills');
    if (!button || button.disabled) return;
    button.disabled = true; button.textContent = '正在读取成交…';
    try {
      const response = await fetch('/api/trades/sync-fills', {method:'POST'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '同步失败');
      window.location.reload();
    } catch (error) {
      const message = $('monitorError'); message.hidden = false; message.textContent = error.message;
      button.disabled = false; button.textContent = '重试同步模拟盘成交';
    }
  });
  initialize();
})();
