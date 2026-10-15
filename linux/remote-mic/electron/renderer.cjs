
"use strict";
const $=id=>document.getElementById(id);
const pages={overview:"设备概览",browser:"浏览器",chatgpt:"ChatGPT",wps:"WPS 演示",wechat:"微信语音",system:"系统按键",backup:"方案与备份",diagnostics:"诊断与维护"};
const scopeLabels={wps:"WPS",browser:"浏览器",chatgpt:"ChatGPT"};
let draft=null,schema=null,voice=null,editing=null,dirty=false,reading=false,toastTimer;
function node(tag,label,clazz){const e=document.createElement(tag);if(label!==undefined)e.textContent=label;if(clazz)e.className=clazz;return e;}
function notify(message){
 const e=$("toast");e.textContent=String(message);e.classList.add("show");
 clearTimeout(toastTimer);toastTimer=setTimeout(()=>e.classList.remove("show"),9000);
}
function setDirty(value){
 dirty=!!value;
 $("saveAll").hidden=!dirty;
 $("saveAll").textContent=dirty?"保存更改 •":"保存配置";
}
function label(section,key){
 const item=schema[section].find(e=>e[0]===key);return item?item[1]:String(key).replace(/^KEY_/,"");
}
function actionLabel(rule){
 if(rule.action)return label("actions",rule.action);
 if(rule.tap)return label("outputs",rule.tap);
 if(rule.shortcut)return label("modifiers",rule.shortcut[0])+" + "+label("outputs",rule.shortcut[1]);
 return "未设置";
}
function navigate(key){
 if(!Object.hasOwn(pages,key))return;
 document.querySelectorAll(".page").forEach(e=>e.classList.toggle("active",e.id==="page-"+key));
 document.querySelectorAll(".nav").forEach(e=>e.classList.toggle("active",e.dataset.page===key));
 $("crumb-current").textContent=pages[key];
 $("mobile-page").value=key;
}
function renderSystemKeys(){
 const panel=$("system-key-list");panel.replaceChildren();
 for(const item of schema.systemKeys){
  const row=node("div",undefined,"system-key");
  const sym=node("span",item.symbol,"key-symbol");
  const detail=node("div");
  detail.append(node("strong",item.label));
  detail.append(node("small",item.hint+" · "+item.code));
  const status=node("span","不可改写 · 待硬件验收","status-chip");
  row.append(sym,detail,status);panel.append(row);
 }
}
function renderRules(){
 if(!schema||!draft)return;
 for(const scope of ["wps","browser","chatgpt"]){
  const parent=$("rules-"+scope);parent.replaceChildren();
  const rules=draft.rules.filter(r=>r.scope===scope);
  if(!rules.length){parent.append(node("div","这里还没有规则。点击“添加按键”开始配置。","empty"));continue;}
  for(const rule of rules){
   const row=node("div",undefined,"rule-row");
   const key=node("strong",label("inputs",rule.input),"rule-key");
   const arrow=node("span","→","rule-arrow");
   const action=node("span",actionLabel(rule),"rule-action");
   const edit=node("button","修改","btn");edit.type="button";
   edit.onclick=()=>editRule(scope,rule.id);
   const remove=node("button","删除","btn");remove.type="button";
   remove.onclick=()=>{
    if(!confirm("删除 "+scopeLabels[scope]+" 中的 "+label("inputs",rule.input)+" 映射？"))return;
    draft.rules=draft.rules.filter(x=>x.id!==rule.id);setDirty(true);renderRules();
   };
   row.append(key,arrow,action,edit,remove);parent.append(row);
  }
 }
 $("raw-json").value=JSON.stringify(draft,null,2);
}
function fillChoices(el,choices,selected){
 el.replaceChildren();
 choices.forEach(pair=>{const option=node("option",pair[1]);option.value=pair[0];el.append(option);});
 if(selected!==undefined)el.value=selected;
}
function editRule(scope,id){
 const old=id?draft.rules.find(r=>r.id===id):null;editing={scope,id};
 $("editor-title").textContent=id?"修改按键规则":"新增按键规则";
 $("editor-description").textContent=scopeLabels[scope]+" · 仅在此应用中执行";
 const blocked=new Set(schema.systemKeys.map(key=>key.code));
 if(scope!=="wps"){blocked.add("KEY_ENTER");blocked.add("KEY_OK");}
 fillChoices($("rule-input"),schema.inputs.filter(x=>!blocked.has(x[0])),old?.input);
 const choices=scope==="chatgpt"?schema.actions.map(x=>["action:"+x[0],x[1]]):
  schema.outputs.map(x=>["tap:"+x[0],"单键 · "+x[1]]).concat(schema.outputs.map(x=>["shortcut:"+x[0],"组合键 · "+x[1]]));
 const prev=old?.action?"action:"+old.action:old?.tap?"tap:"+old.tap:old?.shortcut?"shortcut:"+old.shortcut[1]:null;
 fillChoices($("rule-action"),choices,prev||choices[0][0]);
 fillChoices($("rule-modifier"),schema.modifiers,old?.shortcut?.[0]||"KEY_LEFTCTRL");
 $("rule-cooldown").value=old?.cooldown_ms??schema.defaults.cooldown_ms;
 onActionChanged();$("rule-dialog").showModal();
}
function onActionChanged(){$("modifier-field").hidden=!$("rule-action").value.startsWith("shortcut:");}
function acceptRule(){
 if(!editing)return false;
 const scope=editing.scope,input=$("rule-input").value,kind=$("rule-action").value,ms=Number($("rule-cooldown").value);
 if(!Number.isInteger(ms)||ms<0||ms>5000){notify("防重复时间必须在 0–5000 毫秒。");return false;}
 if(draft.rules.some(r=>r.scope===scope&&r.input===input&&r.id!==editing.id)){
  notify("这个应用中该按键已经有规则，请直接修改原来的映射。");return false;
 }
 const id=editing.id||(scope+"-custom-"+input.toLowerCase().replace("key_",""));
 const rule={id,scope,input,cooldown_ms:ms};
 if(kind.startsWith("tap:"))rule.tap=kind.substring(4);
 else if(kind.startsWith("shortcut:"))rule.shortcut=[$("rule-modifier").value,kind.substring(9)];
 else if(kind.startsWith("action:"))rule.action=kind.substring(7);
 else {notify("无效的按键动作。");return false;}
 const i=draft.rules.findIndex(r=>r.id===id);
 if(i<0)draft.rules.push(rule);else draft.rules[i]=rule;
 setDirty(true);renderRules();return true;
}
async function loadRules(){
 const data=JSON.parse(await window.remote.readRules());
 if(data.version!==1||!Array.isArray(data.rules))throw Error("不支持规则文件版本");
 draft=data;setDirty(false);renderRules();
}
async function saveRules(){
 if(!draft)throw Error("规则未加载");
 const message=await window.remote.saveRules(JSON.stringify(draft,null,2));
 await loadRules();await refresh();notify(message);
}
async function saveVoice(){
 const settings={version:1,enabled:$("voice-enabled").checked,
  auto_focus_composer:$("voice-focus").checked,preview_settle_ms:Number($("voice-delay").value)};
 notify(await window.remote.saveVoice(settings));voice=settings;
}
async function showBackups(){
 const backups=await window.remote.backups(),target=$("backups");target.replaceChildren();
 if(!backups.length){target.append(node("p","还没有历史备份。保存配置会自动备份。","muted"));return;}
 for(const b of backups){
  const row=node("div",undefined,"backup-row"),name=node("div");
  name.append(node("strong",new Date(b.time).toLocaleString("zh-CN")));
  name.append(node("small",b.name+" · "+Math.ceil(b.size/1024)+"KB"));
  const button=node("button","恢复此版本","btn");
  button.onclick=async()=>{
   if(!confirm("将覆盖当前映射，旧配置会先备份。确定恢复？"))return;
   try{notify(await window.remote.restoreBackup(b.name));await loadRules();}catch(e){notify(e.message);}
  };
  row.append(name,button);target.append(row);
 }
}
function setStatus(s){
 $("header-time").textContent="最近检测 "+s.time;
 $("metric-bluetooth").textContent=s.bt?"已连接":"未连接";
 $("metric-hid").textContent=s.hid?"物理 HID":s.proxy?"BLE 兼容桥":"未识别";
 $("metric-rules").textContent=s.count===null?"—":s.count+" 条";
 const working=Object.values(s.units).filter(v=>v.active).length;
 $("metric-services").textContent=working+"/"+Object.keys(s.units).length;
 $("root").textContent=s.root;
 const okay=Boolean(s.backendReady&&s.bt&&(s.hid||s.proxy)&&
                    working===Object.keys(s.units).length);
 $("connection-dot").className="dot "+(okay?"ok":"bad");
 $("connection-summary").textContent=!s.backendReady?"等待安装后端":okay?"设备运行正常":"部分功能需检查";
 $("overview-note").textContent=!s.backendReady?
  "还没有安装 Linux Python 后端。请按 GitHub 文档部署蓝牙/语音服务，然后重新打开控制中心。仅安装 Electron 界面不能识别遥控器。":
  okay?"所有后台服务正在运行。保存规则后，原按键服务自动热加载配置。":
  "设备或服务未就绪，请进入诊断页面查看具体状态。";
 const target=$("services-detail");target.replaceChildren();
 const labels={mic:"蓝牙语音",gatt:"BLE GATT 按键兼容桥",bridge:"微信 / ChatGPT 桥接",video:"应用按键映射引擎"};
 for(const [key,item] of Object.entries(s.units)){
  const row=node("div",undefined,"service-row"),info=node("div");
  info.append(node("strong",labels[key]||key));
  info.append(node("small","PID "+(item.pid||"—")+" · 历史重启 "+item.restarts+" 次"));
  const status=node("span",item.active?"运行中":"已停止","service-badge"+(item.active?"":" bad"));
  row.append(info,status);target.append(row);
 }
}
async function refresh(){
 if(reading)return;reading=true;
 try{setStatus(await window.remote.state());}
 catch(e){notify("读取设备状态失败："+e.message);}
 finally{reading=false;}
}
function bind(id,fn,msg=null){
 $(id).addEventListener("click",async()=>{
  if(msg&&!confirm(msg))return;
  $(id).disabled=true;
  const original=$(id).textContent;
  $(id).textContent="处理中…";
  try{const result=await fn();if(result!==undefined&&result!==null)notify(result);}
  catch(e){notify("操作失败："+e.message);}
  finally{
   $(id).disabled=false;
   $(id).textContent=(id==="saveAll"&&!dirty)?"保存配置":original;
  }
 });
}
window.addEventListener("DOMContentLoaded",async()=>{
 document.querySelectorAll(".nav").forEach(n=>n.onclick=()=>navigate(n.dataset.page));
 $("mobile-page").onchange=()=>navigate($("mobile-page").value);
 navigate("overview");  // never show two active nav entries on first load
 document.querySelectorAll("[data-goto]").forEach(n=>n.onclick=()=>navigate(n.dataset.goto));
 document.querySelectorAll(".add-rule").forEach(n=>n.onclick=()=>editRule(n.dataset.scope,null));
 $("rule-action").onchange=onActionChanged;
 $("rule-form").addEventListener("submit",event=>{
  if(event.submitter?.value==="save"&&!acceptRule())event.preventDefault();
 });
 bind("refresh",refresh);bind("saveAll",saveRules);bind("saveVoice",saveVoice);bind("refreshBackups",showBackups);
 bind("logs",async()=>{$("log").textContent=await window.remote.logs($("logunit").value);});
 bind("restart",async()=>{const result=await window.remote.restart();await refresh();return result;},"重新启动四个遥控器用户服务？");
 bind("reconnect",async()=>{const result=await window.remote.reconnect();await refresh();return result;},"将只断开并重连可信的小米遥控器，确定？");
 bind("import",async()=>{
  const raw=await window.remote.importRules();if(raw===null)return null;
  const doc=JSON.parse(raw);if(doc.version!==1||!Array.isArray(doc.rules))throw Error("不是支持的规则文件");
  draft=doc;setDirty(true);renderRules();return "规则已导入预览，请点击顶部“保存配置”";
 });
 bind("export",()=>window.remote.exportRules(JSON.stringify(draft,null,2)));
 bind("restoreDefaults",async()=>{
  if(!confirm("预览当前程序的默认规则？未保存的修改将放弃。"))return null;
  draft=await window.remote.defaultRules();
  setDirty(true);renderRules();return "默认配置已载入预览，尚未写入电脑。";
 });
 bind("applyRaw",async()=>{
  const doc=JSON.parse($("raw-json").value);
  if(doc.version!==1||!Array.isArray(doc.rules))throw Error("规则结构错误");
  draft=doc;setDirty(true);renderRules();
  return "JSON 已导入预览，请点击顶部“保存配置”使用 Python 原生校验。";
 });
 window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
 try{
  schema=await window.remote.schema();
  renderSystemKeys();
  voice=await window.remote.readVoice();
  $("voice-enabled").checked=voice.enabled;
  $("voice-focus").checked=voice.auto_focus_composer;
  $("voice-delay").value=voice.preview_settle_ms;
  try{await loadRules();}
  catch(e){
   notify("按键后端未就绪，请到“诊断与维护”检查："+e.message);
   draft={version:1,rules:[]};renderRules();
  }
  await refresh();await showBackups();
 }catch(e){notify("界面初始化异常："+e.message);}
 setInterval(refresh,9000);
});
