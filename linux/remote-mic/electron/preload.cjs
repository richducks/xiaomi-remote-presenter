"use strict";
const {contextBridge,ipcRenderer}=require("electron");
const api={};for(const key of ["state","readRules","saveRules","logs","restart","reconnect","readVoice","saveVoice","schema","backups","restoreBackup","importRules","exportRules"])
 api[key]=(...args)=>ipcRenderer.invoke("remote:"+key,...args);
contextBridge.exposeInMainWorld("remote",Object.freeze(api));
