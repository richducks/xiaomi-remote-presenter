#!/usr/bin/env python3
"""Independent Jobs-style product checks of the *candidate* Electron resources.

Run with a separate official Electron runtime containing current source files
in resources/app. Never modifies remote rules or emits hardware input.
Requires Python websockets for local Chromium DevTools inspection.
"""
from __future__ import annotations
import asyncio
import base64
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import urllib.request
import websockets

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'qa/runtime/electron'
MISSING_BACKEND="--missing-backend" in sys.argv
PORT=9254 if MISSING_BACKEND else 9253

async def inspect():
    proc=subprocess.Popen([str(RUNTIME),'--no-sandbox','--disable-gpu',
                           '--remote-debugging-port='+str(PORT)],
                          stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                          text=True,start_new_session=True,
                          env=dict(os.environ,XIAOMI_REMOTE_HOME=(
                              '/tmp/rc003-qa-backend-does-not-exist'
                              if MISSING_BACKEND else str(ROOT))))
    try:
        url=None
        for _ in range(40):
            await asyncio.sleep(.3)
            if proc.poll() is not None:break
            try:
                with urllib.request.urlopen('http://127.0.0.1:'+str(PORT)+'/json/list',timeout=.8) as response:
                    targets=json.load(response)
                url=next((t['webSocketDebuggerUrl'] for t in targets if t.get('type')=='page'
                          and t.get('url','').startswith('file:')),None)
                if url:break
            except Exception:pass
        assert url is not None,'candidate Electron page did not launch'
        async with websockets.connect(url,open_timeout=4,max_size=20000000) as ws:
            serial=0
            async def command(method,params=None):
                nonlocal serial
                serial+=1
                ident=serial
                await ws.send(json.dumps({'id':ident,'method':method,'params':params or {}}))
                while True:
                    data=json.loads(await asyncio.wait_for(ws.recv(),timeout=8))
                    if data.get('id')==ident:
                        assert 'error' not in data,data
                        return data['result']
            async def evaluate(js):
                data=await command('Runtime.evaluate',{
                    'expression':js,'returnByValue':True,'awaitPromise':True})
                assert 'exceptionDetails' not in data,data
                return data['result'].get('value')
            await command('Page.enable')
            if MISSING_BACKEND:
                state={}
                for _ in range(18):
                    state=await evaluate("({warning:document.querySelector('#overview-note')?.textContent,summary:document.querySelector('#connection-summary')?.textContent,dot:document.querySelector('#connection-dot')?.className})")
                    if '还没有安装' in (state.get('warning') or ''):break
                    await asyncio.sleep(.3)
                print('missing-backend:',state)
                assert '还没有安装 Linux Python 后端' in state['warning']
                assert state['summary']=='等待安装后端' and state['dot']=='dot bad'
                print('PASS: missing-backend fail-closed first-run flow')
                return
            value={}
            for _ in range(30):
                value=await evaluate("({url:location.href,pages:document.querySelectorAll('section.page').length,rules:document.querySelectorAll('.rule-row').length,service:document.querySelector('#metric-services')?.textContent,nav:[...document.querySelectorAll('.nav-group')].map(e=>e.textContent.trim())})")
                if value['rules']==11 and value['service']!='—':break
                await asyncio.sleep(.3)
            print('first-use:',value)
            assert '/qa/runtime/resources/app/index.html' in value['url']
            assert value['pages']==8 and value['rules']==11
            active=await evaluate("document.querySelectorAll('.sidebar .nav.active').length")
            assert active==1,"initial navigation must have exactly one active page"

            assert any('系统' in x for x in value['nav'])
            assert any('应用' in x for x in value['nav'])
            assert any('独立' in x for x in value['nav'])
            await evaluate("document.querySelector('.nav[data-page=system]').click()")
            system=await evaluate("({visible:document.querySelector('#page-system').classList.contains('active'),count:document.querySelectorAll('#system-key-list .system-key').length,power:document.querySelector('#system-key-list').textContent.includes('电源键'),warning:document.querySelector('#page-system').textContent.includes('硬件已经实测')})")
            print('system-page:',system)
            assert system['visible'] and system['count']==7 and system['power'] and system['warning']
            screenshot=await command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
            (ROOT/'qa/system-desktop.png').write_bytes(base64.b64decode(screenshot['data']))
            await evaluate("document.querySelector('.nav[data-page=browser]').click();document.querySelector('.add-rule[data-scope=browser]').click()")
            options=await evaluate("({dialog:document.querySelector('#rule-dialog').open,inputs:[...document.querySelector('#rule-input').options].map(o=>o.value)})")
            print('app-picker:',len(options['inputs']), 'options; no power/volume')
            assert options['dialog']
            assert not any(x in options['inputs'] for x in ['KEY_POWER','KEY_SLEEP','KEY_VOLUMEUP','KEY_VOLUMEDOWN'])
            await evaluate("document.querySelector('#rule-dialog button[value=cancel]').click()")
            assert not await evaluate("document.querySelector('#rule-dialog').open")
            defaults=await evaluate("window.remote.defaultRules().then(x=>({count:x.rules.length,version:x.version}))")
            assert defaults=={'count':11,'version':1}
            print('default-source:',defaults)
            await evaluate("document.querySelector('.nav[data-page=overview]').click()")
            dest=ROOT/'qa';dest.mkdir(exist_ok=True)
            shot=await command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
            (dest/'overview-desktop.png').write_bytes(base64.b64decode(shot['data']))
            await command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
            await asyncio.sleep(.7)
            mobile=await evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,pickerVisible:getComputedStyle(document.querySelector('.mobile-picker-wrap')).display!=='none',menuCount:document.querySelectorAll('#mobile-page optgroup').length,firstSteps:document.querySelector('.first-steps')?.textContent,saveHidden:document.querySelector('#saveAll')?.hidden})")
            print('mobile:',mobile)
            assert mobile['scroll']<=mobile['width']+5
            assert mobile['pickerVisible'] and mobile['menuCount']>=5 and mobile['saveHidden']
            shot=await command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
            (dest/'overview-mobile.png').write_bytes(base64.b64decode(shot['data']))
            print('PASS: 8 pages, 3 layers, system protection, picker, defaults, mobile layout')
    finally:
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:
            err=proc.communicate(timeout=5)[1]
            if 'FATAL:' in err:print('Electron runtime warnings:',err[-650:])
        except subprocess.TimeoutExpired:pass

if __name__=='__main__':
    asyncio.run(inspect())
