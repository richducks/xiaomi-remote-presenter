#Requires AutoHotkey v2.0
#SingleInstance Force
Persistent

#Include Lib\AutoHotInterception.ahk

VID := 0x2717
PID := 0x32B8

global AHI := AutoHotInterception()
global KeyboardId := AHI.GetKeyboardId(VID, PID, 1)

if !KeyboardId {
    MsgBox(
        "Xiaomi Remote 2 Pro was not found.`n`n"
        . "Pair/connect the remote, then run Monitor.ahk from AutoHotInterception "
        . "to confirm the device VID/PID.",
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

#HotIf RemoteContext.IsActive
F5::Return
#HotIf

#HotIf RemoteContext.IsActive && IsPresentationEditor()
Enter::Send("{F5}")
Browser_Back::Send("{Esc}")
#HotIf
