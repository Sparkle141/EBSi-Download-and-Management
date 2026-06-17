Option Explicit

Dim shell, fso, rootDir, pythonExe, runnerPath, configPath, command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

rootDir = fso.GetParentFolderName(WScript.ScriptFullName)
runnerPath = fso.BuildPath(fso.BuildPath(rootDir, "system"), "pipeline_runner.py")
configPath = fso.BuildPath(rootDir, "pipeline_config.json")

If Not fso.FileExists(runnerPath) Then
    shell.Popup "system\pipeline_runner.py was not found.", 7, "Exam Reassembler", 48
    WScript.Quit 1
End If

pythonExe = ResolvePython(rootDir)
If pythonExe = "" Then
    shell.Popup "Python 3.10 or later was not found.", 7, "Exam Reassembler", 48
    WScript.Quit 1
End If

command = Quote(pythonExe) & " " & Quote(runnerPath) & " --config " & Quote(configPath)
shell.Run command, 0, False

WScript.Quit 0

Function ResolvePython(baseDir)
    Dim candidates, i, candidate
    candidates = Array( _
        fso.BuildPath(baseDir, "python\python.exe"), _
        fso.BuildPath(baseDir, ".venv\Scripts\python.exe"), _
        "C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" _
    )

    For i = 0 To UBound(candidates)
        candidate = candidates(i)
        If fso.FileExists(candidate) Then
            ResolvePython = candidate
            Exit Function
        End If
    Next

    If CommandExists("python") Then
        ResolvePython = "python"
    Else
        ResolvePython = ""
    End If
End Function

Function CommandExists(commandName)
    CommandExists = (shell.Run("cmd /c where " & commandName & " >nul 2>nul", 0, True) = 0)
End Function

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function
