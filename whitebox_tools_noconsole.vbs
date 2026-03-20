Set WshShell = CreateObject("WScript.Shell")

' Build the command string exactly as WhiteboxTools expects it
args = ""
For i = 0 To WScript.Arguments.Count - 1
    args = args & " " & Chr(34) & WScript.Arguments(i) & Chr(34)
Next

' Path to real whitebox_tools.exe (OSGeo4W)
cmd = Chr(34) & "C:\OSGeo4W\bin\whitebox_tools.exe" & Chr(34) & args

' Run with window hidden (0 = hidden, True = don't wait)
WshShell.Run cmd, 0, True