let token="";
let devices=[];
let selected=null;
let activeFeature=null;
let pollTimer=null;
let mqttFormLoaded=false;
let selectedTemplate="";
let peerConnection=null;
let signalingSocket=null;
let videoGeneration=0;
let scoresExpanded=false;
let authWaiters=[];
let language=localStorage.getItem("recamera-pro-language")||"zh-CN";
const originalText=new WeakMap();
const translations=[
  ["当前未添加任何设备","No devices have been added"],
  ["点击右下角 + 添加一台 reCamera Pro","Click + in the lower-right corner to add a reCamera Pro"],
  ["管理摄像机、实时流与智能事件","Manage cameras, live streams, and intelligent events"],
  ["添加 reCamera Pro","Add reCamera Pro"],["添加设备","Add device"],["设备名称","Device name"],["IP 地址","IP address"],
  ["设备用户名","Device username"],["设备密码","Device password"],["设备密码（可选）","Device password (optional)"],["取消","Cancel"],
  ["连接并添加","Connect and add"],["删除设备","Delete device"],["删除设备？","Delete device?"],
  ["确认删除","Delete"],["MQTT 中心","MQTT Center"],["MQTT 接收","MQTT Receiver"],
  ["连接配置、JSON 解析模板、消息历史与视觉事件规则","Connection, JSON templates, history, and visual event rules"],
  ["WebRTC 实时预览","WebRTC Live Preview"],["连接视频","Connect video"],["主码流","Main stream"],["子码流","Sub stream"],
  ["直接拉取设备低延迟音视频流，不嵌入设备 WebUI","Pull the device's low-latency media stream without embedding its Web UI"],
  ["声音事件检测","Sound Event Detection"],["未连接","Disconnected"],["已连接","Connected"],
  ["AcousticsLab 实时置信度、阈值规则与 HA Bus 事件","Live AcousticsLab confidence, threshold rules, and HA Bus events"],
  ["已开启","Enabled"],["已关闭","Disabled"],["正在重连","Reconnecting"],["鉴权失败","Authentication failed"],
  ["设备状态","Device status"],["Broker 状态","Broker status"],["Broker 已连接","Broker connected"],["历史消息","History"],["最后检测","Last detection"],
  ["最近 90 秒是否收到设备推理消息","Whether an inference message was received from the device in the last 90 seconds"],["HA 到 MQTT Broker 的连接状态","HA-to-MQTT Broker connection status"],
  ["设备在线","Device online"],["设备离线（无近期消息）","Device offline (no recent message)"],["设备状态未知","Device status unknown"],["等待设备消息","Waiting for device message"],
  ["置信度","Confidence"],["Broker 地址","Broker address"],["端口","Port"],
  ["Broker 已创建用户名","Existing Broker username"],["Broker 鉴权密码","Broker password"],
  ["事件 Topic（reCamera → HA）","Event topic (reCamera → HA)"],
  ["“已连接”表示 HA 已连接 Broker；“正在接收”表示最近收到了原厂推理消息。","“Connected” means HA is connected to the Broker; “Receiving” means a factory inference message was received recently."],
  ["保存时会先验证 Broker 鉴权。留空密码表示沿用已保存密码，不会把密码返回浏览器。","Broker authentication is validated before saving. A blank password keeps the saved value, which is never returned to the browser."],
  ["保存并重连","Save and reconnect"],["JSON 解析模板","JSON parser templates"],["模板管理","Manage templates"],
  ["当前模板","Current template"],["仅支持原厂目标检测、图像分类和图像分割输出","Only factory object detection, image classification, and segmentation outputs are supported"],
  ["视觉事件规则","Visual event rules"],["任务类型","Task type"],["全部任务","All tasks"],
  ["按任务类型、类别和置信度匹配结果并发送 HA Bus 事件","Match task type, class, and confidence, then fire an HA Bus event"],
  ["目标检测","Object detection"],["图像分类","Image classification"],["图像分割","Segmentation"],
  ["类别","Class"],["最低置信度","Minimum confidence"],
  ["冷却时间（秒）","Cooldown (seconds)"],["自定义事件名（可选）","Custom event name (optional)"],
  ["添加规则","Add rule"],["最近接收消息","Recent messages"],["清空","Clear"],["暂无消息","No messages"],
  ["暂无视觉事件规则","No visual event rules"],["暂无声音规则","No sound rules"],["暂无自定义模板","No custom templates"],
  ["事件 ","Event "],["冷却 ","Cooldown "],[" 秒"," s"],["声音流","Sound stream"],["实时连接","Live"],
  ["服务离线","Service offline"],["待连接","Ready"],["可用","Available"],["错误：","Error: "],
  ["保留解析结果、原始 JSON 与图片","Parsed results, raw JSON, and images are retained"],
  ["查看原始数据","View raw data"],["隐藏原始数据","Hide raw data"],["时间","Time"],
  ["留空则保持已保存密码","Leave blank to keep the saved password"],
  ["✓ 已安全保存密码；出于安全原因不会回显","✓ Password saved securely; it is never returned to the browser"],
  ["实时声音置信度","Live sound confidence"],["添加声音事件规则","Add sound event rule"],
  ["准备连接设备","Ready to connect"],["点击“连接视频”拉取 WebRTC 流","Click “Connect video” to start the WebRTC stream"],
  ["信令通过 Home Assistant 安全代理，视频媒体由浏览器与设备建立 WebRTC 连接；设备密码不会暴露给前端。","Signaling is securely proxied by Home Assistant; media flows over WebRTC and device credentials are never exposed to the frontend."],
  ["等待数据…","Waiting for data…"],["暂无推理数据","No inference data"],["等待实时类别…","Waiting for live classes…"],
  ["声音类别","Sound class"],["阈值（%）","Threshold (%)"],["规则名称","Rule name"],
  ["HA Bus 事件名","HA Bus event name"],["保存规则","Save rule"],["已配置声音规则","Configured sound rules"],
  ["未以 recamera_ 开头时系统会自动添加前缀。","The recamera_ prefix is added automatically when omitted."],["暂无规则","No rules"],
  ["自定义解析模板","Custom parser template"],["使用 {{路径}} 提取 JSON 字段，例如 {{detection.entries.0.class_name}}。","Use {{path}} to extract a JSON field, for example {{detection.entries.0.class_name}}."],
  ["返回","Back"],["正在接收","Receiving"],["尚未收到 MQTT 消息","No MQTT messages received yet"],
  ["加载失败：","Failed to load: "],["连接失败","Connection failed"],["正在连接设备","Connecting to device"],
  ["建立安全信令与 WebRTC 会话…","Establishing secure signaling and WebRTC session…"],
  ["视频连接中断","Video connection interrupted"],["点击“连接视频”重试","Click “Connect video” to retry"],
  ["创建 WebRTC 会话失败","Failed to create WebRTC session"],["设备拒绝视频连接","The device rejected the video connection"],
  ["未知错误","Unknown error"],["视频信令连接失败","Video signaling failed"],["请检查设备网络和视频服务","Check the device network and video service"],
  ["视频信令已断开","Video signaling disconnected"],["无法连接视频","Unable to connect video"],
  ["设备视频服务不可用","The device video service is unavailable"],["视频会话已过期","The video session has expired"],
  ["等待第一帧推理数据…","Waiting for the first inference frame…"],
  ["将删除“","This will remove “"],["”及其 HA 实体和事件规则。设备本身不会恢复出厂设置。","” and its HA entities and event rules. The device itself will not be factory-reset."],
  ["端口无效","Invalid port"],["Broker、Topic、鉴权用户名和密码均为必填","Broker, topic, username, and password are required"],
  ["Broker 拒绝了用户名或密码，请先在 Broker 中创建同名账户","The Broker rejected the username or password. Create the same account on the Broker first"],
  ["无法连接 Broker，请检查地址、端口和网络","Unable to connect to the Broker. Check the address, port, and network"],
  ["数值格式错误","Invalid number"],["请检查置信度、事件名与冷却时间","Check the confidence, event name, and cooldown"],
  ["用户名或密码错误","Incorrect username or password"],["无法连接设备，请检查 IP 和网络","Unable to connect to the device. Check its IP address and network"],
  ["该设备已经添加","This device has already been added"],["请填写完整信息","Complete all required fields"],
  ["事件名只能包含小写字母、数字和下划线","The event name may contain only lowercase letters, numbers, and underscores"],
  ["阈值或冷却时间无效","The threshold or cooldown is invalid"],["请填写完整规则","Complete all rule fields"],
  ["例如：玻璃破碎告警","Example: glass-break alert"],["WebRTC 已连接","WebRTC connected"],
  ["正在连接","Connecting"],["WebRTC 在线","WebRTC online"]
];

