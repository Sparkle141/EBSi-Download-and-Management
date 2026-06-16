Option Explicit

Dim fso, shell, baseDir, pythonw, python, script
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = "C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
python = "C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
script = baseDir & "\kice_archive_gui.py"

If Not fso.FileExists(script) Then
  MsgBox "GUI script was not found:" & vbCrLf & script, vbCritical, "KICE Archive UI"
  WScript.Quit 1
End If

If fso.FileExists(pythonw) Then
  shell.Run Quote(pythonw) & " " & Quote(script), 1, False
ElseIf fso.FileExists(python) Then
  shell.Run Quote(python) & " " & Quote(script), 1, False
Else
  MsgBox "Python runtime was not found.", vbCritical, "KICE Archive UI"
  WScript.Quit 1
End If

Function Quote(value)
  Quote = Chr(34) & value & Chr(34)
End Function
