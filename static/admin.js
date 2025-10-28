(function () {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // Tabs
  $$("#tabs li").forEach(li => {
    li.addEventListener("click", () => {
      $$("#tabs li").forEach(x => x.classList.remove("active"));
      $$(".tab").forEach(x => x.classList.remove("active"));
      li.classList.add("active");
      $("#" + li.dataset.tab).classList.add("active");
    });
  });

  // Helpers
  const setInfo = (msg) => $("#caps-info").textContent = msg || "Ready";

  async function api(url, opts = {}) {
    const res = await fetch(url, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
    if (!res.ok) throw new Error(res.status + " " + res.statusText);
    return res.json();
  }

  // Auth check
  api("/admin_api/login").then(() => {
    $("#caps-auth").textContent = "AUTH OK";
  }).catch(() => {
    $("#caps-auth").textContent = "AUTH FAILED";
  });

  // ---------------- Licenses ----------------
  async function loadLicenses() {
    const q = ($("#lic-q").value || "").trim();
    const minc = ($("#lic-min").value || "").trim();
    const maxc = ($("#lic-max").value || "").trim();
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (minc) params.set("min_credit", minc);
    if (maxc) params.set("max_credit", maxc);
    const data = await api("/admin_api/licenses?" + params.toString());
    const tbody = $("#lic-table tbody");
    tbody.innerHTML = "";
    (data.items || []).forEach(it => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${it.id}</td>
        <td><code>${it.key}</code></td>
        <td>${it.mac_id || ""}</td>
        <td>${it.status}</td>
        <td>${it.credit}</td>
        <td>${it.last_active || ""}</td>
        <td><span class="badge-del" data-id="${it.id}">Delete</span></td>
      `;
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll(".badge-del").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!confirm("Delete license id=" + id + "?")) return;
        const res = await fetch("/admin_api/licenses/" + id, { method: "DELETE" });
        if (!res.ok) return alert("Delete failed");
        loadLicenses();
      });
    });
  }
  $("#lic-refresh").addEventListener("click", () => loadLicenses());
  $("#lic-save").addEventListener("click", async () => {
    const body = {
      key: $("#lic-key").value.trim(),
      mac_id: $("#lic-mac").value.trim(),
      credit: parseInt($("#lic-credit").value || "0", 10),
      status: $("#lic-status").value
    };
    if (!body.key) return alert("key is required");
    try {
      const res = await api("/admin_api/licenses", { method: "POST", body: JSON.stringify(body) });
      if (!res.ok) throw new Error(res.msg || "fail");
      setInfo("License saved");
      loadLicenses();
    } catch (e) {
      alert(e.message);
    }
  });
  loadLicenses();

  // ---------------- API Keys ----------------
  async function loadApiKeys() {
    const q = ($("#api-q").value || "").trim();
    const st = $("#api-status-filter").value;
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (st) params.set("status", st);
    const data = await api("/admin_api/apikeys?" + params.toString());
    const tbody = $("#api-table tbody");
    tbody.innerHTML = "";
    (data.items || []).forEach(it => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${it.id}</td>
        <td><code>${it.api_key}</code></td>
        <td>${it.status}</td>
        <td>${it.in_use ? "yes" : "no"}</td>
        <td>${it.last_used || ""}</td>
        <td>${it.note || ""}</td>
        <td><span class="badge-del" data-id="${it.id}">Delete</span></td>
      `;
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll(".badge-del").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!confirm("Delete API key id=" + id + "?")) return;
        const res = await fetch("/admin_api/apikeys/" + id, { method: "DELETE" });
        if (!res.ok) return alert("Delete failed");
        loadApiKeys();
      });
    });
  }
  $("#api-refresh").addEventListener("click", () => loadApiKeys());
  $("#api-status-filter").addEventListener("change", () => loadApiKeys());
  $("#api-add").addEventListener("click", async () => {
    const body = {
      api_key: $("#api-key").value.trim(),
      status: $("#api-status").value,
      note: $("#api-note").value.trim()
    };
    if (!body.api_key) return alert("API key is required");
    try {
      const res = await api("/admin_api/apikeys", { method: "POST", body: JSON.stringify(body) });
      if (!res.ok) throw new Error(res.msg || "fail");
      setInfo("API key added");
      $("#api-key").value = "";
      loadApiKeys();
    } catch (e) {
      alert(e.message);
    }
  });
  $("#api-bulk-add").addEventListener("click", async () => {
    const text = $("#api-bulk-text").value;
    if (!text.trim()) return alert("Paste keys first");
    const body = {
      bulk_text: text,
      status: $("#api-bulk-status").value,
      note: $("#api-bulk-note").value.trim()
    };
    try {
      const res = await api("/admin_api/apikeys", { method: "POST", body: JSON.stringify(body) });
      if (!res.ok) throw new Error(res.msg || "fail");
      setInfo(`Bulk added: ${res.added}, skipped: ${res.skipped}`);
      $("#api-bulk-text").value = "";
      loadApiKeys();
    } catch (e) {
      alert(e.message);
    }
  });
  $("#api-file-upload").addEventListener("click", async () => {
    const file = $("#api-file").files[0];
    if (!file) return alert("Choose .txt file");
    const form = new FormData();
    form.append("file", file);
    form.append("status", $("#api-file-status").value);
    form.append("note", $("#api-file-note").value.trim());
    const res = await fetch("/admin_api/apikeys/bulk_file", { method: "POST", body: form });
    if (!res.ok) return alert("Upload failed");
    const data = await res.json();
    setInfo(`Uploaded: added ${data.added}, skipped ${data.skipped}`);
    $("#api-file").value = "";
    loadApiKeys();
  });
  loadApiKeys();

  // ---------------- Prices ----------------
  async function loadPrices() {
    const data = await api("/admin_api/prices");
    const tbody = $("#price-table tbody");
    tbody.innerHTML = "";
    (data.items || []).forEach(it => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${it.id}</td>
        <td><code>${it.model}</code></td>
        <td><input data-model="${it.model}" class="input" value="${it.price}" style="width:100px"/></td>
      `;
      tbody.appendChild(tr);
    });
  }
  $("#price-refresh").addEventListener("click", () => loadPrices());
  $("#price-save").addEventListener("click", async () => {
    const inputs = $$("#price-table input[data-model]");
    const payload = [];
    inputs.forEach(inp => {
      const p = parseInt(inp.value || "0", 10);
      if (Number.isFinite(p) && p > 0) payload.push({ model: inp.dataset.model, price: p });
    });
    try {
      const res = await api("/admin_api/prices", { method: "POST", body: JSON.stringify({ prices: payload }) });
      if (!res.ok) throw new Error(res.msg || "fail");
      setInfo("Prices saved");
      loadPrices();
    } catch (e) {
      alert(e.message);
    }
  });
  loadPrices();

  // ---------------- Config ----------------
  async function loadConfig() {
    const data = await api("/admin_api/config");
    const c = data.config || {};
    $("#cfg-version").value = c.latest_version || "";
    $("#cfg-force").checked = !!c.force_update;
    $("#cfg-maint").checked = !!c.maintenance;
    $("#cfg-message").value = c.maintenance_message || "";
    $("#cfg-links").value = JSON.stringify(c.update_links || [], null, 2);
    $("#cfg-desc").value = c.update_description || "";
  }
  $("#cfg-refresh").addEventListener("click", () => loadConfig());
  $("#cfg-save").addEventListener("click", async () => {
    let links;
    try {
      links = JSON.parse($("#cfg-links").value || "[]");
      if (!Array.isArray(links)) links = [];
    } catch (_) { links = []; }
    const body = {
      latest_version: $("#cfg-version").value.trim(),
      force_update: $("#cfg-force").checked,
      maintenance: $("#cfg-maint").checked,
      maintenance_message: $("#cfg-message").value.trim(),
      update_links: links,
      update_description: $("#cfg-desc").value.trim()
    };
    try {
      const res = await api("/admin_api/config", { method: "POST", body: JSON.stringify(body) });
      if (!res.ok) throw new Error(res.msg || "fail");
      setInfo("Config saved");
      loadConfig();
    } catch (e) {
      alert(e.message);
    }
  });
  loadConfig();

  // ---------------- Logs ----------------
  async function loadLogs() {
    const data = await api("/admin_api/logs");
    const tbody = $("#logs-table tbody");
    tbody.innerHTML = "";
    (data.items || []).forEach(it => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${it.id}</td><td>${it.when || ""}</td><td>${it.action}</td><td>${(it.details || "").replaceAll("<","&lt;")}</td>`;
      tbody.appendChild(tr);
    });
  }
  $("#logs-refresh").addEventListener("click", () => loadLogs());
  loadLogs();

})();