const $=id=>document.getElementById(id);
const esc=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const cameraIcon='<img src="/recamera_pro_static/recamera-pro-icon.png" alt="reCamera Pro">';

function tr(zh,en){return language==="en"?en:zh}

function translateText(text){
  let translated=text;
  for(const [zh,en] of [...translations].sort((a,b)=>b[0].length-a[0].length)){
    translated=translated.split(zh).join(en);
  }
  return translated;
}

function applyLanguage(){
  document.documentElement.lang=language;
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{
    acceptNode:node=>["SCRIPT","STYLE"].includes(node.parentElement?.tagName)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT
  });
  let node;
  while((node=walker.nextNode())){
    if(!originalText.has(node))originalText.set(node,node.nodeValue);
    const zh=originalText.get(node);
    node.nodeValue=language==="en"?translateText(zh):zh;
  }
  document.querySelectorAll("[placeholder],[title],[aria-label]").forEach(element=>{
    for(const attribute of ["placeholder","title","aria-label"]){
      if(!element.hasAttribute(attribute))continue;
      const key=`i18n${attribute.replace("-","")}`;
      if(!element.dataset[key])element.dataset[key]=element.getAttribute(attribute);
      element.setAttribute(attribute,language==="en"?translateText(element.dataset[key]):element.dataset[key]);
    }
  });
  document.querySelectorAll(".lang-switch button").forEach(button=>button.classList.toggle("active",button.dataset.lang===language));
}

