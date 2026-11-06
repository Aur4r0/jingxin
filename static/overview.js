/* 只读净值图表。 */
let overviewChartInstance = null;
let overviewThemeListener = null;
function disposeOverviewChart(){if(overviewChartInstance)overviewChartInstance.destroy();overviewChartInstance=null;if(overviewThemeListener)window.removeEventListener('themechange',overviewThemeListener);overviewThemeListener=null;}
function renderOverviewChart(data) {
  disposeOverviewChart();
  const canvas = document.getElementById('equityChart');
  const summary = document.getElementById('chartSummary');
  if (!canvas || !data.length) return;
  if (typeof Chart === 'undefined') { summary.textContent = '图表加载失败，请检查网络后刷新。'; return; }
  const number = value => Number(value).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
  const first = data[0].equity, last = data[data.length - 1].equity, change = last - first;
  const caption = document.createElement('span');
  caption.textContent = `期初 ${number(first)} → 期末 ${number(last)} USDT`;
  const delta = document.createElement('span');
  delta.textContent = `区间变化 ${change >= 0 ? '+' : ''}${number(change)}${first > 0 ? `（${(change/first*100).toFixed(2)}%）` : ''}`;
  delta.className = change > 0 ? 'overview-positive' : change < 0 ? 'text-danger' : '';
  summary.replaceChildren(caption, delta);
  const color = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const chart = new Chart(canvas, {
    type:'line', data:{labels:data.map(d => new Date(d.time).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})), datasets:[{label:'账户权益 · USDT',data:data.map(d=>d.equity),borderWidth:2.5,pointRadius:data.length===1?4:0,pointHoverRadius:4,tension:0,fill:true}]},
    options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{intersect:false,mode:'index'},plugins:{legend:{display:false},tooltip:{callbacks:{label:context=>`${number(context.parsed.y)} USDT`}}},scales:{x:{grid:{display:false},ticks:{maxTicksLimit:5,maxRotation:0}},y:{title:{display:true,text:'账户权益 · USDT'},ticks:{callback:value=>number(value)}}}}
  });
  function updateColors(){const line=chart.data.datasets[0];line.borderColor=color('--chart-line');line.backgroundColor=color('--chart-line')+'12';for(const axis of Object.values(chart.options.scales)){axis.ticks.color=color('--text-2');axis.grid.color=color('--border');if(axis.title)axis.title.color=color('--text-2');}chart.update('none');}
  overviewChartInstance=chart;overviewThemeListener=updateColors;updateColors();window.addEventListener('themechange',updateColors);
}
