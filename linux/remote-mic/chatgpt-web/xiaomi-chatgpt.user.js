// ==UserScript==
// @name         Xiaomi Remote → ChatGPT Web
// @namespace    local.xiaomi.remote.chatgpt
// @version      0.3.1
// @description  Xiaomi Bluetooth Voice Remote 2 Pro controls ChatGPT Web dictation.
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(() => {
  'use strict';
  const API = 'http://127.0.0.1:18766';
  let cursor = 0;
  const START_LABELS = ['听写','开始听写','语音输入','开始语音输入','Start dictation','Dictate','Dictate button','Start voice input'];
  const STOP_LABELS = ['停止听写','停止录音','Stop dictation','Stop recording'];
  const SEND_LABELS = ['发送','Send prompt','Send'];
  const COMPOSER = '#prompt-textarea,[data-testid="prompt-textarea"],[contenteditable="true"][role="textbox"]';

  const visible = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const buttonMeta = b => {
    const r=b.getBoundingClientRect();
    return {
      aria:b.getAttribute('aria-label'), title:b.getAttribute('title'), testid:b.getAttribute('data-testid'),
      text:(b.innerText||'').trim().slice(0,80), disabled:!!b.disabled,
      childTestids:[...b.querySelectorAll('[data-testid]')].map(x=>x.getAttribute('data-testid')).filter(Boolean).slice(0,10),
      svgAria:[...b.querySelectorAll('svg')].map(x=>x.getAttribute('aria-label')).filter(Boolean).slice(0,5),
      x:Math.round(r.left), y:Math.round(r.top), w:Math.round(r.width), h:Math.round(r.height)
    };
  };
  const composer = () => document.querySelector(COMPOSER);
  const composerRoot = () => composer()?.closest('form') || composer()?.parentElement?.parentElement?.parentElement || document.body;
  const visibleComposerButtons = () => [...composerRoot().querySelectorAll('button')].filter(visible);
  const textOf = b => [b.getAttribute('aria-label'),b.getAttribute('title'),b.getAttribute('data-testid'),b.innerText,
    ...[...b.querySelectorAll('[data-testid]')].map(x=>x.getAttribute('data-testid')),
    ...[...b.querySelectorAll('svg')].map(x=>x.getAttribute('aria-label'))].filter(Boolean).join(' ').toLowerCase();
  function exactLabel(labels) {
    for (const b of visibleComposerButtons()) {
      const vals=[b.getAttribute('aria-label'),b.getAttribute('title')].filter(Boolean).map(x=>x.trim());
      if (labels.some(l=>vals.includes(l)) && !b.disabled && b.getAttribute('aria-disabled')!=='true') return b;
    }
    return null;
  }
  function findStart() {
    let b=exactLabel(START_LABELS); if (b) return b;
    for (const x of visibleComposerButtons()) {
      if (x.disabled || x.getAttribute('aria-disabled')==='true') continue;
      const t=textOf(x);
      if (/(dictat|microphone|\bmic\b|speech|听写|语音输入)/i.test(t) && !/(stop|停止|cancel|取消|send|发送)/i.test(t)) return x;
    }
    return null;
  }
  function findStop() {
    let b=exactLabel(STOP_LABELS); if (b) return b;
    for (const x of visibleComposerButtons()) {
      if (x.disabled || x.getAttribute('aria-disabled')==='true') continue;
      const t=textOf(x);
      if (/(stop.*dictat|stop.*record|停止.*听写|停止.*录音)/i.test(t)) return x;
    }
    return null;
  }
  function findSend() {
    let b=exactLabel(SEND_LABELS); if (b) return b;
    return visibleComposerButtons().find(x => /send-button|composer-submit/i.test(textOf(x)) && !x.disabled) || null;
  }
  const probe = () => ({
    href:location.href,title:document.title,composer:!!composer(),composerText:composer()?.innerText||'',
    start:!!findStart(),stop:!!findStop(),send:!!findSend(),
    buttons:visibleComposerButtons().slice(-24).map(buttonMeta)
  });
  function report(payload) {
    GM_xmlhttpRequest({method:'POST',url:API+'/status',headers:{'Content-Type':'application/json'},data:JSON.stringify(payload),timeout:3000});
  }
  function clickStart() {
    const b=findStart();
    if (!b) return {ok:false,event:'voice_start',reason:'start-not-found',probe:probe()};
    b.click(); return {ok:true,event:'voice_start',button:buttonMeta(b)};
  }
  function clickStop() {
    const b=findStop();
    if (!b) return {ok:false,event:'voice_stop',reason:'stop-not-found',probe:probe()};
    b.click();
    const before=probe();
    setTimeout(()=>report({ok:true,event:'post_stop_750ms',probe:probe()}),750);
    setTimeout(()=>report({ok:true,event:'post_stop_2500ms',probe:probe()}),2500);
    setTimeout(()=>report({ok:true,event:'post_stop_5000ms',probe:probe()}),5000);
    return {ok:true,event:'voice_stop',button:buttonMeta(b),probe:before};
  }
  function handle(type) {
    let result={ok:false,event:type};
    if(type==='voice_start') result=clickStart();
    else if(type==='voice_stop') result=clickStop();
    else if(type==='send') { const b=findSend(); if(b){b.click();result={ok:true,event:type,button:buttonMeta(b)}} else result={ok:false,event:type,reason:'send-not-found',probe:probe()}; }
    else if(type==='inspect') result={ok:true,event:'inspect',probe:probe()};
    report(result);
  }
  function poll() {
    GM_xmlhttpRequest({method:'GET',url:`${API}/next?cursor=${cursor}`,timeout:30000,
      onload:r=>{try{const d=JSON.parse(r.responseText||'{}');if(Number.isFinite(d.cursor))cursor=d.cursor;for(const e of(d.events||[]))handle(e.type)}catch(e){report({ok:false,event:'poll_parse_error',error:String(e)})}setTimeout(poll,20)},
      ontimeout:()=>setTimeout(poll,50),onerror:()=>setTimeout(poll,500)});
  }
  report({ok:true,event:'userscript_ready',version:'0.3.1',probe:probe()});
  poll();
})();
