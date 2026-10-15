#!/usr/bin/env python3
from __future__ import annotations
import asyncio, json, logging, signal, subprocess, time
from pathlib import Path
from collections import deque
from contextlib import suppress
from aiohttp import web
from wechat_dictation import WechatDictation, wechat_window, prewarm_wechat_keyboard

LOG=logging.getLogger('xiaomi-chatgpt-web-bridge')
REMOTE_SOURCE='xiaomi_remote_mic_sink.monitor'

class Bridge:
    def __init__(self):
        self.seq=0; self.events=deque(maxlen=200); self.cond=asyncio.Condition()
        self.previous_source=None; self.restore_task=None
        self.video_seq=0
        self.video_events=deque(maxlen=64)
        self.video_clients={}
        self.video_results=deque(maxlen=30)
        # ChatGPT tabs report foreground presence; no window-title guesses.
        self.chatgpt_clients={}
        self.chatgpt_action_time={}
        self.wechat = WechatDictation()
    def active_chatgpt_client(self):
        now=time.monotonic()
        self.chatgpt_clients={cid:data for cid,data in self.chatgpt_clients.items()
                              if now-data['seen']<6}
        focused=[cid for cid,data in self.chatgpt_clients.items()
                 if data['visible'] and data['focused'] and data['version']>=2]
        return focused[0] if len(focused)==1 else None

    async def chatgpt_heartbeat(self,request):
        if request.headers.get('X-Xiaomi-ChatGPT')!='1' or request.headers.get('Origin') not in (None,'https://chatgpt.com'):
            return web.Response(status=403)
        try:
            d=await request.json()
            cid=d.get('id')
            if not isinstance(cid,str) or not 8<=len(cid)<=100:
                raise ValueError('invalid client')
            if d.get('url')!='https://chatgpt.com':
                raise ValueError('not ChatGPT origin')
            self.chatgpt_clients[cid]={
                'seen':time.monotonic(),'visible':d.get('visible') is True,
                'focused':d.get('focused') is True,
                'version':int(d.get('version',0)),
                # A v0.6+ foreground script reports that draft text is
                # available and no dictation is still being finalized.
                'draft_ready':int(d.get('version',0))>=3 and d.get('draftReady') is True,
            }
            return web.json_response({'ok':True})
        except (ValueError,TypeError,KeyError):
            return web.Response(status=400)

    async def chatgpt_active(self,request):
        return web.json_response({'active':self.active_chatgpt_client() is not None})

    async def chatgpt_draft_ready(self,request):
        cid=self.active_chatgpt_client()
        return web.json_response({'ready':cid is not None and
                                  self.chatgpt_clients[cid]['draft_ready']})

    async def chatgpt_trigger(self,request):
        # Only local Python HID can request an action. Browsers must not
        # be allowed to submit messages by issuing cross-origin requests.
        if request.headers.get('Origin') is not None or request.headers.get('X-Xiaomi-Remote-HID')!='1':
            return web.Response(status=403)
        try:
            d=await request.json()
            action=d.get('action')
        except (ValueError,TypeError):
            return web.Response(status=400)
        if action not in ('new_chat','voice_toggle','send'):
            return web.Response(status=400)
        cid=self.active_chatgpt_client()
        if cid is None:
            return web.json_response({'ok':False,'reason':'no-focused-tab'},status=409)
        now=time.monotonic()
        # Guard repeats from firmware even if HID emits multiple pairs.
        if now-self.chatgpt_action_time.get(action,-float('inf'))<0.40:
            return web.json_response({'ok':False,'reason':'debounced'},status=429)
        self.chatgpt_action_time[action]=now
        await self.emit(action,target=cid)
        return web.json_response({'ok':True,'action':action})

    async def wechat_draft_ready(self, request):
        ready = await asyncio.to_thread(self.wechat.draft_ready)
        busy = self.wechat.busy() and await asyncio.to_thread(wechat_window) is not None
        return web.json_response({'ready': ready, 'busy': busy})

    async def wechat_send(self, request):
        # Local HID only. Browser pages cannot trigger WeChat messages.
        if request.headers.get('Origin') is not None or request.headers.get('X-Xiaomi-Remote-HID') != '1':
            return web.Response(status=403)
        sent = await self.wechat.send()
        return web.json_response({'ok': sent}, status=200 if sent else 409)

    def active_video_clients(self):
        now=time.monotonic()
        self.video_clients={
            k:v for k,v in self.video_clients.items()
            if now-v['seen']<(25.0 if v.get('version',1)>=5 else 5.0)
        }
        return self.video_clients

    async def video_heartbeat(self,request):
        if request.headers.get('X-Xiaomi-Video') != '1':
            return web.Response(status=403)
        try:
            data=await request.json()
            cid=str(data.get('id',''))[:100]
            if not cid or not (data.get('visible') and data.get('has_video')):
                self.video_clients.pop(cid,None)
            else:
                self.video_clients[cid]={'seen':time.monotonic(),
                    'title':str(data.get('title',''))[:120],
                    'origin':str(data.get('origin',''))[:180],
                    'focused':bool(data.get('focused')),
                    'browser':str(data.get('browser',''))[:16],
                    'version':int(data.get('version',1) or 1),
                    'playing':bool(data.get('playing',False))}
            return web.json_response({'ok':True, 'clients':len(self.active_video_clients())})
        except Exception:
            return web.json_response({'ok':False}, status=400)

    async def video_active(self,request):
        browser=request.query.get('browser','')
        active=any(c['focused'] and c['browser']==browser
                   for c in self.active_video_clients().values())
        return web.json_response({'active':active})

    async def video_emit(self,request):
        """A Firefox-native-PiP-only keyboard event for Global Speed.

        Unlike the old bridge this NEVER requests direct playbackRate edits,
        and cannot be used from ordinary Firefox/Chrome video pages.
        """
        if request.headers.get("Origin"):
            return web.Response(status=403)
        try:
            data=await request.json()
            kind=data.get("type")
            if (data.get("browser")!="firefox"
                    or data.get("pip") is not True
                    or kind not in ("speed_up","speed_down")):
                return web.json_response({
                    "ok":False,"reason":"piP-only-global-speed"
                },status=410)
            clients=[
                (cid,c) for cid,c in self.active_video_clients().items()
                if c.get("version",0)>=5
                and c.get("browser")=="firefox"
                and c.get("playing")
            ]
            if not clients:
                return web.json_response({
                    "ok":False,"reason":"no-playing-firefox-global-speed-client-v5"
                },status=409)
            # Several Firefox videos playing simultaneously: we cannot
            # reliably prove which one owns native PiP. Don't change the
            # wrong video; this is safer than picking the latest heartbeat.
            if len(clients)>1:
                return web.json_response({
                    "ok":False,"reason":"ambiguous-multiple-playing-firefox-videos"
                },status=409)
            cid,_=clients[0]
            async with self.cond:
                self.video_seq+=1
                self.video_events.append((self.video_seq,{
                    "type":kind,"browser":"firefox","pip":True,
                    "engine":"global-speed","target":cid,
                }))
                self.cond.notify_all()
            LOG.info(
                "PiP Global Speed key request seq=%s type=%s client=%s",
                self.video_seq,kind,cid[:18],
            )
            return web.json_response({"ok":True,"seq":self.video_seq})
        except Exception as error:
            LOG.warning("PiP GS emit rejected: %s",error)
            return web.Response(status=400)

    async def video_next(self,request):
        try:cursor=int(request.query.get('cursor','-1'))
        except Exception:cursor=0
        async with self.cond:
            # A newly loaded userscript should not replay stale keypresses.
            # Existing browser tabs survive systemd bridge restarts. Their
            # prior cursor may be far ahead of this new process' event seq.
            # Signal a reset immediately or all future button events vanish.
            if cursor<0 or cursor>self.video_seq:
                return web.json_response({'cursor':self.video_seq,'events':[]})
            client_id=request.query.get('client')
            def collect():
                # v0.1/v0.2 browser scripts use no client ID and modify
                # playbackRate directly. NEVER deliver targeted PiP events
                # to them, even if they're still installed.
                if not client_id:
                    return []
                return [(s,e) for s,e in self.video_events
                        if s>cursor and e.get('target')==client_id]
            items=collect()
            if not items:
                try:await asyncio.wait_for(self.cond.wait(),timeout=20)
                except asyncio.TimeoutError:pass
                items=collect()
        return web.json_response({'cursor':items[-1][0] if items else max(cursor,self.video_seq),
                                  'events':[ev for _,ev in items]})

    async def video_report(self,request):
        if request.headers.get('X-Xiaomi-Video') != '1':
            return web.Response(status=403)
        try:
            d=await request.json()
            report={'at':time.time(),'ok':bool(d.get('ok')),
                    'before':d.get('before'), 'speed':d.get('speed'),
                    'key':str(d.get('key',''))[:24],
                    'engine':str(d.get('engine',''))[:32],
                    'pip':bool(d.get('pip')),
                    'url':str(d.get('url',''))[:250],
                    'reason':str(d.get('reason',''))[:120]}
            self.video_results.append(report)
            LOG.info('video result=%s',report)
            return web.json_response({'ok':True})
        except Exception:
            return web.Response(status=400)

    async def video_debug(self,request):
        clients=self.active_video_clients()
        return web.json_response({
            'clients':len(clients),
            'client_versions':{
                browser:sorted([v['version'] for v in clients.values()
                                if v['browser']==browser])
                for browser in ('firefox','chromium')
            },
            'pip_ready':any(
                c['browser']=='firefox' and c.get('version',0)>=5
                and c.get('playing') for c in clients.values()
            ),
            'last_results':list(self.video_results)[-5:],
            'seq':self.video_seq
        })

    def pactl(self,*args):
        p=subprocess.run(['pactl',*args],text=True,capture_output=True,check=False)
        if p.returncode: LOG.warning('pactl %s failed: %s',' '.join(args),p.stderr.strip()); return ''
        return p.stdout.strip()
    async def emit(self,typ,**extra):
        async with self.cond:
            self.seq+=1; self.events.append((self.seq,{'type':typ,**extra})); self.cond.notify_all()
        LOG.info('event=%s seq=%d',typ,self.seq)
    async def next_events(self,request):
        try: cursor=int(request.query.get('cursor','0'))
        except: cursor=0
        if cursor>self.seq or cursor<0: cursor=self.seq
        async with self.cond:
            def collect(): return [(s,e) for s,e in self.events if s>cursor and (not e.get('target') or e.get('target')==request.query.get('client'))]
            items=collect()
            if not items:
                try: await asyncio.wait_for(self.cond.wait(),timeout=25)
                except asyncio.TimeoutError: pass
                items=collect()
        events=[e for _,e in items]
        new_cursor=items[-1][0] if items else max(cursor,self.seq)
        return web.json_response({'cursor':new_cursor,'events':events},headers={'Access-Control-Allow-Origin':'https://chatgpt.com'})
    async def status(self,request):
        try: data=await request.json()
        except: data={'raw':await request.text()}
        LOG.info('browser_status=%s',json.dumps(data,ensure_ascii=False,separators=(',',':')))
        return web.json_response({'ok':True},headers={'Access-Control-Allow-Origin':'https://chatgpt.com'})
    async def options(self,request):
        return web.Response(status=204,headers={'Access-Control-Allow-Origin':'https://chatgpt.com','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Content-Type'})
    async def select_remote(self):
        if self.restore_task:self.restore_task.cancel(); self.restore_task=None
        current=self.pactl('get-default-source')
        if current and current!=REMOTE_SOURCE and not self.previous_source:self.previous_source=current
        self.pactl('set-default-source',REMOTE_SOURCE); LOG.info('default source -> %s',REMOTE_SOURCE)
    async def restore_later(self):
        if self.restore_task:self.restore_task.cancel()
        self.restore_task=asyncio.create_task(self._restore())
    async def _restore(self):
        try:
            await asyncio.sleep(2.5)
            if self.previous_source:
                src=self.previous_source; self.previous_source=None; self.pactl('set-default-source',src); LOG.info('default source restored -> %s',src)
        except asyncio.CancelledError: raise
        finally:self.restore_task=None
    async def follow(self):
        p=await asyncio.create_subprocess_exec('journalctl','--user','-fu','xiaomi-remote-mic.service','-o','cat','--since','now',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        assert p.stdout is not None
        LOG.info('following xiaomi-remote-mic.service')
        try:
            while True:
                raw=await p.stdout.readline()
                if not raw:
                    if p.returncode is not None: raise RuntimeError(f'journalctl exited {p.returncode}')
                    await asyncio.sleep(.1); continue
                line=raw.decode('utf-8','replace')
                if 'ATVV control: audio_start' in line:
                    await self.select_remote()
                    try:
                        await self.wechat.start()
                    except Exception:
                        LOG.exception('optional WeChat recorder failed to start')
                    await self.emit('voice_start')
                elif 'ATVV control: audio_stop' in line:
                    try:
                        await self.wechat.stop()
                    except Exception:
                        LOG.exception('optional WeChat recorder failed to stop')
                    # Keep existing ChatGPT preview/OK behavior unchanged.
                    await self.emit('voice_release'); await self.restore_later()
        finally:
            p.terminate()
            with suppress(Exception): await asyncio.wait_for(p.wait(),timeout=2)

async def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    b=Bridge(); app=web.Application()
    async def user_script(request):
        text=Path('chatgpt-web/xiaomi-chatgpt.user.js').read_text()
        return web.Response(text=text,content_type='application/javascript')
    app.router.add_get('/xiaomi-chatgpt.user.js',user_script)
    # Old Tampermonkey installations probe this derived URL for version.
    async def chatgpt_script_metadata(request):
        source=Path('chatgpt-web/xiaomi-chatgpt.user.js').read_text(encoding='utf-8')
        header=source.split('// ==/UserScript==',1)[0]+'// ==/UserScript==\n'
        return web.Response(text=header, content_type='application/javascript')
    app.router.add_get('/xiaomi-chatgpt.meta.js',chatgpt_script_metadata)
    app.router.add_post('/chatgpt/heartbeat',b.chatgpt_heartbeat)
    app.router.add_get('/chatgpt/active',b.chatgpt_active)
    app.router.add_get('/chatgpt/draft-ready',b.chatgpt_draft_ready)
    app.router.add_post('/chatgpt/trigger',b.chatgpt_trigger)
    app.router.add_get('/wechat/draft-ready', b.wechat_draft_ready)
    app.router.add_post('/wechat/send', b.wechat_send)
    async def video_script(request):
        source=Path('chatgpt-web/xiaomi-video-speed.user.js').read_text(encoding='utf-8')
        return web.Response(text=source,content_type='application/javascript')
    app.router.add_get('/xiaomi-video-speed.user.js',video_script)
    async def video_setup(request):
        source=Path('chatgpt-web/video-setup.html').read_text(encoding='utf-8')
        return web.Response(text=source,content_type='text/html')
    app.router.add_get('/video/setup',video_setup)
    app.router.add_post('/video/heartbeat',b.video_heartbeat)
    app.router.add_post('/video/emit',b.video_emit)
    app.router.add_get('/video/active',b.video_active)
    app.router.add_get('/video/next',b.video_next)
    app.router.add_post('/video/report',b.video_report)
    app.router.add_get('/video/debug',b.video_debug)
    app.router.add_get('/next',b.next_events); app.router.add_post('/status',b.status); app.router.add_route('OPTIONS','/{tail:.*}',b.options)
    runner=web.AppRunner(app, access_log=None); await runner.setup(); site=web.TCPSite(runner,'127.0.0.1',18766); await site.start()
    LOG.info('userscript bridge listening http://127.0.0.1:18766')
    # Warm only the input device, not the STT engine; zero injected keys.
    keyboard_warmup = asyncio.create_task(prewarm_wechat_keyboard())
    stop=asyncio.Event(); loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        with suppress(NotImplementedError): loop.add_signal_handler(sig,stop.set)
    task=asyncio.create_task(b.follow()); await stop.wait(); task.cancel(); keyboard_warmup.cancel(); await asyncio.gather(task,keyboard_warmup,return_exceptions=True); await runner.cleanup()
if __name__=='__main__': asyncio.run(main())
