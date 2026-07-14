@echo off
setlocal EnableExtensions
chcp 65001 >nul
title PROINSALUD - Instalar OCR local

echo ============================================================
echo   INSTALADOR DE OCR LOCAL - PROINSALUD
ECHO ============================================================
echo.

where tesseract >nul 2>&1
if not errorlevel 1 goto :found

if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" goto :found_programfiles
if exist "%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe" goto :found_local

where winget >nul 2>&1
if errorlevel 1 (
    echo No se encontro Tesseract ni el administrador winget.
    echo Instale Tesseract OCR para Windows y active el idioma espanol.
    echo Luego vuelva a ejecutar este archivo.
    goto :end_error
)

echo Se instalara Tesseract OCR mediante Windows Package Manager.
echo Windows puede solicitar autorizacion.
echo.
winget install --exact --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo No fue posible completar la instalacion automatica.
    echo Busque "Tesseract OCR UB Mannheim" e instalelo manualmente.
    goto :end_error
)

if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" goto :found_programfiles
if exist "%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe" goto :found_local
where tesseract >nul 2>&1
if not errorlevel 1 goto :found

echo La instalacion termino, pero Tesseract no fue detectado todavia.
echo Reinicie Windows o cierre y abra nuevamente el aplicativo.
goto :end_ok

:found_programfiles
set "TESSERACT_CMD=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
goto :verify

:found_local
set "TESSERACT_CMD=%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe"
goto :verify

:found
for /f "delims=" %%I in ('where tesseract 2^>nul') do if not defined TESSERACT_CMD set "TESSERACT_CMD=%%I"

:verify
echo OCR encontrado en:
echo   %TESSERACT_CMD%
echo.
"%TESSERACT_CMD%" --version | findstr /b /c:"tesseract"
echo.
echo Idiomas detectados:
"%TESSERACT_CMD%" --list-langs 2>nul

echo.
echo OCR local listo. Cierre esta ventana e inicie el aplicativo.

:end_ok
pause
exit /b 0

:end_error
pause
exit /b 1
