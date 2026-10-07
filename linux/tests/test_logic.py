from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "remote_hid_filter.py"
SPEC = importlib.util.spec_from_file_location("remote_hid_filter", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_wpp_class_is_presentation():
    props = 'WM_CLASS(STRING) = "wpp", "wpp"'
    assert module.is_wps_presentation_window(props)


def test_wpsoffice_ppt_title_is_presentation():
    props = (
        'WM_CLASS(STRING) = "wpsoffice", "wpsoffice"\n'
        '_NET_WM_NAME(UTF8_STRING) = "deck.pptx - WPS Office"'
    )
    assert module.is_wps_presentation_window(props)


def test_wpsoffice_with_wpp_child_is_presentation():
    props = 'WM_CLASS(STRING) = "wpsoffice", "wpsoffice"'
    tree = '0x123 "deck": ("wpp" "wpp") 1280x720+0+0'
    assert module.is_wps_presentation_window(props, tree)


def test_non_wps_window_is_not_presentation():
    props = (
        'WM_CLASS(STRING) = "google-chrome", "Google-chrome"\n'
        '_NET_WM_NAME(UTF8_STRING) = "ChatGPT"'
    )
    assert not module.is_wps_presentation_window(props)
