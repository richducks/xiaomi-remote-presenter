// ==UserScript==
// @name         小米遥控器 2 Pro - Chrome / Firefox 视频倍速
// @namespace    local.xiaomi.remote.video.speed
// @version      0.5.0
// @updateURL    http://127.0.0.1:18766/xiaomi-video-speed.user.js
// @downloadURL  http://127.0.0.1:18766/xiaomi-video-speed.user.js
// @description  仅 Firefox 原生画中画时转发遥控器 D/A 给已安装的 Global Speed；不会直接更改播放速度。
// @match        https://*/*
// @match        http://*/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-start
// @all-frames   true
// ==/UserScript==

(() => {
  "use strict";
  // Normal video speed is ALWAYS handled by physical Xiaomi D/A through
  // the installed Global Speed extension, not by this userscript.
  if (!/Firefox/i.test(navigator.userAgent)) return;
  if (globalThis.__xiaomiRemoteGlobalSpeedPiP_v5) return;
  globalThis.__xiaomiRemoteGlobalSpeedPiP_v5 = true;

  const BASE = "http://127.0.0.1:18766";
  const CLIENT = "gsv5-" + Date.now().toString(36) +
    Math.random().toString(36).slice(2);
  const VERSION = 5;
  let cursor = -1;
  let polling = false;

  function http(method, path, body, onload, retry) {
    try {
      GM_xmlhttpRequest({
        method,
        url: BASE + path,
        timeout: 28000,
        headers: {
          "X-Xiaomi-Video":"1",
          ...(body ? {"Content-Type":"application/json"} : {}),
        },
        data:body ? JSON.stringify(body) : undefined,
        onload,
        ontimeout:()=>retry && retry(),
        onerror:()=>retry && retry(),
      });
    } catch (err) {
      if (retry) retry();
    }
  }

  function activeVideo() {
    try {
      const videos=[...document.querySelectorAll("video")].filter(v =>
        v.readyState >= 1 && !v.ended && (v.videoWidth || 0) >= 40);
      videos.sort((a,b) =>
        Number(!b.paused)-Number(!a.paused) ||
        (b.videoWidth*b.videoHeight)-(a.videoWidth*a.videoHeight));
      return videos[0] || null;
    } catch (_) {
      return null;
    }
  }

  function report(kind, key, before, after, reason = "") {
    const sign=kind==="speed_up" ? 1 : -1;
    const changed=Number.isFinite(after) && Number.isFinite(before) &&
      (after-before)*sign>0.035;
    http("POST","/video/report", {
      id:CLIENT,engine:"global-speed", pip:true, type:kind,
      key,before,speed:after,ok:changed,
      reason:changed ? "" : reason || "global-speed-not-observed",
      url:location.origin+location.pathname,
    },()=>{},()=>{});
  }

  function sendGlobalSpeedKey(kind) {
    const video=activeVideo();
    if (!video) {
      report(kind,"",0,0,"video-no-longer-present");
      return;
    }
    // Only forward a keyboard event. Global Speed's installed WebExtension
    // is the *sole* component authorized to update video.playbackRate.
    const code=kind==="speed_up" ? "KeyD" : "KeyA";
    const key=kind==="speed_up" ? "d" : "a";
    const before=Number(video.playbackRate);
    const focused=document.activeElement;
    // Never inject shortcuts while the source frame's user input is active.
    if (focused && (
      ["INPUT","TEXTAREA","SELECT"].includes(focused.tagName) ||
      focused.isContentEditable
    )) {
      report(kind,code,before,before,"source-text-input-focused");
      return;
    }
    try {
      const opts={bubbles:true,cancelable:true,composed:true,
        code,key,ctrlKey:false,shiftKey:false,altKey:false,metaKey:false,
        repeat:false};
      window.dispatchEvent(new KeyboardEvent("keydown",opts));
      window.dispatchEvent(new KeyboardEvent("keyup",opts));
    } catch (err) {
      report(kind,code,before,before,"keyboard-event-error:"+String(err));
      return;
    }
    // Observe the rate AFTER Global Speed had time to process the key.
    // No alternate playback-rate engine, not even an emergency fallback.
    setTimeout(() => {
      report(kind,code,before,Number(video.playbackRate));
    },750);
  }

  function heartbeat() {
    const video=activeVideo();
    http("POST","/video/heartbeat",{
      id:CLIENT,version:VERSION,browser:"firefox",
      visible:true, has_video:!!video,
      playing:!!video && !video.paused,
      focused:document.hasFocus(),
      title:document.title,origin:location.origin,
    },()=>{},()=>{});
    if (video && !polling) {
      polling=true;
      poll();
    }
  }

  function poll() {
    if (!activeVideo()) {
      polling=false;
      return;
    }
    http("GET","/video/next?cursor="+cursor+
      "&client="+encodeURIComponent(CLIENT),null,response=>{
      try {
        const packet=JSON.parse(response.responseText || "{}");
        if (Number.isInteger(packet.cursor)) cursor=packet.cursor;
        for (const event of packet.events || []) {
          if (event.pip === true && event.browser === "firefox" &&
              event.engine === "global-speed" &&
              event.target === CLIENT &&
              (event.type === "speed_up" || event.type === "speed_down")) {
            sendGlobalSpeedKey(event.type);
          }
        }
      } catch (_) {}
      setTimeout(poll,35);
    },()=>setTimeout(poll,650));
  }

  document.addEventListener("visibilitychange",heartbeat);
  window.addEventListener("focus",heartbeat);
  window.addEventListener("blur",heartbeat);
  setInterval(heartbeat,1700);
  heartbeat();
})();
