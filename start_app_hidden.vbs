Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appFolder = fso.GetParentFolderName(WScript.ScriptFullName)
pythonPath = "C:\Users\nelko\AppData\Local\Programs\Python\Python313\python.exe"
cmd = "cmd /c cd /d """ & appFolder & """ && """ & pythonPath & """ -m streamlit run app.py --server.headless true"
shell.Run cmd, 0, False
WScript.Sleep 5000
shell.Run "http://localhost:8501", 1, False
