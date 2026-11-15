@echo off
setlocal

cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Installation fehlgeschlagen. Bitte Python installieren und zum PATH hinzufuegen.
    pause
    exit /b 1
)

echo.
echo Abhaengigkeiten wurden erfolgreich installiert.
pause
