'use strict';
// Exercise the real ChatGPT userscript in a constrained DOM/GM bridge stub.
// No browser dependencies, no message text leaves the test.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../chatgpt-web/xiaomi-chatgpt.user.js'),'utf8');
function element(name='',text='',testid='') {
  const clicks=[];
  const el={innerText:text,textContent:text,disabled:false,
    getBoundingClientRect:()=>({width:100,height:40}),
    getAttribute:k=>({'aria-label':name,'title':null,'data-testid':testid,'aria-disabled':null}[k]??null),
    querySelectorAll:()=>[],
    matches:()=>false,click:()=>clicks.push('clicked')};
  return {el,clicks};
}
function harness() {
  const newChat=element('New chat');
  const start=element('Start dictation');
  const stop=element('Submit dictation');
  const send=element('Send prompt','','send-button');
  let draft='';
  let recording=false, focused=true, visible=true;
  const form={querySelectorAll:()=>recording?[stop.el,send.el]:[start.el,send.el]};
  const input={closest:()=>form,getBoundingClientRect:()=>({width:100,height:40}),innerText:'',get textContent(){return draft;},get value(){return draft;}};
  Object.defineProperty(input,'innerText',{get:()=>draft});
  const doc={querySelectorAll:sel=>sel.includes('#prompt-textarea')?[input]:sel==='a,button,[role="button"]'?[newChat.el]:[],
    get visibilityState(){return visible?'visible':'hidden';},
    hasFocus:()=>focused,
    addEventListener:()=>{}};
  const log=[];let pollReq;
  const context={location:{origin:'https://chatgpt.com'},document:doc,
    window:{addEventListener:()=>{}},getComputedStyle:()=>({display:'block',visibility:'visible'}),
    setTimeout:callback=>callback(),setInterval:()=>{},Date,Math,console,
    GM_xmlhttpRequest:x=>{
      if(x.method==='GET'){pollReq=x;return}
      if(x.url.endsWith('/status')) log.push(JSON.parse(x.data));
    }};
  context.globalThis=context;
  vm.runInNewContext(source,context);
  function action(type){
    const request=pollReq;
    assert.ok(request, 'poll registered');
    pollReq=undefined;
    request.onload({responseText:JSON.stringify({cursor:log.length+1,events:[{type}]})});
    return log[log.length-1];
  }
  return {action,newChat,start,stop,send,log,setDraft:x=>draft=x,setRecording:x=>recording=x,setFocus:x=>focused=x,setVisible:x=>visible=x};
}
{
 const h=harness();
 assert.equal(h.action('send').reason,'empty-message');
 assert.equal(h.send.clicks.length,0);
 assert.equal(h.action('new_chat').ok,true);
 assert.equal(h.newChat.clicks.length,1);
 h.setDraft('deliberately typed test prompt');
 assert.equal(h.action('new_chat').reason,'draft-or-recording');
 assert.equal(h.newChat.clicks.length,1);
 assert.equal(h.action('send').ok,true);
 assert.equal(h.send.clicks.length,1);
 assert.equal(h.action('voice_toggle').ok,true);
 assert.equal(h.start.clicks.length,1);
 h.setRecording(true);
 assert.equal(h.action('send').reason,'finish-dictation-first');
 assert.equal(h.send.clicks.length,1);
 assert.equal(h.action('voice_toggle').ok,true);
 assert.equal(h.stop.clicks.length,1);
 assert.equal(h.log.some(x=>JSON.stringify(x).includes('deliberately typed test prompt')),false,'no message content leaked');
}
{
 const h=harness();h.setFocus(false);
 assert.equal(h.action('new_chat').reason,'lost-focus');
 assert.equal(h.newChat.clicks.length,0);
}
// End-to-end BLE events: release produces an editable draft, never a send.
{
 let now=1000,scheduled=[],pollReq,recording=false,draft='',focused=true;
 const start=element('听写'),stop=element('停止听写'),send=element('发送');
 start.el.click=()=>{start.clicks.push('clicked');recording=true;};
 stop.el.click=()=>{stop.clicks.push('clicked');recording=false;};
 const form={querySelectorAll:()=>recording?[]:[start.el,send.el]};
 const input={closest:()=>form,getBoundingClientRect:()=>({width:100,height:40}),
   get innerText(){return draft;},get textContent(){return draft;},get value(){return draft;}};
 const doc={querySelectorAll:s=>s.includes('#prompt-textarea')?(recording?[]:[input]):
   s==='button,[role="button"]'?(recording?[stop.el]:[start.el,send.el]):[],
   get visibilityState(){return 'visible';},hasFocus:()=>focused,
   addEventListener:()=>{}};
 class Clock extends Date{static now(){return now;}}
 const logs=[],heartbeats=[];
 const context={location:{origin:'https://chatgpt.com'},document:doc,
   window:{addEventListener:()=>{}},getComputedStyle:()=>({display:'block',visibility:'visible'}),
   Date:Clock,Math,console,setTimeout:(callback,delay)=>scheduled.push({at:now+(delay||0),callback}),
   setInterval:()=>{},clearTimeout:()=>{},
   GM_xmlhttpRequest:x=>{
     if(x.method==='GET'){pollReq=x;return;}
     if(x.url.endsWith('/status')) logs.push(JSON.parse(x.data));
     if(x.url.endsWith('/chatgpt/heartbeat')) heartbeats.push(JSON.parse(x.data));
   }};
 context.globalThis=context;
 vm.runInNewContext(source,context);
 function advance(ms){
   const target=now+ms;let n=0;
   while(true){
     scheduled.sort((a,b)=>a.at-b.at);
     if(!scheduled.length||scheduled[0].at>target)break;
     const t=scheduled.shift();now=t.at;t.callback();
     assert.ok(++n<1000,'bounded transcription timer');
   }
   now=target;
 }
 function action(type){
   if(!pollReq)advance(60);
   assert.ok(pollReq,'poll running');
   const req=pollReq;pollReq=undefined;
   req.onload({responseText:JSON.stringify({cursor:now+1,events:[{type}]})});
 }
 action('voice_start');
 assert.equal(start.clicks.length,1);
 action('voice_release');
 assert.equal(stop.clicks.length,1,'stop found outside hidden composer');
 advance(250);draft='recognized voice draft';advance(1800);
 assert.equal(send.clicks.length,0,'release MUST NOT submit');
 assert.ok(logs.some(x=>x.event==='voice_transcription_ready'&&x.ok));
 assert.ok(heartbeats.some(x=>x.version===3&&x.draftReady===true));
 action('send');
 assert.equal(send.clicks.length,1,'only explicit OK-backed send action submits');
 advance(2000);
 assert.equal(send.clicks.length,1,'no delayed duplicate send');
 assert.equal(logs.some(x=>JSON.stringify(x).includes(draft)),false,'speech is private');
}
console.log('CHATGPT_USER_SCRIPT_TEST_PASSED new chat / guarded send / dictation / focus / privacy');