async function changeLanguage(nextLanguage){
  language=nextLanguage;
  localStorage.setItem("recamera-pro-language",language);
  applyLanguage();

  // Dynamic cards are rendered directly in the active language. Rebuild only
  // the visible view so a page that originally opened in English can switch
  // back to Chinese without reloading or disturbing hidden form state.
  if(!$("device-list-view").hidden){
    renderDevices();
  }else if(!$("device-view").hidden&&selected){
    await openDevice(selected.entry_id);
  }else if(!$("feature-view").hidden&&selected&&activeFeature){
    const titles={mqtt:tr("MQTT 中心","MQTT Center"),video:tr("WebRTC 实时预览","WebRTC Live Preview"),acoustics:tr("声音事件检测","Sound Event Detection")};
    $("feature-title").textContent=titles[activeFeature];
    if(activeFeature!=="video")await refreshFeature();
  }
  applyLanguage();
}

function mqttStateInfo(status){
  if(!status.mqtt_enabled)return {text:tr("已关闭","Disabled"),color:"var(--muted)",online:false};
  if(status.mqtt_connected)return {text:tr("设备在线","Device online"),color:"var(--ok)",online:true};
  if(status.mqtt_broker_connected)return {text:tr("设备离线（无近期消息）","Device offline (no recent message)"),color:"var(--warn)",online:false};
  if(status.mqtt_error){
    const auth=/auth|not authori|bad user|denied/i.test(status.mqtt_error);
    return {text:auth?tr("设备状态未知（ Broker 鉴权失败）","Device status unknown (Broker authentication failed)"):tr("设备状态未知","Device status unknown"),color:"var(--bad)",online:false};
  }
  return {text:tr("等待设备消息","Waiting for device message"),color:"var(--brand)",online:false};
}

window.addEventListener("message",event=>{
  if(event.origin===location.origin&&event.source===window.parent&&event.data?.type==="recamera-auth"){
    const hadToken=Boolean(token);
    token=event.data.token||"";
    for(const resolve of authWaiters.splice(0))resolve(token);
    if(!hadToken)loadDevices();
  }
});

async function requestFreshToken(){
  const freshToken=new Promise(resolve=>{
    const timer=setTimeout(()=>resolve(""),3000);
    authWaiters.push(value=>{clearTimeout(timer);resolve(value)});
  });
  window.parent.postMessage({type:"recamera-auth-request"},location.origin);
  return freshToken;
}

async function api(url,options={},retried=false){
  const requestOptions={...options,headers:{...(options.headers||{}),Authorization:`Bearer ${token}`}};
  const response=await fetch(url,requestOptions);
  const contentType=response.headers.get("content-type")||"";
  const data=contentType.includes("json")?await response.json():{error:await response.text()};
  if(response.status===401&&!retried){
    token="";
    const freshToken=await requestFreshToken();
    if(freshToken)return api(url,options,true);
  }
  if(response.status===401)throw Error("ha_session_expired");
  if(!response.ok)throw Error(data.error||`HTTP ${response.status}`);
  return data;
}

