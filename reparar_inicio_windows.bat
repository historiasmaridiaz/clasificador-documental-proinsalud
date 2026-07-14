@echo off
setlocal EnableExtensions
chcp 65001 >nul
title PROINSALUD TRD - Reparar inicio

if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "APP_HOME=%LOCALAPPDATA%\PROINSALUD_TRD"
set "VENV_DIR=%APP_HOME%\venv"

echo ============================================================
echo   REPARACION DEL ENTORNO PROINSALUD
ECHO ============================================================
echo Esta accion elimina solamente el entorno de Python instalado.
echo No elimina documentos, catalogos ni archivos del aplicativo.
echo.

if exist "%VENV_DIR%" (
    echo Eliminando entorno incompleto...
    rmdir /s /q "%VENV_DIR%"
)

del /q "%APP_HOME%\dependencias_v2.ok" >nul 2>&1

echo Entorno limpiado. Se iniciara una instalacion nueva.
echo.
call "%~dp0iniciar_windows.bat"
endlocal
