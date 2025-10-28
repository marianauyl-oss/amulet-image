// ===== UTILS =====
async function api(url, method="GET", data=null){
  const opt={method,headers:{"Content-Type":"application/json"}};
  if(data)opt.body=JSON.stringify(data);
  const r=await fetch(url,opt);
  if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);
  return await r.json();
}
function $(id){return document.getElementById(id);}
function toast(m){console.log(m);alert(m);}

// ===== LICENSES =====
async function loadLicenses(){
  const q=$("licSearch").value.trim();
  const data=await api("/admin_api/licenses"+(q?`?q=${q}`:""));
  const tb=$("licTbody");tb.innerHTML="";
  data.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td>
      <td><span style="cursor:pointer;color:#2563eb" onclick="copyToClipboard('${x.key}')">${x.key}</span></td>
      <td>${x.credit}</td>
      <td>${x.active?'✅':'❌'}</td>
      <td>${x.mac_id||''}</td>
      <td>${x.created_at||''}</td>
      <td>
        <button class='btn btn-sm btn-outline-primary me-1' onclick='editLicense(${x.id})'>✏️</button>
        <button class='btn btn-sm btn-outline-danger' onclick='deleteLicense(${x.id})'>🗑</button>
      </td>`;
    tb.appendChild(tr);
  });
}
function resetLicenseForm(){
  $("licId").value="";
  $("licKey").value="";
  $("licMac").value="";
  $("licCredit").value=0;
  $("licActive").checked=true;
}
async function submitLicense(){
  const id=$("licId").value;
  const d={
    key:$("licKey").value.trim(),
    mac_id:$("licMac").value.trim(),
    credit:+$("licCredit").value,
    active:$("licActive").checked
  };
  if(!d.key)return toast("Key обовʼязковий");
  if(id){await api(`/admin_api/licenses/${id}`,"PUT",d);toast("✅ Ліцензію оновлено");}
  else{await api("/admin_api/licenses","POST",d);toast("✅ Ліцензію створено");}
  resetLicenseForm();loadLicenses();
}
async function editLicense(id){
  const all=await api("/admin_api/licenses");
  const lic=all.find(x=>x.id===id);
  if(!lic)return toast("Not found");
  $("licId").value=lic.id;
  $("licKey").value=lic.key;
  $("licMac").value=lic.mac_id||"";
  $("licCredit").value=lic.credit;
  $("licActive").checked=!!lic.active;
}
async function deleteLicense(id){
  if(!confirm("Видалити ліцензію?"))return;
  await api(`/admin_api/licenses/${id}`,"DELETE");
  loadLicenses();
}
function copyToClipboard(t){
  navigator.clipboard.writeText(t);
  toast("Скопійовано: "+t);
}

// ===== FILTER LICENSES =====
async function filterLicenses(){
  const min=$("minCredit").value,max=$("maxCredit").value,active=$("filterActive").value;
  const data=await api(`/admin_api/licenses/filter?min_credit=${min}&max_credit=${max}&active=${active}`);
  const tb=$("licTbody");tb.innerHTML="";
  data.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td><td>${x.key}</td><td>${x.credit}</td>
      <td>${x.active?'✅':'❌'}</td><td>${x.mac_id||''}</td>
      <td>
        <button class='btn btn-sm btn-outline-primary me-1' onclick='editLicense(${x.id})'>✏️</button>
        <button class='btn btn-sm btn-outline-danger' onclick='deleteLicense(${x.id})'>🗑</button>
      </td>`;
    tb.appendChild(tr);
  });
}

