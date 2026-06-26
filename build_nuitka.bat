@echo off
setlocal

set PYTHON_EXE=%PYTHON%
if "%PYTHON_EXE%"=="" set PYTHON_EXE=python

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_nuitka.ps1"
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo Build finished successfully.
exit /b 0
