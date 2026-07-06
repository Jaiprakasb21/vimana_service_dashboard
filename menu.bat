@echo off
setlocal
cd /d "%~dp0"

:menu
cls
echo ==========================================
echo ESIGN_SERVICE Dashboard Menu
echo ==========================================
echo 1. Do setup
echo 2. Start server
echo 3. Stop server
echo 4. Exit
echo.
set /p choice=Select an option: 

if "%choice%"=="1" powershell -ExecutionPolicy Bypass -File "%~dp0manage.ps1" setup & goto done
if "%choice%"=="2" powershell -ExecutionPolicy Bypass -File "%~dp0manage.ps1" start & goto done
if "%choice%"=="3" powershell -ExecutionPolicy Bypass -File "%~dp0manage.ps1" stop & goto done
if "%choice%"=="4" exit /b 0

echo Invalid option.
pause
goto menu

:done
echo.
pause
goto menu
