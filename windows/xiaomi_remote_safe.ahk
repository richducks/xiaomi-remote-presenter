#Requires AutoHotkey v2.0
#SingleInstance Force
Persistent

; SAFE default. Only the Xiaomi 2717:32B8 keyboard interface is intercepted.
; Non-video Enter, Back, and all presentation keys stay native.
#Include Lib\AutoHotInterception.ahk

VID := 0x2717
PID := 0x32B8
global AHI := AutoHotInterception()
global KeyboardId := AHI.GetKeyboardId(VID, PID, 1)
if !KeyboardId {
    MsgBox("Xiaomi Remote 2 Pro keyboard HID not found. Connect via Bluetooth and check AutoHotInterception Monitor.ahk.", "Xiaomi Remote Safe")
    ExitApp()
}
global RemoteContext := AHI.CreateContextManager(KeyboardId)

IsBrowser() {
    for exe in [
        "firefox.exe", "chrome.exe", "msedge.exe", "brave.exe",
        "opera.exe", "opera_gx.exe", "vivaldi.exe",
        "librewolf.exe", "waterfox.exe", "zen.exe"
    ] {
        if WinActive("ahk_exe " exe)
            return true
    }
    return false
}

IsVideoPage() {
    if !IsBrowser()
        return false
    ; Window-title recognition is a heuristic, NOT real playback detection.
    ; It keeps ChatGPT and unrelated browser Enter untouched.
    title := WinGetTitle("A")
    return RegExMatch(title, "i)(YouTube|Bilibili|哔哩哔哩|抖音|Douyin|"
                       . "夸克网盘|Quark|Netflix|Vimeo|Twitch|腾讯视频)")
}

SendOnce(keyName, shortcut) {
    Send(shortcut)
    KeyWait(keyName)
}

#HotIf RemoteContext.IsActive && IsBrowser()
Home::SendOnce("Home", "^t")
Browser_Home::SendOnce("Browser_Home", "^t")
SC029::SendOnce("SC029", "^w")
AppsKey::SendOnce("AppsKey", "^{Tab}")
#HotIf

#HotIf RemoteContext.IsActive && IsVideoPage()
; F13 requires browser/xiaomi-remote-video.user.js to toggle HTML5 video.
; A/D require the Global Speed extension's page shortcuts.
Enter::SendOnce("Enter", "{F13}")
Up::SendOnce("Up", "d")
Down::SendOnce("Down", "a")
#HotIf
