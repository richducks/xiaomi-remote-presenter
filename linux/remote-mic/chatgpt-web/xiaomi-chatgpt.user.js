// ==UserScript==
// @name         Xiaomi Remote → ChatGPT Web
// @namespace    local.xiaomi.remote.chatgpt
// @version      0.6.0
// @description  RC003 hold-to-dictate; release to preview; press OK to send.
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-idle
// @updateURL    http://127.0.0.1:18766/xiaomi-chatgpt.meta.js
// @downloadURL  http://127.0.0.1:18766/xiaomi-chatgpt.user.js
// ==/UserScript==
(() => {
  'use strict';
  // Do not register duplicate long polls if a script is reinjected.
  if (window.__xiaomiChatGPTRemoteV4) return;
  window.__xiaomiChatGPTRemoteV4 = true;
  if (location.origin !== 'https://chatgpt.com') return;
  const API = 'http://127.0.0.1:18766';
  const id = (globalThis.crypto?.randomUUID?.() || String(Date.now())+'-'+Math.random()).slice(0,100);
  let cursor = -1;
  const START_LABELS = ['听写','开始听写','语音输入','开始语音输入','Start dictation','Dictate','Dictate button','Start voice input'];
  const STOP_LABELS = ['停止听写','停止录音','提交听写','完成听写','结束听写','结束录音','发送听写','Stop dictation','Stop recording','Submit dictation','Finish dictation','Done dictating'];
  const SEND_LABELS = ['发送','发送消息','发送提示词','Send prompt','Send','Send message','Send dictated message'];
  const NEW_LABELS = ['新聊天','新建聊天','新增聊天','新对话','New chat','Start new chat'];
  const COMPOSER = '#prompt-textarea,[data-testid="prompt-textarea"],[contenteditable="true"][data-lexical-editor="true"],[contenteditable="true"][role="textbox"]';
  const visible = el => {
    if (!el) return false;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
  };
  const enabled = b => b && !b.disabled && b.getAttribute('aria-disabled')!=='true';
  const labels = b => [b.getAttribute('aria-label'),b.getAttribute('title'),b.getAttribute('data-testid'),
    b.innerText, ...[...b.querySelectorAll('[data-testid]')].map(x=>x.getAttribute('data-testid'))]
    .filter(Boolean).map(x=>x.trim());
  const buttonMeta = b => ({label:b.getAttribute('aria-label'),testid:b.getAttribute('data-testid')});
  const composer = () => [...document.querySelectorAll(COMPOSER)].find(visible) || null;
  const composerRoot = () => composer()?.closest('form') || composer()?.parentElement?.parentElement?.parentElement || null;
  const composerButtons = () => [...(composerRoot()?.querySelectorAll('button')||[])].filter(x=>visible(x)&&enabled(x));
  const exact = (collection, names) => collection.find(b => labels(b).some(x=>names.includes(x))) || null;
  const findStart = () => exact(composerButtons(), START_LABELS) ||
    composerButtons().find(b => labels(b).some(x=>/^(start dictation|dictate button|开始听写|语音输入)$/i.test(x))) || null;
  // Current ChatGPT Web can hide the original composer while dictating.
  // Only match explicit recording controls when searching page-wide.
  const stopCandidates = () => [...document.querySelectorAll('button,[role="button"]')]
    .filter(x=>visible(x)&&enabled(x));
  const findStop = () => exact(composerButtons(), STOP_LABELS) ||
    exact(stopCandidates(), STOP_LABELS) ||
    stopCandidates().find(b=>labels(b).some(x=>/^(?:(?:dictation|recording|voice[-_ ]?input)[-_ ]*(?:stop|submit|finish|done)|(?:stop|submit|finish)[-_ ]*(?:dictation|recording))$/i.test(x))) || null;
  const findSend = () => exact(composerButtons(), SEND_LABELS) ||
    composerButtons().find(b=>labels(b).some(x=>/^(send-button|composer-submit-button|composer-submit)$/i.test(x))) || null;
  function findNewChat() {
    const candidates = [...document.querySelectorAll('a,button,[role="button"]')]
      .filter(b=>visible(b)&&enabled(b));
    return exact(candidates, NEW_LABELS) ||
      candidates.find(b=>b.getAttribute('data-testid')==='new-chat-button') ||
      candidates.find(b=>b.matches('a[href="/"]') && /(new chat|新聊天|新建聊天)/i.test((b.innerText||'').trim())) ||
      null;
  }
  const hasDraft = () => Boolean(((composer()?.innerText || composer()?.value || composer()?.textContent)||'').trim());
  const probe = () => ({url:location.origin,composer:!!composer(),draftPresent:hasDraft(),
    start:!!findStart(),stop:!!findStop(),send:!!findSend(),newChat:!!findNewChat()});
  function request(method,path,data,done) {
    GM_xmlhttpRequest({method,url:API+path,
      headers:{'Content-Type':'application/json','X-Xiaomi-ChatGPT':'1'},
      data:data===undefined?undefined:JSON.stringify(data),timeout:10000,
      onload:done||(()=>{}),ontimeout:()=>{},onerror:()=>{}});
  }
  function report(payload) {
    // No transcription text, prompt or browser history in logs.
    request('POST','/status',payload);
  }
  function heartbeat() {
    request('POST','/chatgpt/heartbeat',{id,url:location.origin,version:3,
      visible:document.visibilityState==='visible',focused:document.hasFocus(),
      draftReady:hasDraft() && !findStop() && !voiceSession});
  }
  // Pair BLE voice_start/voice_release in one remote-owned dictation session.
  // Transcription is preview-only. Sending always requires a separate OK.
  let voiceSession = null;
  const inForeground = () =>
    document.visibilityState==='visible' && document.hasFocus() &&
    location.origin==='https://chatgpt.com';
  const draftText = () => ((composer()?.innerText || composer()?.value ||
    composer()?.textContent) || '').trim();
  function voiceFailure(session,reason) {
    if (voiceSession!==session) return;
    voiceSession=null;
    heartbeat();
    report({ok:false,event:'voice_transcription',reason});
  }
  function finishVoice(session) {
    if (voiceSession!==session) return;
    if (!inForeground()) return voiceFailure(session,'lost-focus');
    const now=Date.now();
    if (session.phase==='stopping') {
      // Dictation may replace the composer. Retry finding the stop button
      // briefly after the BLE stop event instead of clicking other controls.
      const stop=findStop();
      if (stop) {
        stop.click();
        session.phase='transcribing';
        session.lastText='';
        session.stableSince=0;
        report({ok:true,event:'voice_stop_clicked',button:buttonMeta(stop)});
      } else if (now-session.stoppedAt>5000) {
        return voiceFailure(session,'stop-button-not-found');
      }
    } else if (session.phase==='transcribing') {
      if (now-session.stoppedAt>25000) return voiceFailure(session,'transcription-timeout');
      // Only mark the new transcription ready. NEVER click Send here.
      if (!findStop()) {
        const content=draftText();
        if (content && content!==session.initialDraft && findSend()) {
          if (content!==session.lastText) {
            session.lastText=content;
            session.stableSince=now;
          } else if (now-session.stableSince>=900) {
            voiceSession=null;
            heartbeat(); // Make the OK button eligible without a 2s delay.
            report({ok:true,event:'voice_transcription_ready'});
            return;
          }
        } else {
          session.lastText='';
          session.stableSince=0;
        }
      }
    }
    setTimeout(()=>finishVoice(session),200);
  }
  function act(type) {
    if (!inForeground()) return {ok:false,event:type,reason:'lost-focus'};
    if (type==='inspect') return {ok:true,event:type,probe:probe()};
    if (type==='voice_release') {
      if (!voiceSession || voiceSession.phase!=='recording')
        return {ok:false,event:type,reason:'no-matched-voice-start'};
      voiceSession.phase='stopping';
      voiceSession.stoppedAt=Date.now();
      finishVoice(voiceSession);
      return {ok:true,event:type,reason:'finalizing'};
    }
    if (type==='voice_start') {
      if (voiceSession) return {ok:false,event:type,reason:'session-in-progress'};
      if (hasDraft()) return {ok:false,event:type,reason:'existing-draft'};
      if (findStop()) return {ok:false,event:type,reason:'already-recording'};
      const start=findStart();
      if (!start) return {ok:false,event:type,reason:'button-not-found',probe:probe()};
      const initialDraft=draftText();
      start.click();
      voiceSession={phase:'recording',initialDraft};
      heartbeat();
      return {ok:true,event:type,button:buttonMeta(start)};
    }
    if (voiceSession && (type==='new_chat'||type==='voice_toggle'||type==='send'))
      return {ok:false,event:type,reason:'voice-session-in-progress'};
    let b=null;
    if (type==='new_chat') {
      if (hasDraft() || findStop()) return {ok:false,event:type,reason:'draft-or-recording'};
      b=findNewChat();
    } else if (type==='voice_toggle') {
      b=findStop()||findStart();
    } else if (type==='send') {
      if (findStop()) return {ok:false,event:type,reason:'finish-dictation-first'};
      if (!hasDraft()) return {ok:false,event:type,reason:'empty-message'};
      b=findSend();
    } else return {ok:false,event:type,reason:'unknown'};
    if (!b) return {ok:false,event:type,reason:'button-not-found',probe:probe()};
    b.click();
    if (type==='send') heartbeat();
    return {ok:true,event:type,button:buttonMeta(b)};
  }
  function poll() {
    GM_xmlhttpRequest({method:'GET',url:API+'/next?cursor='+cursor+'&client='+encodeURIComponent(id),
      timeout:30000,
      onload:r=>{
        try {
          const d=JSON.parse(r.responseText||'{}');
          if (Number.isFinite(d.cursor)) cursor=d.cursor;
          for(const e of d.events||[]) report(act(e.type));
        } catch(e) {report({ok:false,event:'poll-error',error:String(e).slice(0,120)});}
        setTimeout(poll,50);
      },
      ontimeout:()=>setTimeout(poll,100),
      onerror:()=>setTimeout(poll,1000)});
  }
  let inputHeartbeatTimer=null;
  document.addEventListener('input',()=>{
    if (inputHeartbeatTimer!==null) clearTimeout(inputHeartbeatTimer);
    inputHeartbeatTimer=setTimeout(()=>{inputHeartbeatTimer=null;heartbeat();},150);
  },true);
  document.addEventListener('visibilitychange',heartbeat);
  window.addEventListener('focus',heartbeat);
  window.addEventListener('blur',heartbeat);
  heartbeat();
  setInterval(heartbeat,2000);
  report({ok:true,event:'userscript_ready',version:'0.6.0',probe:probe()});
  poll();
})();
