"use strict";
const fs=require("node:fs"),path=require("node:path");
const {promisify}=require("node:util");
const exec=promisify(require("node:child_process").execFile);
const VOICE_DEFAULT={version:1,enabled:true,auto_focus_composer:true,preview_settle_ms:850};
const RULE_BACKUP=/^remote_rules\.[a-zA-Z0-9_.-]{1,150}\.json$/;
function validateVoice(value){
 if(!value||typeof value!=="object"||Array.isArray(value)||
 Object.keys(value).sort().join(",")!=="auto_focus_composer,enabled,preview_settle_ms,version"||
 value.version!==1||typeof value.enabled!=="boolean"||typeof value.auto_focus_composer!=="boolean"||
 !Number.isInteger(value.preview_settle_ms)||value.preview_settle_ms<200||value.preview_settle_ms>1800){
  throw Error("微信语音设置不合法（时间为200～1800毫秒）。");
 }
 return value;
}
class ConfigStore{
 constructor(root){this.root=path.resolve(root);this.voice=path.join(this.root,"wechat_voice_settings.json");this.rules=path.join(this.root,"remote_rules.json");this.backups=path.join(this.root,"backups");}
 readVoice(){
  try{return validateVoice(JSON.parse(fs.readFileSync(this.voice,"utf8")));}
  catch{return {...VOICE_DEFAULT};}
 }
 async saveVoice(payload){
  const value=validateVoice(payload);
  fs.mkdirSync(this.backups,{recursive:true,mode:0o700});
  const tmp=path.join(this.root,".wechat_voice.ui-"+process.pid+".json");
  try{
   fs.writeFileSync(tmp,JSON.stringify(value,null,2)+"\n",{flag:"wx",mode:0o600});
   const result=await exec(path.join(this.root,".venv/bin/python"),
    [path.join(this.root,"wechat_voice_settings.py"),"--check",tmp],
    {timeout:10000,encoding:"utf8"});
   if(!result.stdout.startsWith("VALID:"))throw Error("微信设置未通过 Python 校验");
   if(fs.existsSync(this.voice)){
    const stamp=new Date().toISOString().replace(/[:.]/g,"-");
    fs.copyFileSync(this.voice,path.join(this.backups,"wechat_voice."+stamp+".json"));
   }
   fs.renameSync(tmp,this.voice);
   return "微信语音设置已保存。下一次按住语音键时生效。";
  }finally{try{fs.unlinkSync(tmp);}catch{}}
 }
 listBackups(){
  if(!fs.existsSync(this.backups))return [];
  return fs.readdirSync(this.backups).filter(n=>RULE_BACKUP.test(n))
   .sort().reverse().slice(0,60).map(name=>{
    const stat=fs.statSync(path.join(this.backups,name));
    return {name,time:stat.mtime.toISOString(),size:stat.size};
   }).filter(x=>x.size>0&&x.size<=65536);
 }
 readBackup(name){
  if(typeof name!=="string"||!RULE_BACKUP.test(name))throw Error("非法备份文件名");
  const filepath=path.join(this.backups,name);
  const size=fs.statSync(filepath).size;
  if(size>65536)throw Error("备份文件过大");
  return fs.readFileSync(filepath,"utf8");
 }
}
module.exports={ConfigStore,validateVoice,VOICE_DEFAULT,RULE_BACKUP};
