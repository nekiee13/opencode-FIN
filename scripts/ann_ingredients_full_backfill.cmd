@echo off
setlocal enableextensions

set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."
set "RUNNER=%SCRIPT_DIR%ann_ingredients_full_backfill.py"

for /f %%I in ('powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"') do set "START_EPOCH=%%I"

if not exist "%RUNNER%" (
  echo [ann_ingredients_full_backfill.cmd] Missing runner: "%RUNNER%"
  call :print_elapsed
  exit /b 2
)

echo [ann_ingredients_full_backfill.cmd] Repo: "%REPO_ROOT%"
echo [ann_ingredients_full_backfill.cmd] Runner: "%RUNNER%"

pushd "%REPO_ROOT%" >nul
python "%RUNNER%" %*
set "RC=%ERRORLEVEL%"
popd >nul

if not "%RC%"=="0" (
  echo [ann_ingredients_full_backfill.cmd] Failed with exit code %RC%
  call :print_elapsed
  exit /b %RC%
)

echo [ann_ingredients_full_backfill.cmd] Completed successfully.
call :print_elapsed
exit /b 0

:print_elapsed
for /f %%I in ('powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"') do set "END_EPOCH=%%I"
set /a ELAPSED_SECONDS=END_EPOCH-START_EPOCH
if %ELAPSED_SECONDS% LSS 0 set /a ELAPSED_SECONDS+=86400
set /a ELAPSED_HH=ELAPSED_SECONDS/3600
set /a ELAPSED_MM=(ELAPSED_SECONDS %% 3600)/60
set /a ELAPSED_SS=ELAPSED_SECONDS %% 60
echo [ann_ingredients_full_backfill.cmd] Elapsed: %ELAPSED_HH%h %ELAPSED_MM%m %ELAPSED_SS%s
goto :eof
