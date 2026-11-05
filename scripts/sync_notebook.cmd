@echo off
REM ---------------------------------------------------------------------------
REM Notebook sync: pulls the new challenge, pushes the solution and updates
REM the ledger in Neon.
REM
REM This is the entry point of the Windows Task Scheduler task that runs
REM once a day, at 06:00. The output goes to logs\sync-task.log: no
REM console window pops up, and the history of the runs is always there.
REM
REM The project folder and the uv path below are specific to this machine.
REM Adjust them if the project moves.
REM ---------------------------------------------------------------------------

setlocal

set "PROJECT_DIR=C:\Dev\Projects\leetcode-analytics-automation"
set "UV_PATH=%LOCALAPPDATA%\Programs\Python\Python313\Scripts\uv.exe"

cd /d "%PROJECT_DIR%"

REM The redirection below needs the folder to exist before Python starts.
if not exist "logs" mkdir "logs"

if exist "%UV_PATH%" (
    "%UV_PATH%" run python scripts\sync.py >> "logs\sync-task.log" 2>&1
) else (
    uv run python scripts\sync.py >> "logs\sync-task.log" 2>&1
)

set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
