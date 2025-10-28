// ===== Auth Helpers =====
function $(id){return document.getElementById(id);}
function toast(m){console.log(m);alert(m);}

function saveCreds(u,p){
  localStorage.setItem("amulet_user", u);
  localStorage.setItem("amulet_pass", p);
}
function getCreds(){
  return {
    u: localStorage.getItem("amulet_user") || "",
    p: localStorage.getItem("amulet_pass") || ""
  };
}
function authHeaders(){
  const {u,p}=getCreds();
  const hdr={"Content-Type":"application/json"};
  if(u && p){
    // і Basic, і дублікат у X-Admin-* — для сумісності
    hdr["Authorization"]="Basic "+btoa(u+":"+p);
    hdr["X-Admin-User"]=u;
    hdr["X-Admin-Pass"]=p;
  }
  return hdr;
}
async function api(url, method="GET", data=null, isMultipart=false){
  const opt={method, headers: authHeaders()};
  if(isMultipart){
    delete opt.headers["Content-Type"];
  }else if(data){
    opt.body=JSON.stringify(data);
  }
  const r=await fetch(url, opt);
  if(!r.ok){
    const t=await r.text().catch(()=>String(r.status));
    throw new Error(`${r.status} ${t}`);
  }
  const ct=r.headers.get("Content-Type")||"";
  if(ct.includes("application/json")) return await r.json();
  return await r.text();
}

// ===== Login Flow =====
async function tryLogin(){
  const u=$("loginUser").value.trim();
  const p=$("loginPass").value.trim();
  if(!u || !p) return toast("Введіть логін/пароль");
  saveCreds(u,p);
  try{
    // дозволено GET і POST — тут достатньо GET
    const res=await api("/admin_api/login","GET");
    if(res.ok){
      $("loginBackdrop").style.display="none";
      onAuthed();
    }else{
      throw new Error(res.msg||"Auth failed");
    }
  }catch(e){
    toast("Помилка логіну: "+e.message);
  }
}

async function checkAuthOrAsk(){
  const {u,p}=getCreds();
  if(!u || !p){
    $("loginBackdrop").style.display="flex";
    return;
  }
  try{
    const res=await api("/admin_api/login","GET");
    if(res.ok){ onAuthed(); }
    else{ $("loginBackdrop").style.display="flex"; }
  }catch(_){
    $("loginBackdrop").style.display="flex";
  }
}

// ===== UI Actions After Auth =====
function onAuthed(){
  loadLicenses();
  loadKeys();
  loadVoices();
  loadLogs();
  loadConfig();
}

// ===== Licenses =====
async function loadLicenses(){
  const q=$("licSearch").value.trim();
  const data=await api("/admin_api/licenses"+(q?`?q=${encodeURIComponent(q)}`:""));
  const tb=$("licTbody"); tb.innerHTML="";
  data.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td>
      <td><span style="cursor:pointer;color:#2563eb" onclick="copy('${x.key}')">${x.key}</span></td>
      <td>${x.credit}</td>
      <td>${x.status}</td>
      <td>${x.active?'✅':'❌'}</td>
      <td>${x.mac_id||''}</td>
      <td>${x.created_at||''}</td>
      <td>
        <button class="btn btn-sm btn-outline-primary me-1" onclick="editLicense(${x.id})">✏️</button>
        <button class="btn btn-sm btn-outline-danger" onclick="deleteLicense(${x.id})">🗑</button>
      </td>`;
    tb.appendChild(tr);
  });
}
function resetLicenseForm(){
  $("licId").value=""; $("licKey").value=""; $("licMac").value=""; $("licCredit").value=0; $("licStatus").value="active"; $("licActive").checked=true;
}
async function submitLicense(){
  const id=$("licId").value;
  const d={
    key:$("licKey").value.trim(),
    mac_id:$("licMac").value.trim(),
    credit:+$("licCredit").value,
    status:$("licStatus").value,
    active:$("licActive").checked
  };
  if(!d.key) return toast("Key обовʼязковий");
  if(id){
    await api(`/admin_api/licenses/${id}`,"PUT",d);
    toast("✅ Ліцензія оновлена");
  }else{
    await api("/admin_api/licenses","POST",d);
    toast("✅ Ліцензія створена");
  }
  resetLicenseForm(); loadLicenses();
}
async function editLicense(id){
  const all=await api("/admin_api/licenses");
  const lic=all.find(x=>x.id===id);
  if(!lic) return;
  $("licId").value=lic.id;
  $("licKey").value=lic.key;
  $("licMac").value=lic.mac_id||"";
  $("licCredit").value=lic.credit;
  $("licStatus").value=lic.status||"active";
  $("licActive").checked=!!lic.active;
}
async function deleteLicense(id){
  if(!confirm("Видалити ліцензію?")) return;
  await api(`/admin_api/licenses/${id}`,"DELETE");
  loadLicenses();
}
async function filterLicenses(){
  const min=$("minCredit").value, max=$("maxCredit").value, active=$("filterActive").value;
  const url=`/admin_api/licenses/filter?min_credit=${min||""}&max_credit=${max||""}&active=${active||""}`;
  const data=await api(url);
  const tb=$("licTbody"); tb.innerHTML="";
  data.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td><td>${x.key}</td><td>${x.credit}</td>
      <td>${x.active?'✅':'❌'}</td><td>${x.mac_id||''}</td>
      <td></td>
      <td>
        <button class="btn btn-sm btn-outline-primary me-1" onclick="editLicense(${x.id})">✏️</button>
        <button class="btn btn-sm btn-outline-danger" onclick="deleteLicense(${x.id})">🗑</button>
      </td>`;
    tb.appendChild(tr);
  });
}

