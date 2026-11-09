/* 页面监控仅 GET 当前页面；不触发交易所同步或执行策略。 */
(function(){
  const toolbar=document.querySelector('[data-monitor-interval]');if(!toolbar)return;
  const auto=document.getElementById('monitorAuto'),status=document.getElementById('monitorStatus'),error=document.getElementById('monitorError'),button=document.getElementById('monitorRefresh');
  const interval=Number(toolbar.dataset.monitorInterval)*1000;
  let timer,controller,inFlight=false,lastRead=new Date(),failed=false,disposed=false;
  try{auto.checked=localStorage.getItem('monitor-auto')!=='off';}catch(_){}
  const time=date=>date.toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
  function drawState(){status.textContent=`${document.hidden?'后台已暂停':auto.checked?'自动刷新已开启':'自动刷新已关闭'} · 页面读取 ${time(lastRead)}${failed?' · 数据可能已过期':''}`;}
  function markRecordAge(){document.querySelectorAll('[data-record-time]').forEach(el=>{const date=new Date(el.dataset.recordTime);if(!Number.isFinite(date.getTime()))return;const old=Date.now()-date.getTime()>10*60*1000;el.classList.toggle('monitor-old',old);el.title=old?'该记录超过 10 分钟未更新，请检查账户配置和后台同步。':'记录时间（北京时间）';el.textContent=date.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+(old?' · 较旧':'');});}
  async function refreshRuntime(){
    let node=document.getElementById('runtimeNotice');
    if(!node){node=document.createElement('div');node.id='runtimeNotice';node.className='monitor-error';node.setAttribute('role','status');toolbar.after(node);}
    try{const response=await fetch('/api/runtime/status',{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();const failures=Object.entries(data).filter(([,v])=>!v.ok);node.hidden=!failures.length;node.textContent=failures.map(([name,v])=>`${name==='positions'?'持仓同步':name==='fills'?'成交同步':name.startsWith('protection:')?'订单保护':'账户余额'}：${v.message}（最近检查 ${new Date(v.checked_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}）`).join('；');}catch(_){node.hidden=false;node.textContent='运行状态暂时无法读取，请检查登录或网络。';}
  }
  function drawChart(){const node=document.getElementById('monitorChartData');if(!node || !window.renderOverviewChart)return;const data=JSON.parse(node.textContent).map(d=>({time:d.time || d.timestamp+(d.timestamp.endsWith('Z')?'':'Z'),equity:d.equity ?? d.total_equity}));renderOverviewChart(data);}
  function schedule(){clearTimeout(timer);if(!disposed && auto.checked && !document.hidden)timer=setTimeout(()=>refresh(false),interval);}
  function busy(){return !!document.querySelector('dialog[open],.modal.show,#monitorContent button:disabled') || document.querySelector('#monitorContent')?.contains(document.activeElement);}
  async function refresh(manual=false){
    if(inFlight || document.hidden || (!manual && busy())){schedule();return;}
    inFlight=true;button.disabled=true;status.textContent='正在读取最新页面数据…';controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(location.pathname+location.search,{credentials:'same-origin',cache:'no-store',signal:controller.signal});
      if(response.status===401 || new URL(response.url).pathname==='/login'){auto.checked=false;throw new Error('登录已失效，请重新登录后刷新。');}
      if(!response.ok)throw new Error(`服务返回 ${response.status}，请稍后重试。`);
      const doc=new DOMParser().parseFromString(await response.text(),'text/html');const next=doc.getElementById('monitorContent');if(!next)throw new Error('页面内容不完整，请稍后重试。');
      const chartData=next.querySelector('#monitorChartData');if(chartData)JSON.parse(chartData.textContent);
      // 请求期间用户打开了详情或准备操作时，不替换其正在查看的内容。
      if(busy()){schedule();return;}
      if(window.disposeOverviewChart)window.disposeOverviewChart();
      document.getElementById('monitorContent').replaceChildren(...next.childNodes);
      refreshRuntime();lastRead=new Date();failed=false;error.hidden=true;markRecordAge();
      try{drawChart();}catch(_){error.hidden=false;error.textContent='页面数据已更新，图表暂时不可用，请刷新重试。';}
    }catch(e){if(document.hidden && e.name==='AbortError')return;failed=true;error.hidden=false;error.textContent=(e.name==='AbortError'?'读取超时。':e.message)+' 已保留上次页面数据。';}
    finally{clearTimeout(timeout);controller=null;inFlight=false;button.disabled=false;drawState();schedule();}
  }
  window.refreshMonitor=()=>refresh(true);
  button.addEventListener('click',()=>refresh(true));
  auto.addEventListener('change',()=>{try{localStorage.setItem('monitor-auto',auto.checked?'on':'off');}catch(_){}drawState();schedule();});
  document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if(document.hidden)controller?.abort();drawState();if(!document.hidden && auto.checked)refresh(false);});
  window.addEventListener('pagehide',()=>{disposed=true;clearTimeout(timer);controller?.abort();});
  try{drawChart();}catch(_){error.hidden=false;error.textContent='图表暂时不可用，请检查网络后刷新。';}
  markRecordAge();drawState();schedule();if(typeof document.createElement==='function')refreshRuntime();
})();
