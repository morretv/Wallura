@echo off
cd /d "%~dp0"
echo ==== Wallura-Installer bauen ====
echo.

where py >nul 2>nul
if errorlevel 1 goto nopython

call :findiscc
if defined ISCC goto build
echo Installiere Inno Setup ...
winget install -e --id JRSoftware.InnoSetup --silent --accept-source-agreements --accept-package-agreements
call :findiscc
if defined ISCC goto build
echo.
echo Inno Setup wurde nicht gefunden. Bitte manuell installieren: https://jrsoftware.org/isdl.php
pause
exit /b 1

:build
echo [1/5] Python-Pakete installieren ...
py -m pip install --upgrade pip
py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail

echo [2/5] Icon erstellen ...
py make_icon.py
if errorlevel 1 goto fail

echo [3/5] Tools (mpv, yt-dlp) laden ...
py fetch_tools.py
if errorlevel 1 goto fail

echo [4/5] Wallura.exe bauen ...
py -m PyInstaller --noconfirm --clean --onedir --windowed --name Wallura --icon wallura.ico --collect-all customtkinter --hidden-import pystray._win32 wallura.py
if errorlevel 1 goto fail

echo [5/5] Installer erstellen ...
for /f "delims=" %%v in ('py get_version.py') do set "APPVER=%%v"
echo Version: %APPVER%
"%ISCC%" /DAppVer=%APPVER% Wallura.iss
if errorlevel 1 goto fail

echo.
echo ==== FERTIG ====
echo Dein Installer: %~dp0installer\Wallura-Setup.exe
explorer "%~dp0installer"
pause
exit /b 0

:nopython
echo Python fehlt - installiere es mit winget ...
winget install -e --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
echo.
echo Python wurde installiert. Bitte dieses Fenster schliessen und die Datei NOCH EINMAL starten.
pause
exit /b 0

:fail
echo.
echo Fehler beim Bauen - bitte die Meldungen oben ansehen.
pause
exit /b 1

:findiscc
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
exit /b
