'  ===========================================================================
'   DSH Balance Pet launcher v5 (force-restart on every double-click).
'   Double-click behavior (v5):
'     - ALWAYS force a clean cold start (kill old pet + old bridge, then
'       relaunch). This guarantees the latest patched sprite.js / bridge
'       code is loaded every time — no more "双击了但没变".
'   v4 fixes the v3 killer bug: cmd /c strips leading/trailing quotes, which
'   shredded the quoted node path -> node never started. Paths here contain
'   no spaces, so NO quotes at all around the cmd line.
'   Health checks use WinHttp DIRECT (SetProxy 1). Trace -> launcher.log.
'  ===========================================================================
Option Explicit

Dim shell, fso, here, profile, nodeExe, entryJs, pyw, bridgePy, i, q, nodeLog, cmdline

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
profile = shell.ExpandEnvironmentStrings("%USERPROFILE%")
q = Chr(34)

nodeExe = profile & "\.workbuddy\binaries\node\versions\22.22.2-6\node.exe"
entryJs = profile & "\.workbuddy\binaries\node\versions\22.22.2-6\node_modules\dsh-pet\lib\standalone.js"
pyw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe"
bridgePy = here & "\balance_bridge.py"
nodeLog = here & "\node.log"

If Not fso.FileExists(nodeExe) Or Not fso.FileExists(entryJs) Then
    MsgBox "dsh-pet standalone not found (run: npm i -g dsh-pet).", 16, "DSH Balance Pet"
    WScript.Quit 1
End If
If Not fso.FileExists(pyw) Or Not fso.FileExists(bridgePy) Then
    MsgBox "bridge files missing next to this launcher.", 16, "DSH Balance Pet"
    WScript.Quit 1
End If

Sub Trace(msg)
    Dim f
    On Error Resume Next
    Set f = fso.OpenTextFile(here & "\launcher.log", 8, True)
    f.WriteLine "[" & Year(Now) & "-" & Right("0" & Month(Now), 2) & "-" & Right("0" & Day(Now), 2) & _
                " " & FormatDateTime(Now, 3) & "] " & msg
    f.Close
End Sub

' --- always force a clean restart so the latest patched code loads ---
If HealthOK() Then
    Trace "host alive on start; forcing full restart for fresh code"
    ShutdownHost
    For i = 1 To 30
        If Not HealthOK() Then Exit For
        WScript.Sleep 1000
    Next
    KillBridge
    WScript.Sleep 1000
    Trace "old stack stopped; cold-starting fresh"
End If

Trace "cold start: launching node via cmd /c (unquoted, output -> node.log)"

' --- cold start: node with output captured to node.log ---
' paths contain no spaces -> cmd line must stay UNQUOTED (cmd /c strips
' leading/trailing quotes of a quoted first token and shreds the command)
cmdline = "cmd /c " & nodeExe & " " & entryJs & " > " & nodeLog & " 2>&1"
shell.Run cmdline, 0, False

' wait silently up to 5 minutes; NEVER popup - node.log has clues if it fails
For i = 1 To 300
    If HealthOK() Then Exit For
    WScript.Sleep 1000
Next
If Not HealthOK() Then
    Trace "host NOT healthy after 300s - giving up silently (see node.log)"
    WScript.Quit 1
End If

Trace "host healthy after " & i & "s; starting bridge"
shell.Run q & pyw & q & " " & q & bridgePy & q, 0, False
Trace "bridge launched; done"
WScript.Quit 0


Function HealthOK()
    On Error Resume Next
    HealthOK = False
    Dim x
    Set x = CreateObject("WinHttp.WinHttpRequest.5.1")
    x.SetProxy 1                      ' 1 = DIRECT, ignore system proxy
    x.SetTimeouts 2000, 2000, 2000, 2000
    x.Open "GET", "http://127.0.0.1:3080/health", False
    x.Send
    If Err.Number <> 0 Then Err.Clear : Exit Function
    HealthOK = (x.Status = 200)
End Function

Function ChatOK()
    On Error Resume Next
    ChatOK = False
    Dim x
    Set x = CreateObject("WinHttp.WinHttpRequest.5.1")
    x.SetProxy 1
    x.SetTimeouts 2000, 2000, 2000, 2000
    x.Open "GET", "http://127.0.0.1:30802/", False
    x.Send
    If Err.Number <> 0 Then Err.Clear : Exit Function
    ChatOK = (x.Status = 200)
End Function

Sub ShutdownHost()
    On Error Resume Next
    Dim x
    Set x = CreateObject("WinHttp.WinHttpRequest.5.1")
    x.SetProxy 1
    x.SetTimeouts 2000, 2000, 2000, 2000
    x.Open "POST", "http://127.0.0.1:3080/shutdown", False
    x.Send
End Sub

Sub KillBridge()
    On Error Resume Next
    Dim f, pid, ws, pf
    pf = here & "\pet_bridge.pid"
    If Not fso.FileExists(pf) Then Exit Sub
    Set f = fso.OpenTextFile(pf, 1)
    pid = f.ReadLine
    f.Close
    If pid <> "" Then
        Set ws = CreateObject("WScript.Shell")
        ws.Run "taskkill /F /PID " & pid, 0, True
    End If
End Sub
