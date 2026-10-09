#!/usr/bin/env python3
"""Generate Karabiner rules from a small, reviewable device/app policy.

Run from the repository root: python3 macos/build_rules.py
The checked-in JSON is used by macos/install.sh without requiring Python.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEVICE = [{"vendor_id": 0x2717, "product_id": 0x32B8}]
BROWSERS = [
    r"^com\.apple\.Safari$",
    r"^org\.mozilla\.firefox$",
    r"^org\.mozilla\.firefoxdeveloperedition$",
    r"^org\.mozilla\.nightly$",
    r"^com\.google\.Chrome(?:\.beta|\.dev|\.canary)?$",
    r"^com\.microsoft\.edgemac(?:\.Beta|\.Dev|\.Canary)?$",
    r"^com\.brave\.Browser(?:\.beta|\.nightly)?$",
    r"^com\.operasoftware\.Opera(?:Next)?$",
    r"^com\.vivaldi\.Vivaldi$",
    r"^org\.chromium\.Chromium$",
    r"^org\.torproject\.TorBrowser$",
    r"^org\.mozilla\.librewolf$",
]
WPS = [r"^com\.kingsoft\.wpsoffice\.mac\.global$"]
POWERPOINT = [r"^com\.microsoft\.(Powerpoint|PowerPoint|powerpoint)$"]
KEYNOTE = [r"^com\.apple\.iWork\.Keynote$"]
PRESENTATIONS = WPS + POWERPOINT + KEYNOTE


def input_key(key: str, *, consumer: bool = False) -> dict:
    result = {"consumer_key_code" if consumer else "key_code": key}
    if not consumer:
        result["modifiers"] = {"optional": ["any"]}
    return result


def output_key(key: str, mods: list[str] | None = None) -> list[dict]:
    result: dict = {"key_code": key, "repeat": False}
    if mods:
        result["modifiers"] = mods
    return [result]


def manipulate(src: dict, target: list[dict] | None, app: list[str] | None = None) -> dict:
    conditions = [{"type": "device_if", "identifiers": DEVICE}]
    if app:
        conditions.append({"type": "frontmost_application_if", "bundle_identifiers": app})
    result = {"type": "basic", "from": src, "conditions": conditions}
    if target is not None:
        result["to"] = target
    return result


def rule(description: str, src: list[dict], target: list[dict] | None, apps: list[str]) -> dict:
    return {"description": description, "manipulators": [
        manipulate(key, target, apps) for key in src
    ]}


def build_core() -> dict:
    return {"title": "Xiaomi Remote 2 Pro · 浏览器 / 演示 (设备专属)", "rules": [
        rule("WPS: OK 开始演示", [input_key("return_or_enter")],
             output_key("f5"), WPS),
        rule("PowerPoint: OK 从头放映", [input_key("return_or_enter")],
             output_key("return_or_enter", ["left_command", "left_shift"]), POWERPOINT),
        rule("Keynote: OK 开始演示", [input_key("return_or_enter")],
             output_key("p", ["left_command", "left_option"]), KEYNOTE),
        rule("演示软件: 返回键退出放映", [input_key("ac_back", consumer=True)],
             output_key("escape"), PRESENTATIONS),
        rule("浏览器: 小房子新建标签页 Cmd+T",
             [input_key("home"), input_key("ac_home", consumer=True)],
             output_key("t", ["left_command"]), BROWSERS),
        rule("浏览器: TV 关闭标签页 Cmd+W",
             [input_key("grave_accent_and_tilde")],
             output_key("w", ["left_command"]), BROWSERS),
        rule("浏览器: 三横杠菜单切换标签 Control+Tab",
             [input_key("application")],
             output_key("tab", ["left_control"]), BROWSERS),
        rule("浏览器: 返回键访问上一页 Cmd+[",
             [input_key("ac_back", consumer=True)],
             output_key("open_bracket", ["left_command"]), BROWSERS),
        rule("浏览器: OK -> F13，配合通用视频用户脚本播放/暂停",
             [input_key("return_or_enter")],
             output_key("f13"), BROWSERS),
        {"description": "阻止小米遥控器原始 F5 误刷新",
         "manipulators": [manipulate(input_key("f5"), None)]},
    ]}


def build_safe() -> dict:
    """Safe default: browser tab actions only; no Enter, Back, WPS or F5."""
    return {"title": "Xiaomi Remote 2 Pro SAFE · 浏览器标签页（默认）", "rules": [
        rule("Xiaomi Remote 2 Pro SAFE · 小房子新建标签页 Cmd+T",
             [input_key("home"), input_key("ac_home", consumer=True)],
             output_key("t", ["left_command"]), BROWSERS),
        rule("Xiaomi Remote 2 Pro SAFE · TV 关闭标签页 Cmd+W",
             [input_key("grave_accent_and_tilde")],
             output_key("w", ["left_command"]), BROWSERS),
        rule("Xiaomi Remote 2 Pro SAFE · 菜单切换标签 Control+Tab",
             [input_key("application")],
             output_key("tab", ["left_control"]), BROWSERS),
    ]}


def build_optional_video_ok() -> dict:
    """Optional: Karabiner cannot detect an active HTML5 video frame.

    Enabling this rule intercepts the remote's Enter in ALL browser tabs.
    The userscript only plays/pauses active video, but regular remote Enter
    no longer reaches browser input fields. Never enable automatically.
    """
    return {"title": "Xiaomi Remote 2 Pro · 视频 OK（可选，浏览器占用 Enter）",
            "rules": [
                rule("视频播放（可选）: OK -> F13，仅在浏览器",
                     [input_key("return_or_enter")],
                     output_key("f13"), BROWSERS),
            ]}


def build_optional_speed() -> dict:
    return {"title": "Xiaomi 2 Pro · Global Speed 视频模式（可选，浏览器占用方向键）",
            "rules": [
                rule("视频模式（可选）: 上键 -> Global Speed D (+0.1x)",
                     [input_key("up_arrow")], output_key("d"), BROWSERS),
                rule("视频模式（可选）: 下键 -> Global Speed A (-0.1x)",
                     [input_key("down_arrow")], output_key("a"), BROWSERS),
            ]}


def main() -> None:
    for filename, content in [
        ("xiaomi-remote-presenter.json", build_core()),
        ("xiaomi-remote-safe.json", build_safe()),
        ("xiaomi-remote-video-ok.json", build_optional_video_ok()),
        ("xiaomi-remote-video-speed.json", build_optional_speed()),
    ]:
        out = ROOT / filename
        out.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(out)


if __name__ == "__main__":
    main()
