/* 危险操作集中确认，仅用户确认后调用原接口。 */
let confirmationBusy = false;
async function confirmAction({title, detail, confirmText = '确认', danger = false}) {
  if (confirmationBusy) return false;
  confirmationBusy = true;
  const dialog = document.createElement('dialog');
  dialog.className = 'pp-confirm';
  const heading = document.createElement('h2'); heading.textContent = title; heading.id = 'confirmationTitle';
  const environment = document.createElement('p'); environment.className = 'pp-confirm-environment'; environment.textContent = '正在核对交易环境…';
  const description = document.createElement('p'); description.textContent = detail; description.id = 'confirmationDetail';
  dialog.setAttribute('aria-labelledby', heading.id); dialog.setAttribute('aria-describedby', description.id);
  const actions = document.createElement('div'); actions.className = 'pp-confirm-actions';
  const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'btn btn-outline-secondary'; cancel.textContent = '取消';
  const accept = document.createElement('button'); accept.type = 'button'; accept.className = `btn ${danger ? 'btn-danger' : 'btn-primary'}`; accept.textContent = confirmText; accept.disabled = true;
  actions.append(cancel, accept); dialog.append(heading, environment, description, actions); document.body.append(dialog);
  let accepted = false;
  const result = new Promise(resolve => {
    cancel.onclick = () => dialog.close();
    accept.onclick = () => { accepted = true; dialog.close(); };
    dialog.addEventListener('close', () => {dialog.remove(); confirmationBusy = false; resolve(accepted);}, {once:true});
  });
  dialog.showModal(); cancel.focus();
  try {
    const config = await api('GET', '/system/config');
    if (!dialog.open) return result;
    environment.textContent = config.okx_simulated ? '当前已保存环境：OKX 模拟盘' : '当前已保存环境：OKX 实盘 · 涉及真实资金';
    accept.disabled = false;
  } catch (_) {
    environment.textContent = '无法核对当前交易环境，操作已禁用。请取消并刷新后重试。';
  }
  return result;
}
