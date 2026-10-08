import asyncio
import importlib.util
import pathlib
import unittest
from types import SimpleNamespace

BASE = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chatgpt_web_bridge",BASE/"chatgpt_web_bridge.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class Request:
    def __init__(self, payload=None, headers=None, cursor="0"):
        self.payload = payload or {}
        self.headers = {"X-Xiaomi-Video":"1",**(headers or {})}
        self.query = {"cursor":cursor}

    async def json(self):
        return self.payload


class VideoBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge=module.Bridge()

    async def test_ordinary_speed_bridge_disabled(self):
        from json import loads
        b=self.bridge
        for ev in (
            {"type":"speed_up"},
            {"type":"speed_up","browser":"firefox","pip":False},
            {"type":"speed_down","browser":"chromium","pip":True},
        ):
            result=await b.video_emit(Request(ev))
            self.assertEqual(result.status,410)
            self.assertFalse(loads(result.text)["ok"])
        self.assertEqual(b.video_seq,0)

    async def test_pip_requires_playing_firefox_global_speed_v5(self):
        from json import loads
        b=self.bridge
        event={"type":"speed_up","browser":"firefox","pip":True}
        self.assertEqual((await b.video_emit(Request(event))).status,409)
        for v in (1,2,3,4):
            await b.video_heartbeat(Request({
                "id":"legacy"+str(v),"visible":True,"has_video":True,
                "playing":True,"browser":"firefox","version":v,
            }))
        self.assertEqual((await b.video_emit(Request(event))).status,409)
        await b.video_heartbeat(Request({
            "id":"paused-v5","visible":True,"has_video":True,
            "playing":False,"browser":"firefox","version":5,
        }))
        self.assertEqual((await b.video_emit(Request(event))).status,409)
        await b.video_heartbeat(Request({
            "id":"playing-v5","visible":True,"has_video":True,
            "playing":True,"browser":"firefox","version":5,
            "focused":False,
        }))
        response=await b.video_emit(Request(event))
        self.assertEqual(response.status,200)
        self.assertEqual(loads(response.text)["seq"],1)
        self.assertEqual(b.video_events[-1][1],{
            "type":"speed_up","browser":"firefox","pip":True,
            "engine":"global-speed","target":"playing-v5",
        })
        req=Request(cursor="0")
        req.query["client"]="playing-v5"
        stream=loads((await b.video_next(req)).text)
        self.assertEqual(len(stream["events"]),1)
        self.assertEqual(stream["events"][0]["target"],"playing-v5")
        self.assertEqual(stream["events"][0]["engine"],"global-speed")

    async def test_no_event_reaches_old_scripts_with_missing_client_id(self):
        from unittest.mock import AsyncMock,patch
        from json import loads
        b=self.bridge
        await b.video_heartbeat(Request({
            "id":"video-v5","visible":True,"has_video":True,
            "playing":True,"browser":"firefox","version":5}))
        await b.video_emit(Request({
            "type":"speed_down","browser":"firefox","pip":True,
        }))
        req=Request(cursor="0")
        req.query.pop("client",None)
        with patch.object(b.cond,"wait",new=AsyncMock()):
            result=await b.video_next(req)
        self.assertEqual(loads(result.text)["events"],[])

    async def test_pip_source_is_chosen_from_playing_media_only(self):
        b=self.bridge
        await b.video_heartbeat(Request({
            "id":"playing","visible":True,"has_video":True,
            "playing":True,"browser":"firefox","version":5}))
        await b.video_heartbeat(Request({
            "id":"not-playing","visible":True,"has_video":True,
            "playing":False,"browser":"firefox","version":5,
            "focused":True}))
        await b.video_emit(Request({
            "type":"speed_down","browser":"firefox","pip":True}))
        self.assertEqual(b.video_events[-1][1]["target"],"playing")

    async def test_ambiguous_multiple_playing_v5_videos_are_not_changed(self):
        from json import loads
        b=self.bridge
        for name in ("video-1","video-2"):
            await b.video_heartbeat(Request({
                "id":name,"visible":True,"has_video":True,
                "playing":True,"browser":"firefox","version":5}))
        response=await b.video_emit(Request({
            "type":"speed_up","browser":"firefox","pip":True}))
        self.assertEqual(response.status,409)
        self.assertEqual(
            loads(response.text)["reason"],
            "ambiguous-multiple-playing-firefox-videos")
        self.assertEqual(b.video_seq,0)

    async def test_video_event_is_never_cross_site(self):
        b=self.bridge
        await b.video_heartbeat(Request({
            "id":"playing-v5","visible":True,"has_video":True,
            "playing":True,"browser":"firefox","version":5}))
        response=await b.video_emit(Request(
            {"type":"speed_up","browser":"firefox","pip":True},
            headers={"Origin":"https://malicious.example"}))
        self.assertEqual(response.status,403)
        self.assertEqual(b.video_seq,0)

    async def test_cursor_recovers_after_backend_restart(self):
        from json import loads
        b=self.bridge
        b.video_seq=0
        result=await b.video_next(Request(cursor="500"))
        self.assertEqual(loads(result.text),{'cursor':0,'events':[]})
        result=await b.video_next(Request(cursor="-1"))
        self.assertEqual(loads(result.text),{'cursor':0,'events':[]})

    async def test_voice_queue_still_operates_after_speed_bridge_disabled(self):
        b=self.bridge
        await b.emit("voice_start")
        self.assertEqual(b.seq,1)
        self.assertEqual(b.video_seq,0)
        self.assertEqual(len(b.events),1)
        self.assertEqual(len(b.video_events),0)

    async def test_active_video_requires_matching_browser(self):
        from json import loads
        b=self.bridge
        await b.video_heartbeat(Request({"id":"x","visible":True,"has_video":True,
                                         "focused":True,"browser":"chromium"}))
        chrome=loads((await b.video_active(Request(cursor="0"))).text)
        self.assertFalse(chrome["active"])
        req=Request()
        req.query["browser"]="chromium"
        self.assertTrue(loads((await b.video_active(req)).text)["active"])
        req.query["browser"]="firefox"
        self.assertFalse(loads((await b.video_active(req)).text)["active"])

    async def test_client_heartbeat_off_unsubscribes(self):
        b=self.bridge
        await b.video_heartbeat(Request({"id":"active","visible":True,"has_video":True,"focused":True}))
        self.assertEqual(len(b.active_video_clients()),1)
        await b.video_heartbeat(Request({"id":"active","visible":False,"has_video":True,"focused":False}))
        self.assertEqual(len(b.active_video_clients()),0)

if __name__ == '__main__':
    unittest.main()