function jsonPost(url,payload){
  return api(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
}

function show(view){
  for(const id of ["device-list-view","device-view","feature-view"])$(id).hidden=id!==view;
}

function setStatus(element,online,onlineText=tr("已连接","Connected"),offlineText=tr("未连接","Disconnected")){
  element.innerHTML=`<i class="dot ${online?"ok":""}"></i>${esc(online?onlineText:offlineText)}`;
}

function formatConfidence(value){
  if(value===null||value===undefined||value==="")return "—";
  const number=Number(value);
  return Number.isFinite(number)?`${(number<=1?number*100:number).toFixed(1)}%`:"—";
}

async function loadDevices(){
  if(!token)return;
  try{
    devices=(await api("/api/recamera_pro/devices")).devices||[];
    renderDevices();
  }catch(error){
    $("device-grid").innerHTML=`<div class="empty"><div class="empty-icon">!</div>${tr("加载失败：","Failed to load: ")}${esc(error.message)}</div>`;
  }
}

function renderDevices(){
  if(!devices.length){
    $("device-grid").innerHTML=`<div class="empty"><div class="empty-icon">⌁</div><strong>${tr("当前未添加任何设备","No devices have been added")}</strong><br>${tr("点击右下角 + 添加一台 reCamera Pro","Click + in the lower-right corner to add a reCamera Pro")}</div>`;
    applyLanguage();
    return;
  }
  $("device-grid").innerHTML=devices.map(device=>`
    <article class="card clickable device-card" data-id="${esc(device.entry_id)}">
      <div class="device-visual"><div class="camera-mark">${cameraIcon}</div></div>
      <div class="device-body">
        <div class="device-head"><div><div class="name">${esc(device.name)}</div><div class="host">${esc(device.host)}</div></div><button class="icon-btn card-delete" data-delete="${esc(device.entry_id)}" title="${tr("删除设备","Delete device")}">✕</button></div>
        <div class="meta">${esc(device.model||"reCamera Pro")}${device.firmware_version?` · ${esc(device.firmware_version)}`:""}</div>
        <div class="chip-row"><span class="chip"><i class="dot ${device.mqtt_connected?"ok":""}"></i>${device.mqtt_connected?`MQTT ${tr("设备在线","Device online")}`:device.mqtt_broker_connected?`MQTT ${tr("设备离线","Device offline")}`:device.mqtt_enabled?`MQTT ${tr("等待设备消息","Waiting for device message")}`:`MQTT ${tr("已关闭","Disabled")}`}</span><span class="chip"><i class="dot ${device.acoustics_connected?"ok":""}"></i>${tr("声音流","Sound stream")}</span></div>
      </div>
    </article>`).join("");
  document.querySelectorAll(".device-card").forEach(card=>card.onclick=()=>openDevice(card.dataset.id));
  document.querySelectorAll(".card-delete").forEach(button=>button.onclick=event=>{
    event.stopPropagation();
    openDelete(button.dataset.delete);
  });
  applyLanguage();
}

async function openDevice(entryId){
  selected=devices.find(device=>device.entry_id===entryId);
  if(!selected)return;
  stopPolling();
  stopWebrtc();
  mqttFormLoaded=false;
  $("device-name").textContent=selected.name;
  $("device-host").textContent=`${selected.host} · ${selected.model||"reCamera Pro"}`;
  $("feature-device").textContent=`${selected.name} · ${selected.host}`;
  setStatus($("mqtt-feature-status"),selected.mqtt_connected);
  setStatus($("acoustics-feature-status"),selected.acoustics_connected);
  setStatus($("video-feature-status"),false,tr("可用","Available"),tr("待连接","Ready"));
  show("device-view");
  try{
    const [mqtt,acoustics]=await Promise.all([
      api(`/api/recamera_pro/devices/${selected.entry_id}/status`),
      api(`/api/recamera_pro/devices/${selected.entry_id}/acoustics`)
    ]);
    const mqttInfo=mqttStateInfo(mqtt);
    setStatus($("mqtt-feature-status"),mqttInfo.online,mqttInfo.text,mqttInfo.text);
    setStatus($("acoustics-feature-status"),acoustics.connected,tr("实时连接","Live"),tr("服务离线","Service offline"));
  }catch(error){}
}

function stopPolling(){
  if(pollTimer)clearInterval(pollTimer);
  pollTimer=null;
}

function openFeature(feature){
  if(!selected)return;
  activeFeature=feature;
  stopPolling();
  stopWebrtc();
  for(const id of ["mqtt-feature","video-feature","acoustics-feature"])$(id).hidden=id!==`${feature}-feature`;
  const titles={mqtt:tr("MQTT 中心","MQTT Center"),video:tr("WebRTC 实时预览","WebRTC Live Preview"),acoustics:tr("声音事件检测","Sound Event Detection")};
  $("feature-title").textContent=titles[feature];
  show("feature-view");
  if(feature==="video"){
    connectWebrtc();
    return;
  }
  refreshFeature();
  pollTimer=setInterval(refreshFeature,feature==="acoustics"?1000:2500);
}

async function refreshFeature(){
  if(!selected||!activeFeature)return;
  if(activeFeature==="mqtt")await loadMqtt();
  if(activeFeature==="acoustics")await loadAcoustics();
}

async function loadMqtt(){
  try{
    const [status,messageData]=await Promise.all([
      api(`/api/recamera_pro/devices/${selected.entry_id}/status`),
      api(`/api/recamera_pro/devices/${selected.entry_id}/messages`)
    ]);
    const state=mqttStateInfo(status);
    $("mqtt-state").textContent=state.text;
    $("mqtt-state").style.color=state.color;
    $("mqtt-state").title=status.mqtt_error||"";
    $("mqtt-broker-state").textContent=status.mqtt_broker_connected?tr("Broker 已连接","Broker connected"):tr("Broker 未连接","Broker disconnected");
    $("mqtt-broker-state").style.color=status.mqtt_broker_connected?"var(--ok)":"var(--bad)";
    $("mqtt-count").textContent=status.history_count??(messageData.messages||[]).length;
    $("last-detection").textContent=status.last_detection||"—";
    $("last-confidence").textContent=formatConfidence(status.last_confidence);
    $("mqtt-switch").checked=status.mqtt_enabled;
    if(!mqttFormLoaded){
      $("mqtt-broker").value=status.broker||"";
      $("mqtt-port").value=status.port||1883;
      $("mqtt-username").value=status.username||"admin";
      $("mqtt-password").value="";
      $("mqtt-password-saved").hidden=!status.has_password;
      $("mqtt-in").value=status.topic_in||"results/data";
      mqttFormLoaded=true;
    }
    selectedTemplate=status.selected_template||"";
    renderTemplateOptions(status.templates||[]);
    renderMqttRules(status.event_rules||[]);
    renderMessages(messageData.messages||[]);
    applyLanguage();
  }catch(error){
    $("mqtt-state").textContent=tr("错误","Error");
    $("mqtt-state").title=error.message;
    $("mqtt-state").style.color="var(--bad)";
  }
}

function renderMessages(messages){
  const rows=messages.slice().reverse();
  if(!rows.length){
    $("messages").innerHTML=`<div class="muted">${tr("尚未收到 MQTT 消息","No MQTT messages received yet")}</div>`;
    return;
  }
  $("messages").innerHTML=rows.map(item=>{
    const direction=item.dir==="out"?"HA → reCamera":"reCamera → HA";
    const raw=item.data!==null&&item.data!==undefined?JSON.stringify(item.data,null,2):(item.raw||"");
    const task=String(item.task_type||item.data?.task_type_name||item.data?.task_type||"message");
    const timestamp=String(item.source_timestamp||item.ts||"").replace("T"," ").slice(0,23);
    const taskData=item.data?.[task]||item.data?.classification||item.data?.detection||item.data?.segmentation||{};
    const entries=Array.isArray(taskData?.entries)?taskData.entries:[];
    const chips=entries.slice(0,8).map(entry=>{
      const label=entry.class_name??entry.label??entry.name??entry.class??"result";
      const score=entry.confidence??entry.score??entry.probability;
      const mask=task==="segmentation"&&entry.mask_width&&entry.mask_height?` <small>${esc(entry.mask_width)}×${esc(entry.mask_height)}</small>`:"";
      return `<span class="result-chip">${esc(label)}${score!==undefined?` <strong>${formatConfidence(score)}</strong>`:""}${mask}</span>`;
    }).join("");
    return `<article class="message-card"><div class="message-card-head"><div class="message-identity"><span class="task-badge">${esc(task)}</span></div><span class="time-badge">${tr("时间","Time")} · ${esc(timestamp||"—")}</span></div><div class="message-card-body">${chips?`<div class="result-chips">${chips}</div>`:`<div class="muted">${tr("暂无推理数据","No inference data")}</div>`}${item.image?`<img src="${esc(item.image)}" alt="MQTT image">`:""}<div class="message-card-footer"><span>${esc(direction)} · ${esc(item.topic||"")}</span>${raw?`<button class="btn small ghost raw-toggle" type="button">${tr("查看原始数据","View raw data")}</button>`:""}</div>${raw?`<pre class="raw">${esc(raw)}</pre>`:""}</div></article>`;
  }).join("");
  applyLanguage();
}

function renderTemplateOptions(templates){
  const select=$("template-select");
  const names={detection:tr("目标检测","Object detection"),classification:tr("图像分类","Image classification"),segmentation:tr("图像分割","Segmentation")};
  const options=[];
  for(const template of templates){
    options.push(`<option value="${esc(template.id)}">${esc(names[template.id]||template.id)}</option>`);
  }
  select.innerHTML=options.join("");
  select.value=selectedTemplate;
}

function renderMqttRules(rules){
  if(!rules.length){
    $("mqtt-rules").innerHTML=`<div class="muted">${tr("暂无视觉事件规则","No visual event rules")}</div>`;
    return;
  }
  $("mqtt-rules").innerHTML=rules.map(rule=>`<div class="rule"><div><div class="rule-title"><span class="task-badge">${esc(rule.task_type||"*")}</span> ${esc(rule.class_name||"*")} ≥ ${formatConfidence(rule.min_confidence)}</div><div class="rule-detail">${tr("事件 ","Event ")}${esc(rule.event_name||"recamera_pro_trigger")} · ${tr("冷却 ","Cooldown ")}${esc(rule.cooldown??3)}${tr(" 秒"," s")}</div></div><div class="rule-controls"><label class="toggle-switch"><input class="mqtt-rule-toggle" data-id="${esc(rule.id)}" type="checkbox" ${rule.enabled!==false?"checked":""}><span class="toggle-track"></span></label><button class="icon-btn mqtt-rule-delete" data-id="${esc(rule.id)}">✕</button></div></div>`).join("");
  document.querySelectorAll(".mqtt-rule-toggle").forEach(toggle=>toggle.onchange=()=>changeMqttRule("toggle",toggle.dataset.id));
  document.querySelectorAll(".mqtt-rule-delete").forEach(button=>button.onclick=()=>changeMqttRule("delete",button.dataset.id));
}

async function saveMqttSettings(event){
  event.preventDefault();
  const error=$("mqtt-settings-error");
  error.style.display="none";
  try{
    await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/settings`,{
      broker:$("mqtt-broker").value.trim(),
      port:Number($("mqtt-port").value),
      username:$("mqtt-username").value.trim(),
      password:$("mqtt-password").value,
      topic_in:$("mqtt-in").value.trim()
    });
    $("mqtt-password").value="";
    $("mqtt-password-saved").hidden=false;
    $("mqtt-state").textContent=tr("正在重连","Reconnecting");
    $("mqtt-state").style.color="var(--warn)";
    setTimeout(loadMqtt,1000);
  }catch(problem){
    error.textContent=({ha_session_expired:tr("HA 会话已过期，请刷新页面后重试","The Home Assistant session expired. Refresh the page and try again"),invalid_port:tr("端口无效","Invalid port"),invalid_settings:tr("Broker、Topic、鉴权用户名和密码均为必填","Broker, topic, username, and password are required"),mqtt_auth_failed:tr("Broker 拒绝了用户名或密码，请先在 Broker 中创建同名账户","The Broker rejected the username or password. Create the same account on the Broker first"),mqtt_connect_failed:tr("无法连接 Broker，请检查地址、端口和网络","Unable to connect to the Broker. Check the address, port, and network")}[problem.message]||problem.message);
    error.style.display="block";
  }
}

async function toggleMqtt(){
  await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/toggle`,{enabled:$("mqtt-switch").checked});
  await loadMqtt();
}

async function saveMqttRule(event){
  event.preventDefault();
  const error=$("mqtt-rule-error");
  error.style.display="none";
  try{
    await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/event-rules`,{
      action:"add",
      task_type:$("mqtt-rule-task").value,
      class_name:$("mqtt-rule-class").value.trim()||"*",
      min_confidence:Number($("mqtt-rule-confidence").value),
      event_name:$("mqtt-rule-event").value.trim(),
      cooldown:Number($("mqtt-rule-cooldown").value),
      enabled:true
    });
    $("mqtt-rule-event").value="";
    await loadMqtt();
  }catch(problem){
    error.textContent=({invalid_number:tr("数值格式错误","Invalid number"),invalid_rule:tr("请检查置信度、事件名与冷却时间","Check the confidence, event name, and cooldown")}[problem.message]||problem.message);
    error.style.display="block";
  }
}

async function changeMqttRule(action,id){
  await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/event-rules`,{action,id});
  await loadMqtt();
}

async function clearMessages(){
  await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/messages`,{action:"clear"});
  await loadMqtt();
}

async function selectTemplate(){
  selectedTemplate=$("template-select").value;
  await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/templates`,{template_id:selectedTemplate});
}

