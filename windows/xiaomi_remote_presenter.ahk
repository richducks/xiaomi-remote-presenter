#Requires AutoHotkey v2.0
#SingleInstance Force
Persistent

; Only keys from the Xiaomi 2717:32B8 keyboard interface are remapped.
; Keep a spare keyboard when first installing the Interception driver.
#Include Lib\AutoHotInterception.ahk

VID := 0x2717
PID := 0x32B8
global AHI := AutoHotInterception()
global KeyboardId := AHI.GetKeyboardId(VID, PID, 1)

if !KeyboardId {
    MsgBox(
        "Xiaomi Remote 2 Pro was not found." Chr(10) Chr(10)
        . "Connect the remote and use AutoHotInterception Monitor.ahk "
        . "to confirm VID/PID and the actual key codes.",
        "Xiaomi Remote Presenter"
    )
    ExitApp()
}

global RemoteContext := AHI.CreateContextManager(KeyboardId)

IsPresentationEditor() {
    return WinActive("ahk_exe POWERPNT.EXE")
        || WinActive("ahk_exe wpp.exe")
        || WinActive("ahk_exe soffice.bin")
        || WinActive("ahk_exe soffice.exe")
}

IsBrowser() {
    ; Only standalone browser processes. Do not use window title alone:
    ; a terminal or WPS document can mention "Firefox" in its title.
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
    ; Safe default: UP/DOWN mappings are limited to recognizable video
    ; site titles, never on every browser page. This is a heuristic,
    ; not proof that a video is playing.
    title := WinGetTitle("A")
    return RegExMatch(title, "i)(YouTube|Bilibili|哔哩哔哩|抖音|Douyin|"
                       . "夸克网盘|Quark|Netflix|Vimeo|Twitch|腾讯视频)")
}

; One action per physical press: ignore auto-repeat until physical release.
; Keys are intercepted from the Xiaomi keyboard only (AHI context).
SendOnce(keyName, shortcut) {
    Send(shortcut)
    KeyWait(keyName)
}

#HotIf RemoteContext.IsActive
F5::Return  ; Physical F5 must not accidentally refresh a browser.
#HotIf

#HotIf RemoteContext.IsActive && IsPresentationEditor()
Enter::SendOnce("Enter", "{F5}")
Browser_Back::SendOnce("Browser_Back", "{Esc}")
#HotIf

#HotIf RemoteContext.IsActive && IsBrowser()
; Note: macOS equivalent is Command, not Control.
; Remote house -> new browser tab; TV -> close tab.
Home::SendOnce("Home", "^t")
Browser_Home::SendOnce("Browser_Home", "^t")
SC029::SendOnce("SC029", "^w")       ; TV is HID 0x35 / grave
AppsKey::SendOnce("AppsKey", "^{Tab}") ; three lines / Application
Browser_Back::SendOnce("Browser_Back", "!{Left}") ; previous history entry

; Browser OK -> F13. Install browser/xiaomi-remote-video.user.js to
; toggle the foreground HTML5 video (YouTube, Quark, Douyin, etc.).
; Unlike a blind "k", this does not type into YouTube's search box.
Enter::SendOnce("Enter", "{F13}")
#HotIf

#HotIf RemoteContext.IsActive && IsVideoPage()
; Global Speed MUST be installed and configured for D (+.1) / A (-.1).
; No second playback-rate engine. Volume buttons stay native.
Up::SendOnce("Up", "d")
Down::SendOnce("Down", "a")
#HotIf
