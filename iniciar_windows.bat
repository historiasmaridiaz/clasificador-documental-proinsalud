@echo off
setlocal EnableExtensions
chcp 65001 >nul

title PROINSALUD TRD - Inicio seguro
set "PROJECT_DIR=%~dp0"
pushd "%PROJECT_DIR%"

rem ============================================================
rem El entorno virtual se guarda fuera del proyecto para evitar
rem el error WinError 206 (ruta o nombre de archivo demasiado largo).
rem ============================================================
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "APP_HOME=%LOCALAPPDATA%\PROINSALUD_TRD"
set "VENV_DIR=%APP_HOME%\venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "READY_MARKER=%APP_HOME%\dependencias_v2.ok"
set "PIP_CACHE_DIR=%APP_HOME%\pip-cache"
set "PYTHONUTF8=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"
set "OMP_NUM_THREADS=1"
set "OPENBLAS_NUM_THREADS=1"
set "MKL_NUM_THREADS=1"
set "NUMEXPR_NUM_THREADS=1"

rem Detecta Tesseract instalado fuera del PATH para habilitar OCR local.
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESSERACT_CMD=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if not defined TESSERACT_CMD if exist "%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe" set "TESSERACT_CMD=%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe"

if not exist "%APP_HOME%" mkdir "%APP_HOME%" >nul 2>&1

if not exist "%PROJECT_DIR%app.py" (
    echo.
    echo ERROR: No se encontro app.py en la carpeta del aplicativo.
    echo Vuelva a extraer completamente el archivo ZIP.
    goto :fatal
)

set "PY_LAUNCHER="
where py >nul 2>&1
if not errorlevel 1 set "PY_LAUNCHER=py"
if not defined PY_LAUNCHER (
    where python >nul 2>&1
    if not errorlevel 1 set "PY_LAUNCHER=python"
)

if not defined PY_LAUNCHER (
    echo.
    echo ERROR: Python no esta instalado o no esta agregado al PATH.
    echo Instale Python 3.11 o superior desde python.org.
    echo Durante la instalacion active: Add Python to PATH.
    goto :fatal
)

echo ============================================================
echo   CLASIFICADOR DOCUMENTAL PROINSALUD
ECHO ============================================================
echo Proyecto: "%PROJECT_DIR%"
echo Entorno corto: "%VENV_DIR%"
echo Version: 2026.07.13-TRD-INSTRUMENTS-SCOPE-9
echo.

if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if errorlevel 1 (
        echo El entorno anterior esta incompleto. Se reconstruira...
        rmdir /s /q "%VENV_DIR%" >nul 2>&1
        del /q "%READY_MARKER%" >nul 2>&1
    )
)

if not exist "%VENV_PY%" (
    echo [1/3] Creando entorno virtual en una ruta corta...
    "%PY_LAUNCHER%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo ERROR: No fue posible crear el entorno virtual.
        goto :fatal
    )
    del /q "%READY_MARKER%" >nul 2>&1
) else (
    echo [1/3] Entorno virtual encontrado.
)

if exist "%READY_MARKER%" (
    "%VENV_PY%" -c "import streamlit, pandas, openpyxl, sklearn, pypdf, fitz, docx, pptx, xlrd, rarfile, PIL, pytesseract, bs4, charset_normalizer, reportlab" >nul 2>&1
    if not errorlevel 1 goto :run_app
    del /q "%READY_MARKER%" >nul 2>&1
)

echo [2/3] Instalando dependencias. La primera vez puede tardar varios minutos...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :install_error

"%VENV_PY%" -m pip install -r "%PROJECT_DIR%requirements.txt"
if errorlevel 1 goto :install_error

"%VENV_PY%" -c "import streamlit, pandas, openpyxl, sklearn, pypdf, fitz, docx, pptx, xlrd, rarfile, PIL, pytesseract, bs4, charset_normalizer, reportlab"
if errorlevel 1 goto :install_error

> "%READY_MARKER%" echo Dependencias verificadas correctamente.

:run_app
echo [3/3] Iniciando la aplicacion...
echo.
if defined TESSERACT_CMD (
    echo OCR local detectado: "%TESSERACT_CMD%"
) else (
    echo AVISO: Tesseract OCR no fue detectado.
    echo Para clasificar PDF escaneados, cierre la aplicacion y ejecute:
    echo   instalar_ocr_windows.bat
)
echo.
echo Cuando aparezca la direccion, abra: http://localhost:8501
echo Para cerrar el aplicativo presione Ctrl+C en esta ventana.
echo.
"%VENV_PY%" -m streamlit run "%PROJECT_DIR%app.py"
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo La aplicacion se cerro con el codigo %APP_EXIT%.
    goto :fatal
)
goto :end

:install_error
echo.
echo ============================================================
echo ERROR AL INSTALAR LAS DEPENDENCIAS
ECHO ============================================================
echo El entorno corto ya evita el error WinError 206.
echo Si la instalacion fue interrumpida, ejecute:
echo   reparar_inicio_windows.bat
echo.
echo Revise tambien que exista conexion a Internet y espacio disponible.
goto :fatal

:fatal
echo.
echo No cierre esta ventana antes de leer el mensaje anterior.
pause
goto :end

:end
popd
endlocal
