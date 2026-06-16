Option Explicit

Dim fso, shell, baseDir, py, years, pauseAtEnd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
py = "C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
years = "2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 2026"
pauseAtEnd = True
If WScript.Arguments.Count > 1 Then
  If LCase(Trim(WScript.Arguments(1))) = "nopause" Then
    pauseAtEnd = False
  End If
End If

If Not fso.FileExists(py) Then
  MsgBox "Python runtime was not found:" & vbCrLf & py, vbCritical, "Launcher"
  WScript.Quit 1
End If

Dim choice
If WScript.Arguments.Count > 0 Then
  choice = WScript.Arguments(0)
Else
  choice = InputBox(MenuText(), "Life Ethics Archive Launcher", "1")
End If

choice = LCase(Trim(choice))

Select Case choice
  Case "", "0", "q", "quit", "exit"
    WScript.Quit 0
  Case "1", "scan", "status"
    RunCmd "Status and classification", CmdStatus()
  Case "2", "download"
    RunCmd "Official download refresh", CmdDownload()
  Case "3", "gap", "missing"
    RunCmd "Missing exam report", CmdGap("reports/official_gap_plan_latest.csv")
  Case "4", "apply"
    If ConfirmWrite() Then
      RunCmd "Apply missing official files", CmdApply("reports/official_gap_plan_latest.csv", "reports/official_gap_apply_manifest_latest.json")
    End If
  Case "5", "full"
    If ConfirmWrite() Then
      RunCmd "Full refresh", CmdFull()
    End If
  Case "6", "reports"
    shell.Run "explorer.exe " & Q(baseDir & "\reports"), 1, False
  Case "7", "folder"
    shell.Run "explorer.exe " & Q(baseDir), 1, False
  Case Else
    MsgBox "Unknown option: " & choice, vbExclamation, "Launcher"
End Select

Function MenuText()
  MenuText = _
    "Choose a task:" & vbCrLf & vbCrLf & _
    "1. Status scan + classification" & vbCrLf & _
    "2. Refresh official downloads (2014-2026)" & vbCrLf & _
    "3. Make missing/redownload report" & vbCrLf & _
    "4. Apply missing official files to iCloud" & vbCrLf & _
    "5. Full refresh: scan, download, report, apply, rescan" & vbCrLf & _
    "6. Open reports folder" & vbCrLf & _
    "7. Open tool folder" & vbCrLf & _
    "0. Exit"
End Function

Function ConfirmWrite()
  ConfirmWrite = (MsgBox("This task may copy files into the iCloud source folder." & vbCrLf & _
                         "Existing files are not overwritten by the Python copy tool." & vbCrLf & _
                         "Continue?", vbQuestion + vbYesNo, "Confirm iCloud write") = vbYes)
End Function

Function Q(value)
  Q = Chr(34) & value & Chr(34)
End Function

Sub RunCmd(title, command)
  Dim full
  If pauseAtEnd Then
    full = "cmd.exe /c " & Q("title " & title & " && cd /d " & Q(baseDir) & " && " & command & " && echo. && echo Done. && pause")
  Else
    full = "cmd.exe /c " & Q("title " & title & " && cd /d " & Q(baseDir) & " && " & command)
  End If
  shell.Run full, 1, True
End Sub

Function CmdStatus()
  CmdStatus = Q(py) & " exam_archive_manager.py --hash"
End Function

Function CmdDownload()
  CmdDownload = Q(py) & " official_exam_sources.py --academic-years " & years & _
    " --out reports/official_exam_sources_2014_2026_verified.csv" & _
    " --download-dir official_downloads_2014_2026_verified" & _
    " --manifest reports/official_download_manifest_2014_2026_verified.json --download"
End Function

Function CmdGap(outPath)
  CmdGap = Q(py) & " official_gap_plan.py --out " & outPath
End Function

Function CmdApply(gapPath, manifestPath)
  CmdApply = Q(py) & " apply_official_gap_plan.py --gap-plan " & gapPath & " --manifest " & manifestPath & " --apply"
End Function

Function CmdFull()
  CmdFull = CmdStatus() & " && " & _
    CmdDownload() & " && " & _
    CmdGap("reports/official_gap_plan_latest.csv") & " && " & _
    CmdApply("reports/official_gap_plan_latest.csv", "reports/official_gap_apply_manifest_latest.json") & " && " & _
    CmdStatus() & " && " & _
    CmdGap("reports/official_gap_plan_latest_after_apply.csv")
End Function
