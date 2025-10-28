// static/admin.js
// Amulet Admin Pro — Licenses / API Keys / Config / Prices / Logs (без Voices)

(function () {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = { tab: 'licenses' };

  async function fetchJSON(url, opts = {}) {
    const res = await fetch(url, Object.assign({
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
    }, opts));
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    const ct = res.headers.get('content-type') || '';
    return ct.includes('application/json') ? res.json() : res.text();
  }

  function escapeHtml(s) {
    return String(s ?? '')
      .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
  }

  function toast(msg, type = 'info') {
    let box = $('#toast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toast';
      Object.assign(box.style, {
        position: 'fixed', right: '16px', top: '16px', zIndex: 9999,
        maxWidth: '520px', color: '#fff', fontWeight: 800,
        background: '#2563eb', padding: '12px 14px', borderRadius: '10px',
        boxShadow: '0 6px 24px rgba(0,0,0,.25)', transition: 'opacity .3s',
      });
      document.body.appendChild(box);
    }
    const colors = { info: '#2563eb', ok: '#16a34a', warn: '#f59e0b', error: '#dc2626' };
    box.style.background = colors[type] || colors.info;
    box.textContent = msg;
    box.style.opacity = '1';
    setTimeout(() => { box.style.opacity = '0'; }, 2200);
  }

  // ===== Tabs =====
  function bindTabs() {
    $$('#nav .tab').forEach(btn => {
      btn.addEventListener('click', () => setTab(btn.dataset.tab));
    });
  }
  function setTab(tab) {
    state.tab = tab;
    $$('#nav .tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    $$('.view').forEach(v => v.classList.toggle('hidden', v.id !== `view-${tab}`));
    if (tab === 'licenses') loadLicenses();
    else if (tab === 'apikeys') loadApiKeys();
    else if (tab === 'config') loadConfig();
    else if (tab === 'prices') loadPrices();
    else if (tab === 'logs') loadLogs();
  }

  // ===== Licenses =====
  async function loadLicenses() {
    const tbody = $('#licensesTable tbody');
    tbody.innerHTML = '<tr><td colspan="7">Завантаження…</td></tr>';
    try {
      const j = await fetchJSON('/admin_api/licenses');
      tbody.innerHTML = '';
      (j.items || []).forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${row.id}</td>
          <td><code>${escapeHtml(row.key)}</code></td>
          <td>${row.mac_id ? `<small>${escapeHtml(row.mac_id)}</small>` : '—'}</td>
          <td><span class="badge ${row.status === 'active' ? 'ok' : 'bad'}">${row.status}</span></td>
          <td><b>${row.credit}</b></td>
          <td>${row.last_active ? new Date(row.last_active).toLocaleString() : '—'}</td>
          <td><button class="btn btn-danger" data-id="${row.id}">Видалити</button></td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" class="error">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  function bindLicenseForm() {
    const form = $('#addLicenseForm');
    if (!form) return;
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const key = form.key.value.trim();
      const credit = parseInt(form.credit.value || '0', 10) || 0;
      const status = form.status.value || 'active';
      if (!key) { toast('Введіть ключ', 'warn'); return; }
      try {
        const r = await fetchJSON('/admin_api/licenses', { method: 'POST', body: JSON.stringify({ key, credit, status }) });
        if (r.ok) { toast('Ліцензію додано', 'ok'); form.reset(); loadLicenses(); }
      } catch (e) { toast(e.message, 'error'); }
    });

    $('#licensesTable').addEventListener('click', async (ev) => {
      const btn = ev.target.closest('button.btn-danger');
      if (!btn) return;
      const id = btn.dataset.id;
      if (!confirm('Видалити ліцензію?')) return;
      try {
        const r = await fetchJSON(`/admin_api/licenses/${id}`, { method: 'DELETE' });
        if (r.ok) { toast('Видалено', 'ok'); loadLicenses(); }
      } catch (e) { toast(e.message, 'error'); }
    });
  }

  // ===== API Keys =====
  async function loadApiKeys() {
    const tbody = $('#apiKeysTable tbody');
    tbody.innerHTML = '<tr><td colspan="7">Завантаження…</td></tr>';
    try {
      const j = await fetchJSON('/admin_api/apikeys');
      tbody.innerHTML = '';
      (j.items || []).forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${row.id}</td>
          <td><code>${escapeHtml(row.api_key)}</code></td>
          <td><span class="badge ${row.status === 'active' ? 'ok' : 'bad'}">${row.status}</span></td>
          <td>${row.in_use ? '<b>YES</b>' : 'no'}</td>
          <td>${row.last_used ? new Date(row.last_used).toLocaleString() : '—'}</td>
          <td>${row.note ? escapeHtml(row.note) : '—'}</td>
          <td>
            <button class="btn btn-secondary" data-act="toggle" data-id="${row.id}">${row.in_use ? 'Відпустити' : 'Зайняти'}</button>
            <button class="btn btn-danger" data-act="del" data-id="${row.id}">Видалити</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" class="error">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  function bindApiKeyForm() {
    const form = $('#addApiKeyForm');
    if (!form) return;
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const api_key = form.api_key.value.trim();
      const status = form.status.value || 'active';
      const note = form.note.value.trim();
      if (!api_key) { toast('Введіть API ключ', 'warn'); return; }
      try {
        const r = await fetchJSON('/admin_api/apikeys', { method: 'POST', body: JSON.stringify({ api_key, status, note }) });
        if (r.ok) { toast('API ключ додано', 'ok'); form.reset(); loadApiKeys(); }
      } catch (e) { toast(e.message, 'error'); }
    });

    $('#apiKeysTable').addEventListener('click', async (ev) => {
      const btn = ev.target.closest('button');
      if (!btn) return;
      const id = btn.dataset.id;
      const act = btn.dataset.act;
      try {
        if (act === 'toggle') {
          const r = await fetchJSON(`/admin_api/apikeys/${id}/toggle_use`, { method: 'POST' });
          if (r.ok) { toast('Статус змінено', 'ok'); loadApiKeys(); }
        } else if (act === 'del') {
          if (!confirm('Видалити цей API ключ?')) return;
          const r = await fetchJSON(`/admin_api/apikeys/${id}`, { method: 'DELETE' });
          if (r.ok) { toast('Видалено', 'ok'); loadApiKeys(); }
        }
      } catch (e) { toast(e.message, 'error'); }
    });
  }

  // ===== Config =====
  async function loadConfig() {
    const form = $('#configForm');
    if (!form) return;
    form.reset();
    try {
      const j = await fetchJSON('/admin_api/config');
      const c = j.config || {};
      form.latest_version.value = c.latest_version || '';
      form.force_update.checked = !!c.force_update;
      form.maintenance.checked = !!c.maintenance;
      form.maintenance_message.value = c.maintenance_message || '';
      form.update_links.value = Array.isArray(c.update_links) ? JSON.stringify(c.update_links) : (c.update_links || '[]');
      form.update_description.value = c.update_description || '';
    } catch (e) { toast(e.message, 'error'); }
  }

  function bindConfigForm() {
    const form = $('#configForm');
    if (!form) return;
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      let links = form.update_links.value.trim();
      try {
        links = links ? JSON.parse(links) : [];
        if (!Array.isArray(links)) links = [];
      } catch {
        // дозволимо також строку з комами
        links = form.update_links.value.split(',').map(s => s.trim()).filter(Boolean);
      }
      const payload = {
        latest_version: form.latest_version.value.trim(),
        force_update: form.force_update.checked,
        maintenance: form.maintenance.checked,
        maintenance_message: form.maintenance_message.value.trim(),
        update_links: links,
        update_description: form.update_description.value.trim(),
      };
      try {
        const r = await fetchJSON('/admin_api/config', { method: 'POST', body: JSON.stringify(payload) });
        if (r.ok) { toast('Конфіг збережено', 'ok'); loadConfig(); }
      } catch (e) { toast(e.message, 'error'); }
    });
  }

  // ===== Prices =====
  async function loadPrices() {
    const tbody = $('#pricesTable tbody');
    tbody.innerHTML = '<tr><td colspan="5">Завантаження…</td></tr>';
    try {
      const j = await fetchJSON('/admin_api/prices');
      tbody.innerHTML = '';
      (j.items || j.prices || []).forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${row.id ?? ''}</td>
          <td><code>${escapeHtml(row.model)}</code></td>
          <td><input type="number" min="1" step="1" class="price-input" data-id="${row.id ?? ''}" data-model="${escapeHtml(row.model)}" value="${row.price}"></td>
          <td>${row.updated_at ? new Date(row.updated_at).toLocaleString() : '—'}</td>
          <td>
            <button class="btn btn-primary" data-act="save" data-id="${row.id ?? ''}" data-model="${escapeHtml(row.model)}">Зберегти</button>
            <button class="btn btn-danger" data-act="del" data-id="${row.id ?? ''}" ${row.id ? '' : 'disabled'}>Видалити</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="5" class="error">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  function bindPricesForm() {
    const form = $('#addPriceForm');
    if (form) {
      form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const model = form.model.value.trim();
        const price = parseInt(form.price.value || '0', 10) || 0;
        if (!model || price < 1) { toast('Модель і ціна обовʼязкові', 'warn'); return; }
        try {
          const r = await fetchJSON('/admin_api/prices', { method: 'POST', body: JSON.stringify({ model, price }) });
          if (r.ok) { toast('Ціну додано/оновлено', 'ok'); form.reset(); loadPrices(); }
        } catch (e) { toast(e.message, 'error'); }
      });
    }

    $('#pricesTable').addEventListener('click', async (ev) => {
      const btn = ev.target.closest('button');
      if (!btn) return;
      const act = btn.dataset.act;
      const id = btn.dataset.id;
      const model = btn.dataset.model;
      if (act === 'save') {
        const input = $(`.price-input[data-model="${CSS.escape(model)}"]`);
        const price = parseInt(input?.value || '0', 10) || 0;
        if (price < 1) { toast('Ціна має бути ≥ 1', 'warn'); return; }
        try {
          const r = await fetchJSON('/admin_api/prices', { method: 'POST', body: JSON.stringify({ model, price }) });
          if (r.ok) { toast('Збережено', 'ok'); loadPrices(); }
        } catch (e) { toast(e.message, 'error'); }
      } else if (act === 'del' && id) {
        if (!confirm('Видалити запис ціни?')) return;
        try {
          const r = await fetchJSON(`/admin_api/prices/${id}`, { method: 'DELETE' });
          if (r.ok) { toast('Видалено', 'ok'); loadPrices(); }
        } catch (e) { toast(e.message, 'error'); }
      }
    });

    const syncBtn = $('#syncDefaultPrices');
    if (syncBtn) {
      syncBtn.addEventListener('click', async () => {
        if (!confirm('Підтягнути дефолтні ціни (оновить/додасть стандартні моделі)?')) return;
        try {
          const r = await fetchJSON('/admin_api/prices/sync_defaults', { method: 'POST' });
          if (r.ok) { toast('Синхронізовано', 'ok'); loadPrices(); }
        } catch (e) { toast(e.message, 'error'); }
      });
    }
  }

  // ===== Logs =====
  async function loadLogs() {
    const tbody = $('#logsTable tbody');
    tbody.innerHTML = '<tr><td colspan="4">Завантаження…</td></tr>';
    try {
      const j = await fetchJSON('/admin_api/logs');
      tbody.innerHTML = '';
      (j.items || []).forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${row.id}</td>
          <td>${row.action}</td>
          <td>${row.details ? `<code>${escapeHtml(row.details)}</code>` : '—'}</td>
          <td>${row.created_at ? new Date(row.created_at).toLocaleString() : '—'}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="4" class="error">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  // ===== Init =====
  function init() {
    bindTabs();
    bindLicenseForm();
    bindApiKeyForm();
    bindConfigForm();
    bindPricesForm();
    setTab(state.tab);
  }

  document.addEventListener('DOMContentLoaded', init);
})();