// ===== API Keys =====
async function loadKeys(){
  const d=await api("/admin_api/apikeys");
  const tb=$("keysTbody"); tb.innerHTML="";
  d.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td>
      <td><span style="cursor:pointer;color:#2563eb" onclick="copy('${x.api_key}')">${x.api_key}</span></td>
      <td>${x.status}</td>
      <td>${x.in_use?'🟡 in use':'🟢 free'}</td>
      <td>${x.last_used||''}</td>
      <td>${x.note||''}</td>
      <td>
        <button class="btn btn-sm btn-outline-primary me-1" onclick="editKey(${x.id})">✏️</button>
        <button class="btn btn-sm btn-outline-danger" onclick="deleteKey(${x.id})">🗑</button>
      </td>`;
    tb.appendChild(tr);
  });
}
function resetKeyForm(){
  $("keyId").value=""; $("keyValue").value=""; $("keyStatus").value="active"; $("keyNote").value="";
}
async function submitKey(){
  const id=$("keyId").value;
  const d={api_key:$("keyValue").value.trim(), status:$("keyStatus").value, note:$("keyNote").value.trim()};
  if(!d.api_key) return toast("API key обовʼязковий");
  if(id){
    await api(`/admin_api/apikeys/${id}`,"PUT",d);
    toast("✅ Ключ оновлено");
  }else{
    await api("/admin_api/apikeys","POST",d);
    toast("✅ Ключ додано");
  }
  resetKeyForm(); loadKeys();
}
async function editKey(id){
  const d=await api("/admin_api/apikeys");
  const k=d.find(x=>x.id===id);
  if(!k) return;
  $("keyId").value=k.id;
  $("keyValue").value=k.api_key;
  $("keyStatus").value=k.status;
  $("keyNote").value=k.note||"";
}
async function deleteKey(id){
  if(!confirm("Видалити ключ?")) return;
  await api(`/admin_api/apikeys/${id}`,"DELETE");
  loadKeys();
}
async function uploadKeysTxt(){
  const f=$("keysFile").files[0];
  if(!f) return toast("Виберіть .txt файл");
  const fd=new FormData();
  fd.append("file", f);
  const {u,p}=getCreds();
  const r=await fetch("/admin_api/apikeys",{method:"POST",headers:{
    "Authorization":"Basic "+btoa(u+":"+p),
    "X-Admin-User":u,"X-Admin-Pass":p
  }, body:fd});
  if(!r.ok){ return toast("Помилка імпорту: "+r.status); }
  const js=await r.json();
  toast(`✅ Імпортовано: ${js.imported||0}`);
  loadKeys();
}

// ===== Voices =====
async function loadVoices(){
  const d=await api("/admin_api/voices");
  const tb=$("voicesTbody"); tb.innerHTML="";
  d.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td><td>${x.name}</td><td>${x.voice_id}</td><td>${x.active?'✅':'❌'}</td>
      <td>
        <button class="btn btn-sm btn-outline-primary me-1" onclick="editVoice(${x.id})">✏️</button>
        <button class="btn btn-sm btn-outline-danger" onclick="deleteVoice(${x.id})">🗑</button>
      </td>`;
    tb.appendChild(tr);
  });
}
function resetVoiceForm(){
  $("voiceId").value=""; $("voiceName").value=""; $("voiceValue").value=""; $("voiceActive").checked=true;
}
async function submitVoice(){
  const id=$("voiceId").value;
  const d={name:$("voiceName").value.trim(), voice_id:$("voiceValue").value.trim(), active:$("voiceActive").checked};
  if(!d.name || !d.voice_id) return toast("Потрібно name і voice_id");
  if(id){
    await api("/admin_api/voices","PUT",{id:+id,...d});
    toast("✅ Голос оновлено");
  }else{
    await api("/admin_api/voices","POST",d);
    toast("✅ Голос додано");
  }
  resetVoiceForm(); loadVoices();
}
async function editVoice(id){
  const d=await api("/admin_api/voices");
  const v=d.find(x=>x.id===id);
  if(!v) return;
  $("voiceId").value=v.id; $("voiceName").value=v.name; $("voiceValue").value=v.voice_id; $("voiceActive").checked=v.active;
}
async function deleteVoice(id){
  if(!confirm("Видалити голос?")) return;
  await api(`/admin_api/voices/${id}`,"DELETE");
  loadVoices();
}
async function deleteAllVoices(){
  if(!confirm("Видалити всі голоси?")) return;
  await api("/admin_api/voices/delete_all","DELETE");
  loadVoices();
}
async function uploadVoicesTxt(){
  const f=$("voiceFile").files[0];
  if(!f) return toast("Виберіть .txt файл");
  const txt=await f.text();
  const lines=txt.split(/\r?\n/).filter(Boolean);
  for(const line of lines){
    const [name, id] = line.includes(":") ? line.split(":") : [null, null];
    if(name && id) await api("/admin_api/voices","POST",{name:name.trim(), voice_id:id.trim(), active:true});
  }
  toast("✅ Імпорт голосів завершено");
  loadVoices();
}

