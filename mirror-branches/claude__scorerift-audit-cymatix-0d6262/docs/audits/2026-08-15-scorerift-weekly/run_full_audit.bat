@echo off
set "PATH=F:\Projects\cymatix-context\.venv\Scripts;C:\Users\max\AppData\Local\Python\pythoncore-3.14-64\Scripts;%PATH%"
set "SCORERIFT_PYTEST_TIMEOUT=5400"
set "SCORERIFT_PYTEST_MARKERS="
cd /d F:\tmp\cymatixscontext_SR_reports
"C:\Users\max\AppData\Local\Python\pythoncore-3.14-64\python.exe" run_full_audit.py > run_stdout.log 2> run_stderr.log
echo %ERRORLEVEL% > run_exitcode.txt
