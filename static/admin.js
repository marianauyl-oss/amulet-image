/* Amulet Admin UI (vanilla JS) */

(function () {
  const $ = (sel, ctx=document) => ctx.querySelector(sel);
  const $$ = (sel, ctx=document) => Array.from(ctx.querySelectorAll(sel));

  // ===== auth token (optional) =====
  const url = new URL(window.location.href);
  const ADMIN_TOKEN = url.searchParams.get('token') || '';

  const headers = () => {
    const h = { 'Content-Type': 'application/json' };
    if (ADMIN_TOKEN) h['X-Admin-Token'] = ADMIN_TOKEN;
    return h;
  };

  // ===== toast =====
  let toastTimer = null;
  function toast(msg, type='info', ms=2200){
    const t = $('#toast');
    t.textContent = msg;
    t.className = `toast ${type}`;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(()=>{ t.hidden = true; }, ms);
  }

  // ===== tabs =====
  const tabs = $('#tabs');
  tabs.addEventListener('click', (e)=>{
    const li = e.target.closest('li[data-tab]');
    if(!li) return;
    $$('.tabs li').forEach(n=>n.classList.remove('active'));
    li.classList.add('active');
    $$('.tab').forEach(n=>n.classList.remove('active'));
    const sec = '#'+li.dataset.tab;
    $(sec).classList.add('active');
  });

  // ===== login ping + config chip =====
  async function api(path, opt={}){
    const o = Object.assign({ method:'GET', headers:headers(), credentials:'same-origin' }, opt);
    if (o.body && typeof o.body !== 'string' && !(o.body instanceof FormData)) {
      o.body = JSON.stringify(o.body);
    }
    const res = await fetch(path + (path.includes('?') ? '' : ''), o);
    if (res.status === 401) {
      toast('Потрібна авторизація (401)', 'err', 3000);
      throw new Error('401');
    }
    if (res.headers.get('content-type')?.includes('application/json')) {
      return await res.json();
    }
    return await res.text();
  }

  async function pingLogin(){
    try{
      const j = await api('/admin_api/login');
      if (j && j.ok){
        $('#loginChip').textContent = `login: ${j.user}`;
        $('#loginChip').classList.add('chip-green');
      } else {
        $('#loginChip').textContent = '—';
      }
    }catch(e){
      $('#loginChip').textContent = '—';
    }
  }

  async function loadConfigChip(){
    try{
      const j = await api('/admin_api/config');
      if (j && j.ok){
        const c = j.config || {};
        $('#cfgChip').textContent = `config: v${c.latest_version || '—'}${c.maintenance ? ' • maint' : ''}`;
      }
    }catch(e){}
  }

  // ====== LICENCES ======
  let licPage=1, licPages=1, licPageSize=20, licQ='', licStatus='';

  function licQuery(){
    const params = new URLSearchParams();
    params.set('page', String(licPage));
    params.set('page_size', String(licPageSize));
    if (licQ) params.set('q', licQ);
    if (licStatus) params.set('status', licStatus);
    return '/admin_api/licenses?'+params.toString();
  }

  async function loadLicences(){
    $('#licTable tbody').innerHTML = `<tr><td colspan="9">Завантаження…</td></tr>`;
    try{
      const j = await api(licQuery());
      const arr = (j && j.items) || [];
      licPages = j.pages || 1;
      $('#licPageInfo').textContent = `${j.page}/${j.pages}`;
      const rows = arr.map(it=>{
        return `
          <tr data-id="${it.id}">
            <td>${it.id}</td>
            <td><span class="copyable" data-copy="${it.key}" title="копіювати">${it.key}</span></td>
            <td><input class="small-input input" data-edit="mac_id" value="${it.mac_id||''}" /></td>
            <td>
              <select class="input small-input" data-edit="status">
                ${['active','inactive','banned'].map(s=>`<option value="${s}" ${it.status===s?'selected':''}>${s}</option>`).join('')}
              </select>
            </td>
            <td>
              <div class="delta-btns">
                <button class="tiny-btn btn" data-delta="-10">-10</button>
                <input class="small-input input" data-edit="credit" type="number" value="${it.credit||0}" />
                <button class="tiny-btn btn" data-delta="+10">+10</button>
              </div>
            </td>
            <td>${it.last_active||''}</td>
            <td>${it.created_at||''}</td>
            <td>${it.updated_at||''}</td>
            <td>
              <button class="tiny-btn btn btn-success" data-action="save">Зберегти</button>
              <button class="tiny-btn btn btn-danger" data-action="del">Видалити</button>
            </td>
          </tr>
        `;
      }).join('');
      $('#licTable tbody').innerHTML = rows || `<tr><td colspan="9">Порожньо</td></tr>`;
    }catch(e){
      $('#licTable tbody').innerHTML = `<tr><td colspan="9">Помилка</td></tr>`;
    }
  }

  // ліцензії — події
  $('#licRefresh').addEventListener('click', ()=>{ licPage=1; loadLicences(); });
  $('#licPrev').addEventListener('click', ()=>{ if(licPage>1){ licPage--; loadLicences(); }});
  $('#licNext').addEventListener('click', ()=>{ if(licPage<licPages){ licPage++; loadLicences(); }});
  $('#licSearch').addEventListener('input', (e)=>{ licQ=e.target.value.trim(); licPage=1; });
  $('#licStatus').addEventListener('change', (e)=>{ licStatus=e.target.value; licPage=1; });
  $('#licPageSize').addEventListener('change', (e)=>{ licPageSize=parseInt(e.target.value,10)||20; licPage=1; loadLicences(); });

  // копіювання ключа
  $('#licTable').addEventListener('click', (e)=>{
    const c = e.target.closest('[data-copy]');
    if (c){
      navigator.clipboard.writeText(c.dataset.copy||'').then(()=>toast('Скопійовано','ok'));
    }
  });

  // дельта кредиту
  $('#licTable').addEventListener('click', async (e)=>{
    const btn = e.target.closest('[data-delta]');
    if(!btn) return;
    const tr = e.target.closest('tr[data-id]');
    const id = tr?.dataset.id;
    const delta = btn.dataset.delta === '+10' ? 10 : -10;
    try{
      const j = await api(`/admin_api/licenses/${id}/credit_adjust`, {method:'POST', headers:headers(), body:{delta}});
      if (j.ok){
        tr.querySelector('[data-edit="credit"]').value = j.credit;
        toast('Кредит оновлено','ok');
      }
    }catch(e){ toast('Помилка', 'err'); }
  });

  // зберегти/видалити
  $('#licTable').addEventListener('click', async (e)=>{
    const a = e.target.closest('[data-action]');
    if(!a) return;
    const tr = e.target.closest('tr[data-id]');
    const id = tr?.dataset.id;
    if(a.dataset.action==='save'){
      const body = {
        mac_id: tr.querySelector('[data-edit="mac_id"]').value.trim(),
        status: tr.querySelector('[data-edit="status"]').value,
        credit: parseInt(tr.querySelector('[data-edit="credit"]').value,10)||0,
      };
      try{
        const j = await api(`/admin_api/licenses/${id}`, {method:'PUT', headers:headers(), body});
        if (j.ok) { toast('Збережено','ok'); loadLicences(); }
        else toast(j.msg||'Помилка','err');
      }catch(e){ toast('Помилка','err'); }
    } else if (a.dataset.action==='del'){
      if(!confirm('Видалити ліцензію?')) return;
      try{
        const j = await api(`/admin_api/licenses/${id}`, {method:'DELETE', headers:headers()});
        if (j.ok){ toast('Видалено','ok'); loadLicences(); }
      }catch(e){ toast('Помилка','err'); }
    }
  });

  // нова ліцензія (генерується на бекенді якщо key порожній)
  $('#licNewBtn').addEventListener('click', async ()=>{
    const credit = prompt('Початковий кредит (int):','0') || '0';
    const status = prompt('Статус (active/inactive/banned):','active') || 'active';
    const key = prompt('Ключ (порожньо — згенерується):','') || '';
    try{
      const j = await api('/admin_api/licenses', {method:'POST', headers:headers(), body:{key, credit:parseInt(credit,10)||0, status}});
      if (j.ok){ toast('Створено','ok'); loadLicences(); }
      else toast(j.msg||'Помилка','err');
    }catch(e){ toast('Помилка','err'); }
  });

  // bulk імпорт ліцензій
  $('#licBulkUploadBtn').addEventListener('click', async ()=>{
    const fi = $('#licBulkFile');
    if (!fi.files || !fi.files[0]) { toast('Вибери .txt','warn'); return; }
    const fd = new FormData();
    fd.append('file', fi.files[0]);
    fd.append('credit', $('#licBulkCredit').value || '');
    fd.append('status', $('#licBulkStatus').value || 'active');
    const opt = { method:'POST', body:fd, headers:{} };
    if (ADMIN_TOKEN) opt.headers['X-Admin-Token'] = ADMIN_TOKEN;
    try{
      const res = await fetch('/admin_api/licenses/bulk', opt);
      const j = await res.json();
      if (j.ok){ toast(`OK: +${j.created} (skip ${j.skipped})`,'ok'); loadLicences(); }
      else toast(j.msg||'Помилка','err');
    }catch(e){ toast('Помилка','err'); }
  });

  // ====== API KEYS ======
  let apiPage=1, apiPages=1, apiPageSize=20, apiQ='', apiStatus='';

  function apiQuery(){
    const p = new URLSearchParams();
    p.set('page',String(apiPage));
    p.set('page_size',String(apiPageSize));
    if (apiQ) p.set('q',apiQ);
    if (apiStatus) p.set('status',apiStatus);
    return '/admin_api/apikeys?'+p.toString();
  }

  async function loadApiKeys(){
    $('#apiTable tbody').innerHTML = `<tr><td colspan="9">Завантаження…</td></tr>`;
    try{
      const j = await api(apiQuery());
      apiPages = j.pages||1;
      $('#apiPageInfo').textContent = `${j.page}/${j.pages}`;
      const rows = (j.items||[]).map(it=>`
        <tr data-id="${it.id}">
          <td>${it.id}</td>
          <td><span class="copyable" data-copy="${it.api_key}" title="копіювати">${it.api_key}</span></td>
          <td>
            <select class="input small-input" data-edit="status">
              ${['active','inactive'].map(s=>`<option value="${s}" ${it.status===s?'selected':''}>${s}</option>`).join('')}
            </select>
          </td>
          <td>${it.in_use ? '<span class="pill">yes</span>' : 'no'}</td>
          <td>${it.last_used||''}</td>
          <td><input class="small-input input" data-edit="note" value="${(it.note||'').replaceAll('"','&quot;')}"/></td>
          <td>${it.created_at||''}</td>
          <td>${it.updated_at||''}</td>
          <td>
            <button class="tiny-btn btn btn-success" data-action="save">Зберегти</button>
            <button class="tiny-btn btn btn-danger" data-action="del">Видалити</button>
          </td>
        </tr>
      `).join('');
      $('#apiTable tbody').innerHTML = rows || `<tr><td colspan="9">Порожньо</td></tr>`;
    }catch(e){
      $('#apiTable tbody').innerHTML = `<tr><td colspan="9">Помилка</td></tr>`;
    }
  }

  $('#apiRefresh').addEventListener('click', ()=>{ apiPage=1; loadApiKeys(); });
  $('#apiPrev').addEventListener('click', ()=>{ if(apiPage>1){ apiPage--; loadApiKeys(); }});
  $('#apiNext').addEventListener('click', ()=>{ if(apiPage<apiPages){ apiPage++; loadApiKeys(); }});
  $('#apiSearch').addEventListener('input', (e)=>{ apiQ=e.target.value.trim(); apiPage=1; });
  $('#apiStatus').addEventListener('change', (e)=>{ apiStatus=e.target.value; apiPage=1; });
  $('#apiPageSize').addEventListener('change', (e)=>{ apiPageSize=parseInt(e.target.value,10)||20; apiPage=1; loadApiKeys(); });

  $('#apiTable').addEventListener('click', (e)=>{
    const c = e.target.closest('[data-copy]');
    if (c){ navigator.clipboard.writeText(c.dataset.copy||''); toast('Скопійовано','ok'); }
  });

  $('#apiTable').addEventListener('click', async (e)=>{
    const a = e.target.closest('[data-action]');
    if(!a) return;
    const tr = e.target.closest('tr[data-id]'); const id = tr?.dataset.id;
    if(a.dataset.action==='save'){
      const body = {
        status: tr.querySelector('[data-edit="status"]').value,
        note: tr.querySelector('[data-edit="note"]').value,
      };
      try{
        const j = await api(`/admin_api/apikeys/${id}`, {method:'PUT', headers:headers(), body});
        if (j.ok){ toast('Збережено','ok'); loadApiKeys(); } else toast(j.msg||'Помилка','err');
      }catch(e){ toast('Помилка','err'); }
    } else if(a.dataset.action==='del'){
      if(!confirm('Видалити ключ?')) return;
      try{
        const j = await api(`/admin_api/apikeys/${id}`, {method:'DELETE', headers:headers()});
        if (j.ok){ toast('Видалено','ok'); loadApiKeys(); } else toast(j.msg||'Помилка','err');
      }catch(e){ toast('Помилка','err'); }
    }
  });

  $('#apiNewBtn').addEventListener('click', async ()=>{
    const v = $('#apiNewValue').value.trim();
    if (!v) { toast('Введи ключ','warn'); return; }
    const note = $('#apiNewNote').value.trim();
    try{
      const j = await api('/admin_api/apikeys', {method:'POST', headers:headers(), body:{api_key:v, note}});
      if (j.ok){ toast('Додано','ok'); $('#apiNewValue').value=''; $('#apiNewNote').value=''; loadApiKeys(); }
      else toast(j.msg||'Помилка','err');
    }catch(e){ toast('Помилка','err'); }
  });

  $('#apiBulkUploadBtn').addEventListener('click', async ()=>{
    const f = $('#apiBulkFile');
    if(!f.files || !f.files[0]) { toast('Вибери .txt','warn'); return; }
    const fd = new FormData(); fd.append('file', f.files[0]);
    const opt = { method:'POST', body:fd, headers:{} };
    if (ADMIN_TOKEN) opt.headers['X-Admin-Token'] = ADMIN_TOKEN;
    try{
      const res = await fetch('/admin_api/apikeys/bulk', opt);
      const j = await res.json();
      if (j.ok){ toast(`OK: +${j.created} (skip ${j.skipped})`,'ok'); loadApiKeys(); }
      else toast(j.msg||'Помилка','err');
    }catch(e){ toast('Помилка','err'); }
  });

  // ====== PRICES ======
  let pricePage=1, pricePages=1, pricePageSize=20, priceQ='';

  function priceQuery(){
    const p = new URLSearchParams();
    p.set('page',String(pricePage));
    p.set('page_size',String(pricePageSize));
    if (priceQ) p.set('q',priceQ);
    return '/admin_api/prices?'+p.toString();
  }

  async function loadPrices(){
    $('#priceTable tbody').innerHTML = `<tr><td colspan="6">Завантаження…</td></tr>`;
    try{
      const j = await api(priceQuery());
      pricePages = j.pages||1;
      $('#pricePageInfo').textContent = `${j.page}/${j.pages}`;
      $('#priceTable tbody').innerHTML = (j.items||[]).map(it=>`
        <tr data-id="${it.id}">
          <td>${it.id}</td>
          <td><input class="small-input input" data-edit="model" value="${it.model}"/></td>
          <td><input class="small-input input" data-edit="price" type="number" min="1" value="${it.price}"/></td>
          <td>${it.created_at||''}</td>
          <td>${it.updated_at||''}</td>
          <td>
            <button class="tiny-btn btn btn-success" data-action="save">Зберегти</button>
            <button class="tiny-btn btn btn-danger" data-action="del">Видалити</button>
          </td>
        </tr>
      `).join('') || `<tr><td colspan="6">Порожньо</td></tr>`;
    }catch(e){
      $('#priceTable tbody').innerHTML = `<tr><td colspan="6">Помилка</td></tr>`;
    }
  }

  $('#priceRefresh').addEventListener('click', ()=>{ pricePage=1; loadPrices(); });
  $('#pricePrev').addEventListener('click', ()=>{ if(pricePage>1){ pricePage--; loadPrices(); }});
  $('#priceNext').addEventListener('click', ()=>{ if(pricePage<pricePages){ pricePage++; loadPrices(); }});
  $('#priceSearch').addEventListener('input', (e)=>{ priceQ=e.target.value.trim(); pricePage=1; });
  $('#pricePageSize').addEventListener('change', (e)=>{ pricePageSize=parseInt(e.target.value,10)||20; pricePage=1; loadPrices(); });

  // add/update single
  $('#priceAddBtn').addEventListener('click', async ()=>{
    const model = $('#priceModel').value.trim(); const price = parseInt($('#priceValue').value,10)||0;
    if(!model || price<=0){ toast('model + price > 0','warn'); return; }
    try{
      const j = await api('/admin_api/prices', {method:'POST', headers:headers(), body:{model, price}});
      if (j.ok){ toast('Збережено','ok'); $('#priceModel').value=''; $('#priceValue').value=''; loadPrices(); }
      else toast(j.msg||'Помилка','err');
    }catch(e){ toast('Помилка','err'); }
  });

  // table actions
  $('#priceTable').addEventListener('click', async (e)=>{
    const a = e.target.closest('[data-action]');
    if(!a) return;
    const tr = e.target.closest('tr[data-id]'); const id = tr?.dataset.id;
    if(a.dataset.action==='save'){
      const model = tr.querySelector('[data-edit="model"]').value.trim();
      const price = parseInt(tr.querySelector('[data-edit="price"]').value,10)||0;
      if(!model || price<=0){ toast('Некоректні дані','warn'); return; }
      try{
        const j = await api(`/admin_api/prices/${id}`, {method:'PUT', headers:headers(), body:{model, price}});
        if (j.ok){ toast('Збережено','ok'); loadPrices(); } else toast(j.msg||'Помилка','err');
      }catch(e){ toast('Помилка','err'); }
    } else if (a.dataset.action==='del'){
      if(!confirm('Видалити запис?')) return;
      try{
        const j = await api(`/admin_api/prices/${id}`, {method:'DELETE', headers:headers()});
        if (j.ok){ toast('Видалено','ok'); loadPrices(); } else toast(j.msg||'Помилка','err');
      }catch(e){ toast('Помилка','err'); }
    }
  });

  // bulk prices
  $('#priceBulkUploadBtn').addEventListener('click', async ()=>{
    const f = $('#priceBulkFile'); if(!f.files || !f.files[0]){ toast('Вибери .txt','warn'); return; }
    const fd = new FormData(); fd.append('file', f.files[0]);
    const opt = { method:'POST', body:fd, headers:{} }; if (ADMIN_TOKEN) opt.headers['X-Admin-Token']=ADMIN_TOKEN;
    try{
      const res = await fetch('/admin_api/prices/bulk', opt);
      const j = await res.json();
      if (j.ok){ toast(`OK: +${j.created}, upd ${j.updated}, skip ${j.skipped}`,'ok'); loadPrices(); }
      else toast(j.msg||'Помилка','err');
    }catch(e){ toast('Помилка','err'); }
  });

  $('#priceDefaultsBtn').addEventListener('click', async ()=>{
    try{
      const j = await api('/admin_api/prices/defaults', {method:'POST', headers:headers()});
      if (j.ok){ toast(`Додано: ${j.added}`,'ok'); loadPrices(); }
      else toast(j.msg||'Помилка','err');
    }catch(e){ toast('Помилка','err'); }
  });

  // ====== CONFIG ======
  async function loadConfig(){
    try{
      const j = await api('/admin_api/config');
      if (j && j.ok){
        const c = j.config||{};
        $('#cfgLatest').value = c.latest_version || '';
        $('#cfgForce').checked = !!c.force_update;
        $('#cfgMaint').checked = !!c.maintenance;
        $('#cfgMaintMsg').value = c.maintenance_message || '';
        $('#cfgDesc').value = c.update_description || '';
        const links = c.update_links || '[]';
        $('#cfgLinks').value = typeof links === 'string' ? links : JSON.stringify(links);
      }
    }catch(e){}
  }

  $('#cfgSaveBtn').addEventListener('click', async ()=>{
    const latest = $('#cfgLatest').value.trim();
    const force_update = $('#cfgForce').checked;
    const maintenance = $('#cfgMaint').checked;
    const maintenance_message = $('#cfgMaintMsg').value.trim();
    const update_description = $('#cfgDesc').value;
    let update_links = $('#cfgLinks').value.trim();
    if (update_links && !update_links.startsWith('[')) {
      update_links = update_links.split(',').map(s=>s.trim()).filter(Boolean);
    } else {
      try { update_links = JSON.parse(update_links||'[]'); } catch { update_links = []; }
    }
    try{
      const j = await api('/admin_api/config', {method:'POST', headers:headers(), body:{
        latest_version: latest,
        force_update, maintenance, maintenance_message,
        update_description, update_links
      }});
      if (j.ok){ toast('Конфіг збережено','ok'); loadConfigChip(); }
      else toast(j.msg||'Помилка','err');
    }catch(e){ toast('Помилка','err'); }
  });

  // ====== LOGS ======
  let logPage=1, logPages=1, logPageSize=20;

  function logQuery(){
    const p = new URLSearchParams();
    p.set('page', String(logPage));
    p.set('page_size', String(logPageSize));
    return '/admin_api/logs?'+p.toString();
  }

  async function loadLogs(){
    $('#logTable tbody').innerHTML = `<tr><td colspan="4">Завантаження…</td></tr>`;
    try{
      const j = await api(logQuery());
      logPages = j.pages||1;
      $('#logPageInfo').textContent = `${j.page}/${j.pages}`;
      $('#logTable tbody').innerHTML = (j.items||[]).map(it=>`
        <tr>
          <td>${it.id}</td>
          <td>${it.when||''}</td>
          <td>${it.event||''}</td>
          <td><code>${(it.meta||'').slice(0,180).replaceAll('<','&lt;')}</code></td>
        </tr>
      `).join('') || `<tr><td colspan="4">Порожньо</td></tr>`;
    }catch(e){
      $('#logTable tbody').innerHTML = `<tr><td colspan="4">Помилка</td></tr>`;
    }
  }

  $('#logRefresh').addEventListener('click', ()=>{ logPage=1; loadLogs(); });
  $('#logPrev').addEventListener('click', ()=>{ if(logPage>1){ logPage--; loadLogs(); }});
  $('#logNext').addEventListener('click', ()=>{ if(logPage<logPages){ logPage++; loadLogs(); }});
  $('#logPageSize').addEventListener('change', (e)=>{ logPageSize=parseInt(e.target.value,10)||20; logPage=1; loadLogs(); });

  // ===== reload all =====
  $('#reloadAllBtn').addEventListener('click', ()=>{
    loadLicences(); loadApiKeys(); loadPrices(); loadConfig(); loadLogs();
  });

  // ===== init =====
  (async function init(){
    await pingLogin();
    await loadConfigChip();
    await loadLicences();
    await loadApiKeys();
    await loadPrices();
    await loadConfig();
    await loadLogs();
    toast('Готово', 'ok', 1200);
  })();

})();