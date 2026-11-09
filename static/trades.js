document.addEventListener('click', async (event) => {
  const button = event.target.closest('#syncFills');
  if (!button || button.disabled) return;
  button.disabled = true;
  button.textContent = '正在读取成交…';
  try {
    const response = await fetch('/api/trades/sync-fills', {method: 'POST'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '同步失败');
    window.location.reload();
  } catch (error) {
    const message = document.getElementById('monitorError');
    message.hidden = false;
    message.textContent = error.message;
    button.disabled = false;
    button.textContent = '重试同步模拟盘成交';
  }
});