// ===== API KEYS =====
async function loadKeys(){
  const d=await api("/admin_api/apikeys");
  const tb=$("keysTbody");tb.innerHTML="";
  d.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td><td>${x.api_key}</td><td>${x.status}</td>
      <td>
        <button class='btn btn-sm btn-outline-primary me-1' onclick='editApiKey(${x.id})'>✏️</button>
        <button class='btn btn-sm btn-outline-danger' onclick='deleteKey(${x.id})'>🗑</button>
      </td>`;
    tb.appendChild(tr);
  });
}
function resetApiKeyForm(){
  $("keyId").value="";
  $("keyValue").value="";
  $("keyStatus").value="active";
}
async function submitApiKey(){
  const id=$("keyId").value;
  const d={api_key:$("keyValue").value.trim(),status:$("keyStatus").value};
  if(!d.api_key)return toast("API key обовʼязковий");
  if(id){await api("/admin_api/apikeys","PUT",{id:+id,...d});toast("✅ Ключ оновлено");}
  else{await api("/admin_api/apikeys","POST",d);toast("✅ Ключ додано");}
  resetApiKeyForm();loadKeys();
}
async function editApiKey(id){
  const d=await api("/admin_api/apikeys");
  const k=d.find(x=>x.id===id);
  if(!k)return;
  $("keyId").value=k.id;
  $("keyValue").value=k.api_key;
  $("keyStatus").value=k.status;
}
async function deleteKey(id){
  if(!confirm("Видалити ключ?"))return;
  await api(`/admin_api/apikeys/${id}`,"DELETE");
  loadKeys();
}

// ===== VOICES =====
async function loadVoices(){
  const d=await api("/admin_api/voices");
  const tb=$("voicesTbody");tb.innerHTML="";
  d.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td><td>${x.name}</td><td>${x.voice_id}</td><td>${x.active?'✅':'❌'}</td>
      <td>
        <button class='btn btn-sm btn-outline-primary me-1' onclick='editVoice(${x.id})'>✏️</button>
        <button class='btn btn-sm btn-outline-danger' onclick='deleteVoice(${x.id})'>🗑</button>
      </td>`;
    tb.appendChild(tr);
  });
}
function resetVoiceForm(){
  $("voiceId").value="";
  $("voiceName").value="";
  $("voiceValue").value="";
  $("voiceActive").checked=true;
}
async function submitVoice(){
  const id=$("voiceId").value;
  const d={name:$("voiceName").value.trim(),voice_id:$("voiceValue").value.trim(),active:$("voiceActive").checked};
  if(!d.name||!d.voice_id)return toast("Потрібно name і voice_id");
  if(id){await api("/admin_api/voices","PUT",{id:+id,...d});toast("✅ Голос оновлено");}
  else{await api("/admin_api/voices","POST",d);toast("✅ Голос додано");}
  resetVoiceForm();loadVoices();
}
async function editVoice(id){
  const d=await api("/admin_api/voices");
  const v=d.find(x=>x.id===id);
  if(!v)return;
  $("voiceId").value=v.id;
  $("voiceName").value=v.name;
  $("voiceValue").value=v.voice_id;
  $("voiceActive").checked=v.active;
}
async function deleteVoice(id){
  if(!confirm("Видалити голос?"))return;
  await api(`/admin_api/voices/${id}`,"DELETE");
  loadVoices();
}
async function deleteAllVoices(){
  if(!confirm("Видалити всі голоси?"))return;
  await api("/admin_api/voices/delete_all","DELETE");
  loadVoices();
}
async function uploadVoices(){
  const f=$("voiceFile").files[0];
  if(!f)return toast("Вибери .txt файл");
  const txt=await f.text();
  const lines=txt.split(/\r?\n/).filter(Boolean);
  for(const line of lines){
    const [n,id]=line.split(":");
    if(n&&id)await api("/admin_api/voices","POST",{name:n.trim(),voice_id:id.trim(),active:true});
  }
  toast("✅ Імпорт завершено");
  loadVoices();
}

// ===== LOGS =====
async function loadLogs(){
  const d=await api("/admin_api/logs");
  const tb=$("logsTbody");tb.innerHTML="";
  d.forEach(x=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${x.id}</td><td>${x.license_id}</td><td>${x.action}</td>
      <td>${x.char_count}</td><td>${x.details||''}</td><td>${x.created_at}</td>`;
    tb.appendChild(tr);
  });
}

// ===== CONFIG =====
async function loadConfig(){
  const c=await api("/admin_api/config");
  $("cfgLatest").value=c.latest_version||"";
  $("cfgForce").checked=c.force_update;
  $("cfgMaint").checked=c.maintenance;
  $("cfgMaintMsg").value=c.maintenance_message||"";
  $("cfgDesc").value=c.update_description||"";
  $("cfgLinks").value=Array.isArray(c.update_links)
    ? c.update_links.join(", ")
    : (c.update_links||"");
}
async function saveConfig(){
  const rawLinks=$("cfgLinks").value.trim();
  let links=[];
  try{
    if(rawLinks.startsWith("[")) links=JSON.parse(rawLinks);
    else links=rawLinks.split(",").map(s=>s.trim()).filter(Boolean);
  }catch(e){links=rawLinks.split(",").map(s=>s.trim()).filter(Boolean);}

  const d={
    latest_version:$("cfgLatest").value.trim(),
    force_update:$("cfgForce").checked,
    maintenance:$("cfgMaint").checked,
    maintenance_message:$("cfgMaintMsg").value.trim(),
    update_description:$("cfgDesc").value.trim(),
    update_links:links
  };
  await api("/admin_api/config","PUT",d);
  toast("✅ Config saved");
}
function downloadBackup(){
  const a=document.createElement("a");
  a.href="/admin_api/backup";
  a.download="amulet_backup.json";
  a.click();
}
function downloadUsersBackup(){
  const a=document.createElement("a");
  a.href="/admin_api/backup/users";
  a.download="users_backup.json";
  a.click();
}

// ===== CONSOLE =====
async function runConsole(){
  try{
    const action=$("apiAction").value.trim();
    const payload=$("apiPayload").value.trim();
    const d=payload?JSON.parse(payload):{};
    d.action=action;
    const res=await api("/api","POST",d);
    $("apiResult").innerText=JSON.stringify(res,null,2);
  }catch(e){toast("Помилка: "+e.message);}
}
function formatJson(){
  try{$("apiPayload").value=JSON.stringify(JSON.parse($("apiPayload").value),null,2);}
  catch(e){toast("Bad JSON");}
}

// ===== INIT =====
window.addEventListener("DOMContentLoaded",()=>{
  setTimeout(()=>{
    loadLicenses();
    loadKeys();
    loadVoices();
    loadLogs();
    loadConfig();
  },300);
});