// ===== Logs / Config =====
async function loadLogs(){
  const d=await api("/admin_api/logs");
  const tb=$("logsTbody"); tb.innerHTML="";
  d.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td><td>${x.license_id||''}</td><td>${x.action}</td>
      <td>${x.char_count}</td><td>${x.details||''}</td><td>${x.created_at}</td>`;
    tb.appendChild(tr);
  });
}
async function loadConfig(){
  const c=await api("/admin_api/config");
  $("cfgLatest").value=c.latest_version||"";
  $("cfgForce").checked=!!c.force_update;
  $("cfgMaint").checked=!!c.maintenance;
  $("cfgMaintMsg").value=c.maintenance_message||"";
  $("cfgDesc").value=c.update_description||"";
  $("cfgLinks").value=Array.isArray(c.update_links)? c.update_links.join(", ") : (c.update_links||"");
}
async function saveConfig(){
  const raw=$("cfgLinks").value.trim();
  let links=[];
  try{ links = raw.startsWith("[") ? JSON.parse(raw) : raw.split(",").map(s=>s.trim()).filter(Boolean); }
  catch{ links = raw.split(",").map(s=>s.trim()).filter(Boolean); }
  await api("/admin_api/config","PUT",{
    latest_version:$("cfgLatest").value.trim(),
    force_update:$("cfgForce").checked,
    maintenance:$("cfgMaint").checked,
    maintenance_message:$("cfgMaintMsg").value.trim(),
    update_description:$("cfgDesc").value.trim(),
    update_links:links
  });
  toast("✅ Config saved");
}
function downloadBackup(){
  const a=document.createElement("a"); a.href="/admin_api/backup"; a.download="amulet_backup.json"; a.click();
}
function downloadUsersBackup(){
  const a=document.createElement("a"); a.href="/admin_api/backup/users"; a.download="users_backup.json"; a.click();
}

// ===== API Console =====
async function runConsole(){
  try{
    const action=$("apiAction").value.trim();
    const payload=$("apiPayload").value.trim();
    const d=payload?JSON.parse(payload):{};
    d.action=action;
    const r=await fetch("/api",{method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(d)});
    const js=await r.json();
    $("apiResult").innerText=JSON.stringify(js,null,2);
  }catch(e){ toast("Помилка: "+e.message); }
}
function formatJson(){
  try{$("apiPayload").value=JSON.stringify(JSON.parse($("apiPayload").value),null,2);}
  catch{ toast("Bad JSON");}
}

// ===== Utils =====
function copy(t){ navigator.clipboard.writeText(t); toast("Скопійовано: "+t); }

// ===== Init =====
window.addEventListener("DOMContentLoaded", ()=>{
  $("loginBtn").addEventListener("click", tryLogin);
  checkAuthOrAsk();
});