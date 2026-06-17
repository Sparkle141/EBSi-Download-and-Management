Option Explicit

Dim shell, fso, rootDir, pythonExe, runnerPath, configPath, command, checkedLocations

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

rootDir = fso.GetParentFolderName(WScript.ScriptFullName)
runnerPath = fso.BuildPath(fso.BuildPath(rootDir, "system"), "pipeline_runner.py")
configPath = fso.BuildPath(rootDir, "pipeline_config.json")
checkedLocations = ""

If Not fso.FileExists(runnerPath) Then
    shell.Popup "system\pipeline_runner.py was not found.", 7, "Exam Reassembler", 48
    WScript.Quit 1
End If

pythonExe = ResolvePythonRuntime(rootDir)
If pythonExe = "" Then
    shell.Popup "Python runtime was not found." & vbCrLf & vbCrLf & _
        "Checked locations:" & vbCrLf & checkedLocations & vbCrLf & _
        "Install Python or create .venv in this folder, then run this launcher again.", _
        12, "Exam Reassembler", 48
    WScript.Quit 1
End If

If shell.Environment("PROCESS")("EBSI_LAUNCHER_DRY_RUN") = "1" Then
    WScript.Echo pythonExe
    WScript.Quit 0
End If

command = Quote(pythonExe) & " " & Quote(runnerPath) & " --config " & Quote(configPath)
shell.CurrentDirectory = rootDir
shell.Run command, 0, False

WScript.Quit 0

Function ResolvePythonRuntime(baseDir)
    Dim env, candidates, candidate, found
    Set env = shell.Environment("PROCESS")

    candidates = Array( _
        fso.BuildPath(baseDir, "python\pythonw.exe"), _
        fso.BuildPath(baseDir, ".venv\Scripts\pythonw.exe"), _
        fso.BuildPath(baseDir, "python\python.exe"), _
        fso.BuildPath(baseDir, ".venv\Scripts\python.exe"), _
        env("LOCALAPPDATA") & "\Python\bin\pythonw.exe", _
        env("LOCALAPPDATA") & "\Python\bin\python.exe", _
        env("LOCALAPPDATA") & "\Programs\Python\Python314\pythonw.exe", _
        env("LOCALAPPDATA") & "\Programs\Python\Python314\python.exe", _
        env("LOCALAPPDATA") & "\Programs\Python\Python313\pythonw.exe", _
        env("LOCALAPPDATA") & "\Programs\Python\Python313\python.exe", _
        env("LOCALAPPDATA") & "\Programs\Python\Python312\pythonw.exe", _
        env("LOCALAPPDATA") & "\Programs\Python\Python312\python.exe", _
        env("PROGRAMFILES") & "\Python314\pythonw.exe", _
        env("PROGRAMFILES") & "\Python314\python.exe", _
        env("PROGRAMFILES") & "\Python313\pythonw.exe", _
        env("PROGRAMFILES") & "\Python313\python.exe", _
        env("PROGRAMFILES") & "\Python312\pythonw.exe", _
        env("PROGRAMFILES") & "\Python312\python.exe", _
        env("USERPROFILE") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe", _
        env("USERPROFILE") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" _
    )

    For Each candidate In candidates
        found = ExistingFile(candidate)
        If found <> "" Then
            ResolvePythonRuntime = found
            Exit Function
        End If
    Next

    found = FindOnPath("pythonw.exe")
    If found <> "" Then
        ResolvePythonRuntime = found
        Exit Function
    End If

    ResolvePythonRuntime = FindOnPath("python.exe")
End Function

Function ExistingFile(path)
    If path <> "" Then
        checkedLocations = checkedLocations & "- " & path & vbCrLf
        If fso.FileExists(path) Then
            ExistingFile = path
            Exit Function
        End If
    End If
    ExistingFile = ""
End Function

Function FindOnPath(exeName)
    Dim exec, line
    checkedLocations = checkedLocations & "- PATH: " & exeName & vbCrLf
    On Error Resume Next
    Set exec = shell.Exec("%ComSpec% /c where " & exeName & " 2>nul")
    If Err.Number <> 0 Then
        Err.Clear
        FindOnPath = ""
        Exit Function
    End If
    On Error GoTo 0
    If Not exec.StdOut.AtEndOfStream Then
        line = Trim(exec.StdOut.ReadLine)
        If fso.FileExists(line) Then
            FindOnPath = line
            Exit Function
        End If
    End If
    FindOnPath = ""
End Function

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function
