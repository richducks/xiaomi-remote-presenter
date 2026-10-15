"use strict";
const {app,BrowserWindow,ipcMain,dialog}=require("electron");
const fs=require("node:fs"),path=require("node:path"),os=require("node:os");
const {promisify}=require("node:util"),run=promisify(require("node:child_process").execFile);
// Portable backend location. Explicit installer-provided env wins; otherwise
// probe the standard per-user install and retain the legacy developer layout.
const backendCandidates=[
 process.env.XIAOMI_REMOTE_HOME,
 path.join(os.homedir(),".local/share/xiaomi-remote-2pro/backend"),
 path.join(os.homedir(),"Documents/CodexProjects/xiaomi-remote-mic-linux")
].filter(Boolean);
const root=process.env.XIAOMI_REMOTE_HOME
 ? path.resolve(process.env.XIAOMI_REMOTE_HOME)
 : backendCandidates.find(dir=>
     fs.existsSync(path.join(dir,"remote_rules.py"))&&
     fs.existsSync(path.join(dir,".venv/bin/python")))||backendCandidates[0];
const {ConfigStore}=require("./config-store.cjs");
const configStore=new ConfigStore(root);

const rules=path.join(root,"remote_rules.json");
const units={mic:"xiaomi-remote-mic.service",gatt:"xiaomi-remote-gatt-key-bridge.service",bridge:"xiaomi-chatgpt-web-bridge.service",video:"xiaomi-remote-video-only.service"};
let busy=false;
async function exec(file,args,t=9000){
 try {const r=await run(file,args,{timeout:t,encoding:"utf8",maxBuffer:131072});return {ok:true,out:(r.stdout||"").trim()};}
 catch(e){return {ok:false,out:String(e.stdout||e.stderr||e.message).trim().slice(0,4000)};}
}
function inputMode(){
 try{
  const text=fs.readFileSync("/proc/bus/input/devices","utf8");
  const blocks=text.split(/\n\s*\n/).filter(x=>/Vendor=2717\s+Product=32b8/i.test(x));
  const proxy=blocks.some(x=>x.includes('Xiaomi RC003 GATT Key Proxy'));
  const physical=blocks.some(x=>!x.includes('Xiaomi RC003 GATT Key Proxy')&&
    !x.includes('Xiaomi Remote Video Only')&&!x.includes('Xiaomi Remote 2 Pro Filtered'));
  return {physical,proxy};
 }catch{return {physical:false,proxy:false};}
}

