/* 仅展示交互，不在页面加载时触发写入或交易所请求。 */
(function(){
  document.addEventListener('submit',event=>{const form=event.target;if(!form.matches('form[data-auto-filter]'))return;const select=form.querySelector('select[name="strategy_id"]');if(select && select.value==='')select.disabled=true;});
  document.addEventListener('change',event=>{const form=event.target.closest('form[data-auto-filter]');if(form)form.requestSubmit();});
  document.addEventListener('click',async event=>{const button=event.target.closest('[data-copy-target]');if(!button)return;try{await navigator.clipboard.writeText(document.getElementById(button.dataset.copyTarget).textContent);button.textContent='已复制';}catch(_){button.textContent='复制失败，请手动选择文本';}});
  const forms=document.querySelectorAll('form[data-section]');
  forms.forEach(form=>{form.addEventListener('input',()=>{form.dataset.dirty='true';const hint=form.querySelector('[data-save-state]');if(hint)hint.textContent='有未保存的修改';});form.addEventListener('change',()=>{form.dataset.dirty='true';const hint=form.querySelector('[data-save-state]');if(hint)hint.textContent='有未保存的修改';});});
  window.addEventListener('beforeunload',event=>{if(Array.from(document.querySelectorAll('form[data-section]')).some(form=>form.dataset.dirty==='true')){event.preventDefault();event.returnValue='';}});
})();
