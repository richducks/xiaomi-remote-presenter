"use strict";
const vm=require("node:vm");
const fs=require("node:fs");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,
  "../chatgpt-web/xiaomi-video-speed.user.js"),"utf8");

function boot({engineEnabled=true,pip=true,sourceInputFocused=false,
               startRate=1.5,eventTargetMatches=true,
               eventKind="speed_down"}={}) {
  let playbackRate=startRate;
  let writes=0;
  let requests=0;
  let heartbeat=null;
  const timers=[];
  const reports=[];
  const keyEvents=[];
  const sourceVideo={
    readyState:4,ended:false,paused:false,videoWidth:1280,videoHeight:720,
    get playbackRate(){return playbackRate;},
    set playbackRate(rate){writes++;playbackRate=rate;},
  };
  const document={
    title:"Playing from Firefox native PiP",
    visibilityState:"hidden",
    hasFocus:()=>false,
    activeElement:{tagName:sourceInputFocused?"INPUT":"BODY",
                   isContentEditable:false},
    querySelectorAll:s=>s==="video"?[sourceVideo]:[],
    addEventListener:()=>{},
  };
  const window={
    addEventListener:()=>{},
    dispatchEvent:e=>{
      keyEvents.push(e);
      // The mock represents the already installed Global Speed extension,
      // not part of the Xiaomi helper itself.
      if(engineEnabled&&e.type==="keydown"){
        if(e.code==="KeyA")sourceVideo.playbackRate=Math.round((playbackRate-.1)*10)/10;
        if(e.code==="KeyD")sourceVideo.playbackRate=Math.round((playbackRate+.1)*10)/10;
      }
      return true;
    },
  };
  class KeyboardEvent {
    constructor(type,opts){this.type=type;Object.assign(this,opts);}
  }
  function GM_xmlhttpRequest(opts) {
    if(opts.url.includes("/video/heartbeat")){
      heartbeat=JSON.parse(opts.data);
      opts.onload({responseText:'{"ok":true}'});
    }else if(opts.url.includes("/video/next")){
      const data=requests++===0 ? {cursor:0,events:[]} :
        {cursor:1,events:[{type:eventKind,pip,
          engine:"global-speed",browser:"firefox",
          target:eventTargetMatches ? heartbeat.id : "another-client"}]};
      opts.onload({responseText:JSON.stringify(data)});
    }else if(opts.url.includes("/video/report")){
      reports.push(JSON.parse(opts.data));
      opts.onload({responseText:'{"ok":true}'});
    }else{
      opts.onload({responseText:'{}'});
    }
  }
  vm.runInNewContext(source,{
    globalThis:{},document,window,KeyboardEvent,
    location:{origin:"https://www.bilibili.com",pathname:"/video/BV123"},
    navigator:{userAgent:"Mozilla/5.0 Firefox/157.0"},
    GM_xmlhttpRequest,Date,Math,
    setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},
    setInterval:()=>{},
  });
  function fire(ms){
    const idx=timers.findIndex(t=>t.ms===ms);
    if(idx<0)throw new Error("No scheduled timer for "+ms+"ms");
    const timer=timers.splice(idx,1)[0];
    timer.fn();
  }
  return {
    heartbeat,reports,keyEvents,fire,
    get playbackRate(){return playbackRate;},
    get writes(){return writes;}
  };
}
module.exports={boot,source};