async function state(){
 const rows=await Promise.all(Object.entries(units).map(async([name,unit])=>{
  const [a,b]=await Promise.all([exec("systemctl",["--user","is-active",unit],5000),exec("systemctl",["--user","show",unit,"-p","NRestarts","-p","MainPID"],5000)]);
  const p=Object.fromEntries(b.out.split("\n").map(s=>s.split("=")).filter(s=>s.length===2));
  return [name,{active:a.out==="active",state:a.out,pid:+p.MainPID||0,restarts:+p.NRestarts||0}];
 }));
 const bt=await exec("bluetoothctl",["devices","Connected"],7000);
 let count=null;try{count=JSON.parse(fs.readFileSync(rules,"utf8")).rules.length;}catch{}
 return {root,backendReady:fs.existsSync(path.join(root,"remote_rules.py"))&&
   fs.existsSync(path.join(root,".venv/bin/python")),
  hid:inputMode().physical,proxy:inputMode().proxy,bt:/小米蓝牙语音遥控器|MI RC|Xiaomi Bluetooth Remote/i.test(bt.out),
  units:Object.fromEntries(rows),count,busy,time:new Date().toLocaleString("zh-CN")};
}
function readRules(){
 const data=fs.readFileSync(rules,"utf8");if(Buffer.byteLength(data)>65536)throw Error("配置文件超过64KB");
 return data;
}
async function saveRules(data){
 if(typeof data!=="string"||Buffer.byteLength(data)>65536)throw Error("规则最大64KB");
 const obj=JSON.parse(data);
 if(obj?.version!==1||!Array.isArray(obj.rules)||obj.rules.length>64||
   Object.keys(obj).sort().join(",")!=="rules,version")throw Error("配置结构有误");
 const tmp=path.join(root,".remote_rules.electron-"+process.pid+".json");
 try{
  fs.writeFileSync(tmp,data,{mode:0o600,flag:"wx"});
  const test=await exec(path.join(root,".venv/bin/python"),[path.join(root,"remote_rules.py"),"--check",tmp],10000);
  if(!test.ok||!test.out.startsWith("VALID:"))throw Error("原生校验失败："+test.out);
  const folder=path.join(root,"backups");fs.mkdirSync(folder,{recursive:true,mode:0o700});
  fs.copyFileSync(rules,path.join(folder,"remote_rules.electron-"+new Date().toISOString().replace(/[:.]/g,"-")+".json"));
  fs.renameSync(tmp,rules);return "映射已校验、备份并保存，将被服务热加载。";
 } finally{try{fs.unlinkSync(tmp);}catch{}}
}
async function logs(k){
 if(!Object.hasOwn(units,k))throw Error("不支持的服务");
 return (await exec("journalctl",["--user","-u",units[k],"-n","55","--no-pager","-o","short-iso"],12000)).out.slice(-15000);
}
async function restart(){
 if(busy)throw Error("正在执行修复");busy=true;
 try{const output=[];for(const unit of [units.gatt,units.mic,units.bridge,units.video]){
  const r=await exec("systemctl",["--user","restart",unit],14000);output.push(unit+": "+(r.ok?"已启动":r.out));
 }return output.join("\n");}finally{busy=false;}
}
async function reconnect(){
 if(busy)throw Error("正在执行修复");busy=true;
 try{
  const paired=await exec("bluetoothctl",["devices","Paired"],8000);let addr;
  for(const line of paired.out.split("\n")){
   const m=line.match(/^Device ([0-9A-F:]{17}) /i);if(!m)continue;
   const d=await exec("bluetoothctl",["info",m[1]],8000);
   if(/bluetooth:v2717p32b8/i.test(d.out)&&/Trusted:\s+yes/i.test(d.out)){addr=m[1];break;}
  }
  if(!addr)throw Error("未找到可信的小米 RC003，不会误操作其他蓝牙设备");
  for(const unit of [units.video,units.gatt,units.bridge,units.mic])await exec("systemctl",["--user","stop",unit],12000);
  let result;
  try{
   await exec("bluetoothctl",["disconnect",addr],16000);
   await new Promise(r=>setTimeout(r,1500));
   result=await exec("bluetoothctl",["connect",addr],25000);
   await new Promise(r=>setTimeout(r,2500));
  }finally{for(const unit of [units.mic,units.gatt,units.bridge,units.video])await exec("systemctl",["--user","start",unit],14000);}
  const mode=inputMode();return "蓝牙重连："+(result.ok?"已执行":result.out)+"\n输入方式："+(mode.physical?"原生 HID":mode.proxy?"BLE GATT 兼容桥":"尚未识别，请查看 GATT 桥接日志");
 }finally{busy=false;}
}
async function importRules(){
 const picker=await dialog.showOpenDialog({title:"导入遥控器按键方案（导入后需点击保存）",
  properties:["openFile"],filters:[{name:"遥控器 JSON 规则",extensions:["json"]}]});
 if(picker.canceled||!picker.filePaths.length)return null;
 const file=picker.filePaths[0],info=fs.statSync(file);
 if(info.size>65536)throw Error("方案大小超过64KB");
 const raw=fs.readFileSync(file,"utf8");
 const obj=JSON.parse(raw);
 if(obj?.version!==1||!Array.isArray(obj.rules))throw Error("不是受支持的规则文件");
 return raw;
}
async function exportRules(raw){
 if(typeof raw!=="string"||Buffer.byteLength(raw)>65536)throw Error("导出内容过大");
 const dest=await dialog.showSaveDialog({title:"导出遥控器配置",
  defaultPath:"xiaomi-remote-rules.json",filters:[{name:"JSON",extensions:["json"]}]});
 if(dest.canceled||!dest.filePath)return "已取消导出";
 const obj=JSON.parse(raw);
 if(obj?.version!==1||!Array.isArray(obj.rules))throw Error("不合法的配置");
 fs.writeFileSync(dest.filePath,raw,{mode:0o600});
 return "规则已导出，可分享给其他用户（请自行确认内容）。";
}
async function defaultRules(){
 const result=await exec(path.join(root,".venv/bin/python"),
    [path.join(root,"remote_rules.py"),"--defaults"],10000);
 if(!result.ok)throw Error("默认规则不可用："+result.out);
 const parsed=JSON.parse(result.out);
 if(parsed.version!==1||!Array.isArray(parsed.rules))throw Error("默认规则版本不正确");
 return parsed;
}
const methods={
 state,readRules,saveRules,logs,restart,reconnect,defaultRules,
 readVoice:()=>configStore.readVoice(),
 saveVoice:v=>configStore.saveVoice(v),
 schema:()=>JSON.parse(fs.readFileSync(path.join(__dirname,"ui-schema.json"),"utf8")),
 backups:()=>configStore.listBackups(),
 restoreBackup:name=>saveRules(configStore.readBackup(name)),
 importRules,exportRules
};
for(const [name,fn] of Object.entries(methods))ipcMain.handle("remote:"+name,(_,arg)=>fn(arg));
function open(){
 const win=new BrowserWindow({width:1190,height:830,minWidth:900,minHeight:620,title:"小米遥控器 2 Pro 控制中心",
  backgroundColor:"#f3f5f9",autoHideMenuBar:true,webPreferences:{
  preload:path.join(__dirname,"preload.cjs"),contextIsolation:true,sandbox:true,nodeIntegration:false,webSecurity:true}});
 win.loadFile(path.join(__dirname,"index.html"));
}
// Config UI uses no 3D/WebGL. Avoid unstable Wayland GPU subprocesses on
// affected Ubuntu systems; this does not weaken Electron's process sandbox.
app.disableHardwareAcceleration();
app.whenReady().then(()=>{open();app.on("activate",()=>{if(BrowserWindow.getAllWindows().length===0)open();});});
app.on("window-all-closed",()=>{if(process.platform!=="darwin")app.quit();});