function setVideoState(state,title,detail){
  const connected=state==="connected";
  const connecting=state==="connecting";
  setStatus($("video-status"),connected,connected?tr("WebRTC 已连接","WebRTC connected"):title,connecting?tr("正在连接","Connecting"):title);
  $("video-overlay-title").textContent=title;
  $("video-overlay-text").textContent=detail||"";
  $("video-overlay").classList.toggle("hidden",connected);
  setStatus($("video-feature-status"),connected,tr("WebRTC 在线","WebRTC online"),tr("待连接","Ready"));
}

function stopWebrtc(){
  videoGeneration++;
  if(signalingSocket){
    signalingSocket.onopen=signalingSocket.onmessage=signalingSocket.onerror=signalingSocket.onclose=null;
    try{signalingSocket.close()}catch(error){}
    signalingSocket=null;
  }
  if(peerConnection){
    for(const receiver of peerConnection.getReceivers())if(receiver.track)receiver.track.stop();
    peerConnection.close();
    peerConnection=null;
  }
  const video=$("webrtc-video");
  if(video?.srcObject){
    for(const track of video.srcObject.getTracks())track.stop();
    video.srcObject=null;
  }
}

async function connectWebrtc(){
  if(!selected)return;
  stopWebrtc();
  const generation=videoGeneration;
  setVideoState("connecting",tr("正在连接设备","Connecting to device"),tr("建立安全信令与 WebRTC 会话…","Establishing secure signaling and WebRTC session…"));
  try{
    const stream=$("video-stream").value;
    const ticket=await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/webrtc-ticket`,{stream});
    if(generation!==videoGeneration)return;
    const scheme=location.protocol==="https:"?"wss":"ws";
    signalingSocket=new WebSocket(`${scheme}://${location.host}${ticket.path}`);
    const PeerConnection=window.RTCPeerConnection||window.webkitRTCPeerConnection;
    const MediaStreamCtor=window.MediaStream;
    if(typeof PeerConnection!=="function"||typeof MediaStreamCtor!=="function"){
      throw new Error("webrtc_unsupported");
    }
    peerConnection=new PeerConnection({bundlePolicy:"max-bundle",iceServers:[],sdpSemantics:"unified-plan"});
    const mediaStream=new MediaStreamCtor();
    $("webrtc-video").srcObject=mediaStream;
    peerConnection.addTransceiver("video",{direction:"recvonly"});
    peerConnection.addTransceiver("audio",{direction:"recvonly"});
    peerConnection.ontrack=event=>{
      if(generation!==videoGeneration)return;
      if(!mediaStream.getTracks().some(track=>track.id===event.track.id))mediaStream.addTrack(event.track);
      $("webrtc-video").play().catch(()=>{});
    };
    peerConnection.onicecandidate=event=>{
      if(event.candidate&&signalingSocket?.readyState===WebSocket.OPEN){
        signalingSocket.send(JSON.stringify({type:"webrtc/candidate",value:event.candidate.candidate}));
      }
    };
    peerConnection.onconnectionstatechange=()=>{
      if(generation!==videoGeneration)return;
      if(peerConnection.connectionState==="connected")setVideoState("connected",tr("WebRTC 已连接","WebRTC connected"),stream==="main"?tr("主码流","Main stream"):tr("子码流","Sub stream"));
      if(["failed","disconnected"].includes(peerConnection.connectionState))setVideoState("error",tr("视频连接中断","Video connection interrupted"),tr("点击“连接视频”重试","Click “Connect video” to retry"));
    };
    signalingSocket.onopen=async()=>{
      try{
        const offer=await peerConnection.createOffer({offerToReceiveVideo:true,offerToReceiveAudio:true});
        await peerConnection.setLocalDescription(offer);
        signalingSocket.send(JSON.stringify({type:"webrtc/offer",value:offer.sdp}));
      }catch(error){
        setVideoState("error",tr("创建 WebRTC 会话失败","Failed to create WebRTC session"),error.message);
      }
    };
    signalingSocket.onmessage=async event=>{
      try{
        const message=JSON.parse(event.data);
        if(message.type==="webrtc/answer")await peerConnection.setRemoteDescription({type:"answer",sdp:message.value});
        if(message.type==="webrtc/candidate"&&message.value)await peerConnection.addIceCandidate({candidate:message.value,sdpMid:"0"});
        if(message.type==="error")setVideoState("error",tr("设备拒绝视频连接","The device rejected the video connection"),message.value||tr("未知错误","Unknown error"));
      }catch(error){}
    };
    signalingSocket.onerror=()=>setVideoState("error",tr("视频信令连接失败","Video signaling failed"),tr("请检查设备网络和视频服务","Check the device network and video service"));
    signalingSocket.onclose=()=>{
      if(generation===videoGeneration&&peerConnection?.connectionState!=="connected")setVideoState("error",tr("视频信令已断开","Video signaling disconnected"),tr("点击“连接视频”重试","Click “Connect video” to retry"));
    };
  }catch(error){
    setVideoState("error",tr("无法连接视频","Unable to connect video"),({device_unavailable:tr("设备视频服务不可用","The device video service is unavailable"),invalid_ticket:tr("视频会话已过期","The video session has expired"),webrtc_unsupported:tr("当前浏览器不支持 WebRTC","This browser does not support WebRTC")}[error.message]||error.message));
  }
}

