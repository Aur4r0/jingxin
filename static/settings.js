let savedEnvironment;
const accountForm = document.getElementById('configForm');
const simSwitch = document.getElementById('simSwitch');
savedEnvironment = simSwitch.checked;
const secretNames = new Set(['okx_live_api_key','okx_live_secret_key','okx_live_passphrase','okx_sim_api_key','okx_sim_secret_key','okx_sim_passphrase','ai_default_api_key','tg_bot_token','binance_live_api_key','binance_live_secret_key','binance_sim_api_key','binance_sim_secret_key']);
let revealOther = false;
function toggleSimWarning(){
  document.getElementById('simLabel').textContent = `${simSwitch.checked===savedEnvironment?'已保存环境':'待保存环境'}：${simSwitch.checked ? '模拟盘' : '实盘'}${simSwitch.checked !== savedEnvironment ? '（尚未生效）' : ''}`;
  document.getElementById('liveWarning').classList.toggle('d-none',simSwitch.checked);
  const sections = document.querySelectorAll('.credential-section');
  sections.forEach((section,index)=>{section.hidden = !revealOther && (simSwitch.checked ? index===0 : index===1);});
}
function showOtherCredentials(){revealOther=!revealOther;document.getElementById('otherCredentials').setAttribute('aria-expanded',String(revealOther));document.getElementById('otherCredentials').textContent=revealOther?'收起另一套账户凭据':'展开另一套账户凭据';toggleSimWarning();}
function feedback(form,message,error=false){const el=form.querySelector(':scope > .settings-feedback');el.textContent=message;el.className=`settings-feedback ${error?'text-danger':'text-success'}`;el.setAttribute('role',error?'alert':'status');if(!error){form.dataset.dirty='false';const state=form.querySelector('[data-save-state]');if(state)state.textContent='已保存 · 连接状态以测试结果为准';}}
async function saveSection(event,form){
  event.preventDefault(); const button=form.querySelector('[type="submit"]');
  const payload={};for(const [key,value] of new FormData(form)){if(secretNames.has(key) && !value.trim())continue;payload[key]=value;}
  if(form.dataset.section==='account'){
    payload.okx_simulated=simSwitch.checked;
    if(payload.okx_simulated!==savedEnvironment){
      if(!await confirmAction({title:`切换为${payload.okx_simulated?'模拟盘':'实盘'}`,detail:'保存后，启用中的策略后续执行将使用新环境；旧环境的持仓不会自动关闭或迁移。建议先暂停策略并检查两套账户。',confirmText:'确认切换',danger:!payload.okx_simulated}))return;
    }
  }
  setLoading(button,true);
  try{
    const config=await api('PUT','/system/config',payload);
    if(form.dataset.section==='account'){savedEnvironment=config.okx_simulated;document.getElementById('savedLiveWarning')?.classList.toggle('d-none',config.okx_simulated);toggleSimWarning();const label=document.getElementById('environmentLabel');label.textContent=config.okx_simulated?'OKX · 模拟盘':'OKX · 实盘';label.classList.toggle('pp-live',!config.okx_simulated);}
    form.querySelectorAll('input[type="password"]').forEach(input=>{if(input.value){input.value='';input.placeholder='已设置，留空保留';}});
    const summary=form.closest('details')?.querySelector('summary span');
    if(summary && form.dataset.section==='ai')summary.textContent=`${config.ai_default_provider} · ${config.ai_default_model} · 点击编辑`;
    if(summary && form.dataset.section==='notification')summary.textContent=`${config.tg_bot_token_set ? '已配置机器人' : '未配置'} · Telegram · 点击编辑`;
    feedback(form,'本区域配置已保存。其他区域未修改。');
  }catch(error){feedback(form,'保存失败：'+error.message+'。输入内容已保留，请检查后重试。',true);}finally{setLoading(button,false);}
}
async function testConnection(button){
  const result=document.getElementById('connResult');result.className='settings-feedback';result.textContent='正在测试已保存的交易账户…';setLoading(button,true);
  try{const data=await api('POST','/system/test-connection');result.textContent=`${data.mode || ''} · ${data.message}`;result.classList.add(data.ok?'text-success':'text-danger');if(!data.ok)result.textContent+=' 请检查已保存的账户环境、凭据权限和代理连接。';}catch(error){result.textContent='连接测试失败：'+error.message+'。请检查网络与已保存配置。';result.classList.add('text-danger');}finally{setLoading(button,false);}
}
async function testTelegram(button){
  const fd=new FormData(document.getElementById('notificationForm'));const result=document.getElementById('tgTestResult');result.className='settings-feedback';result.textContent='正在发送测试消息…';setLoading(button,true);
  try{const data=await api('POST','/system/test-telegram',Object.fromEntries(fd));result.textContent=data.message;result.classList.add(data.ok?'text-success':'text-danger');}catch(error){result.textContent='测试消息发送失败：'+error.message+'。请检查机器人、接收人和代理设置。';result.classList.add('text-danger');}finally{setLoading(button,false);}
}
function renderPositionMode(mode){document.getElementById('positionModeBadge').textContent=mode==='long_short_mode'?'双向持仓':'单向持仓';document.getElementById('positionModeSelect').value=mode;}
async function loadPositionMode(){try{const data=await api('GET','/system/position-mode');renderPositionMode(data.mode);}catch(error){document.getElementById('positionModeBadge').textContent='读取失败';document.getElementById('positionModeTip').textContent='无法读取已保存账户的持仓模式：'+error.message;}}
async function setPositionMode(){
  const mode=document.getElementById('positionModeSelect').value;const label=mode==='long_short_mode'?'双向持仓':'单向持仓';
  if(!await confirmAction({title:'修改账户持仓模式',detail:`将已保存账户切换为${label}，会直接修改交易所账户设置。存在持仓或挂单时，交易所可能拒绝操作。此操作不使用尚未保存的账户配置。`,confirmText:'应用持仓模式',danger:true}))return;
  const button=document.getElementById('setPositionModeBtn');setLoading(button,true);
  try{const data=await api('PUT','/system/position-mode',{mode});renderPositionMode(data.mode||mode);document.getElementById('positionModeTip').textContent=data.message||'持仓模式已更新';}catch(error){document.getElementById('positionModeTip').textContent='切换失败：'+error.message;}finally{setLoading(button,false);}
}
toggleSimWarning();
document.getElementById('advancedSettings').addEventListener('toggle',function(){if(this.open)loadPositionMode();});

async function testBinance(button,environment){
  const result=button.parentElement.querySelector('.binance-test-result');
  result.textContent='正在读取已保存的账户配置…';result.classList.remove('text-danger','text-success');setLoading(button,true);
  try{const data=await api('POST','/system/test-binance',{environment});result.textContent=data.message;result.classList.add('text-success');}
  catch(error){result.textContent=error.message;result.classList.add('text-danger');}
  finally{setLoading(button,false);}
}
