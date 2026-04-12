@echo off
setlocal enableextensions

set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."
set "RUNNER=%SCRIPT_DIR%ann_ingredients_full_backfill.py"

if not exist "%RUNNER%" (
  echo [ann_ingredients_full_backfill.cmd] Missing runner: "%RUNNER%"
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
  exit /b %RC%
)

echo [ann_ingredients_full_backfill.cmd] Completed successfully.
exit /b 0