function renderScores(scores){
  if(!scores.length){
    $("scores").innerHTML=`<div class="muted">${tr("暂无推理数据","No inference data")}</div>`;
    return;
  }
  const rows=scores.map(score=>{
    const percent=Math.max(0,Math.min(100,Number(score.confidence)*100));
    return `<div class="score-row"><span>${esc(score.label)}</span><span class="bar"><i style="width:${percent.toFixed(2)}%"></i></span><strong>${percent.toFixed(1)}%</strong></div>`;
  });
  const visible=rows.slice(0,4).join("");
  const extra=rows.slice(4).join("");
  $("scores").innerHTML=visible+(extra?`<div class="scores-extra" ${scoresExpanded?"":"hidden"}>${extra}</div><button type="button" class="scores-toggle">${scoresExpanded?tr("收起","Collapse"):tr("展开其余 ","Show ")}(${rows.length-4})</button>`:"");
  const toggle=$("scores").querySelector(".scores-toggle");
  if(toggle)toggle.onclick=()=>{scoresExpanded=!scoresExpanded;renderScores(scores)};
}

function updateLabelOptions(scores){
  const select=$("rule-label");
  const current=select.value;
  // Keep the user's in-progress selection even when a live frame temporarily
  // omits that label. Acoustics scores are refreshed every second and the
  // previous implementation rebuilt the select from only the latest frame,
  // which silently changed the selected rule label to the first new option.
  const labels=[...new Set([current,...scores.map(score=>score.label)].filter(Boolean))];
  if(!labels.length)return;
  select.innerHTML=labels.map(label=>`<option value="${esc(label)}">${esc(label)}</option>`).join("");
  if(current)select.value=current;
}

