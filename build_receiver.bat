@echo off
setlocal

cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo.
    echo Installation fehlgeschlagen. Bitte Python installieren und zum PATH hinzufuegen.
    pause
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --onefile --windowed --name WakeupReceiver receiver.py
if errorlevel 1 (
    echo.
    echo Der Build von WakeupReceiver.exe ist fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo Fertig: dist\WakeupReceiver.exe
pause