function renderRules(rules){
  if(!rules.length){
    $("rules").innerHTML=`<div class="muted">${tr("暂无声音规则","No sound rules")}</div>`;
    return;
  }
  $("rules").innerHTML=rules.map(rule=>`<div class="rule"><div><div class="rule-title">${esc(rule.name||rule.label)}</div><div class="rule-detail">${esc(rule.label)} ≥ ${(Number(rule.threshold)*100).toFixed(1)}% → ${esc(rule.event_type)} · ${tr("冷却 ","Cooldown ")}${esc(rule.cooldown)}${tr(" 秒"," s")}</div></div><div class="rule-controls"><label class="toggle-switch"><input class="sound-rule-toggle" data-rule="${esc(rule.id)}" type="checkbox" ${rule.enabled!==false?"checked":""}><span class="toggle-track"></span></label><button class="icon-btn sound-rule-delete" data-rule="${esc(rule.id)}">✕</button></div></div>`).join("");
  document.querySelectorAll(".sound-rule-toggle").forEach(toggle=>toggle.onchange=()=>toggleRule(toggle.dataset.rule));
  document.querySelectorAll(".sound-rule-delete").forEach(button=>button.onclick=()=>deleteRule(button.dataset.rule));
}

async function toggleRule(ruleId){
  await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/acoustics`,{action:"toggle_rule",id:ruleId});
  await loadAcoustics();
}

async function loadAcoustics(){
  try{
    const data=await api(`/api/recamera_pro/devices/${selected.entry_id}/acoustics`);
    setStatus($("acoustics-state"),data.connected,tr("实时连接","Live"),tr("服务离线","Service offline"));
    renderScores(data.scores||[]);
    updateLabelOptions(data.scores||[]);
    renderRules(data.rules||[]);
  }catch(error){
    setStatus($("acoustics-state"),false,tr("实时连接","Live"),`${tr("错误：","Error: ")}${error.message}`);
  }
}

async function saveRule(event){
  event.preventDefault();
  const error=$("rule-error");
  error.style.display="none";
  try{
    await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/acoustics`,{
      action:"upsert_rule",
      label:$("rule-label").value,
      threshold:Number($("rule-threshold").value)/100,
      cooldown:Number($("rule-cooldown").value),
      name:$("rule-name").value,
      event_type:$("rule-event").value
    });
    $("rule-name").value="";
    $("rule-event").value="";
    await loadAcoustics();
  }catch(problem){
    error.textContent=({invalid_event_type:tr("事件名只能包含小写字母、数字和下划线","The event name may contain only lowercase letters, numbers, and underscores"),invalid_number:tr("阈值或冷却时间无效","The threshold or cooldown is invalid"),required_fields:tr("请填写完整规则","Complete all rule fields")}[problem.message]||problem.message);
    error.style.display="block";
  }
}

async function deleteRule(ruleId){
  await jsonPost(`/api/recamera_pro/devices/${selected.entry_id}/acoustics`,{action:"delete_rule",id:ruleId});
  await loadAcoustics();
}

function openDelete(entryId){
  selected=devices.find(device=>device.entry_id===entryId);
  if(!selected)return;
  $("delete-text").textContent=`${tr("将删除“","This will remove “")}${selected.name}${tr("”及其 HA 实体和事件规则。设备本身不会恢复出厂设置。","” and its HA entities and event rules. The device itself will not be factory-reset.")}`;
  $("delete-error").style.display="none";
  $("delete-modal").style.display="flex";
}

async function confirmDelete(){
  const button=$("confirm-delete");
  const error=$("delete-error");
  button.classList.add("busy");
  error.style.display="none";
  try{
    await api(`/api/recamera_pro/devices/${selected.entry_id}`,{method:"DELETE"});
    $("delete-modal").style.display="none";
    selected=null;
    show("device-list-view");
    await loadDevices();
  }catch(problem){
    error.textContent=problem.message;
    error.style.display="block";
  }finally{button.classList.remove("busy")}
}

$("add-device").onclick=()=>{$("add-modal").style.display="flex";applyLanguage()};
$("cancel-add").onclick=()=>$("add-modal").style.display="none";
document.querySelectorAll(".lang-switch button").forEach(button=>button.onclick=()=>changeLanguage(button.dataset.lang));
$("add-form").onsubmit=async event=>{
  event.preventDefault();
  const form=event.currentTarget;
  const button=form.querySelector(".primary");
  const error=$("add-error");
  button.classList.add("busy");
  error.style.display="none";
  try{
    await jsonPost("/api/recamera_pro/devices",Object.fromEntries(new FormData(form)));
    $("add-modal").style.display="none";
    form.reset();
    form.device_name.value="reCamera Pro";
    form.device_username.value="root";
    await loadDevices();
  }catch(problem){
    error.textContent=({invalid_auth:tr("用户名或密码错误","Incorrect username or password"),cannot_connect:tr("无法连接设备，请检查 IP 和网络","Unable to connect to the device. Check its IP address and network"),already_configured:tr("该设备已经添加","This device has already been added"),required_fields:tr("请填写完整信息","Complete all required fields")}[problem.message]||problem.message);
    error.style.display="block";
  }finally{button.classList.remove("busy")}
};

$("back-devices").onclick=()=>{stopPolling();stopWebrtc();selected=null;show("device-list-view");loadDevices()};
$("back-features").onclick=()=>{stopPolling();stopWebrtc();activeFeature=null;show("device-view")};
document.querySelectorAll("[data-feature]").forEach(card=>card.onclick=()=>openFeature(card.dataset.feature));
$("delete-device").onclick=()=>openDelete(selected.entry_id);
$("cancel-delete").onclick=()=>$("delete-modal").style.display="none";
$("confirm-delete").onclick=confirmDelete;
$("mqtt-settings-form").onsubmit=saveMqttSettings;
$("mqtt-switch").onchange=toggleMqtt;
$("mqtt-rule-form").onsubmit=saveMqttRule;
$("clear-messages").onclick=clearMessages;
$("template-select").onchange=selectTemplate;
$("messages").onclick=event=>{
  if(event.target.classList.contains("raw-toggle")){
    const raw=event.target.nextElementSibling;
    const visible=raw.style.display==="block";
    raw.style.display=visible?"none":"block";
    event.target.textContent=visible?tr("查看原始数据","View raw data"):tr("隐藏原始数据","Hide raw data");
  }
};
$("video-connect").onclick=connectWebrtc;
$("video-stream").onchange=connectWebrtc;
$("rule-form").onsubmit=saveRule;
window.addEventListener("beforeunload",stopWebrtc);
applyLanguage();
window.parent.postMessage({type:"recamera-ready"},location.origin);
