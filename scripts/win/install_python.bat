@echo off
REM SPRi Newsletter - Python auto-install script
REM Called by setup_local.bat. Downloads and installs Python if not found.
chcp 65001 >nul

setlocal

set PYTHON_VERSION=3.11.9
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe
set INSTALLER=%TEMP%\python-%PYTHON_VERSION%-amd64.exe

REM -- 1. Check if Python is already installed --
python --version >nul 2>&1
if not errorlevel 1 (
    echo [Python] Already installed:
    python --version
    goto :done
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
    echo [Python] Available via py launcher:
    py -3 --version
    goto :done
)

REM -- 2. Python not found --
echo(
echo ============================================================
echo  Python %PYTHON_VERSION% Auto Install
echo ============================================================
echo(
echo  Python is not installed.
echo  Downloading from python.org ...
echo(

REM -- 3. Download --
echo [1/3] Downloading Python %PYTHON_VERSION% ...
echo       URL: %PYTHON_URL%
echo(

curl -L -o "%INSTALLER%" "%PYTHON_URL%" --progress-bar --ssl-no-revoke
if errorlevel 1 goto :download_failed

REM Check file size (too small = proxy login page)
for %%F in ("%INSTALLER%") do set FILESIZE=%%~zF
if not defined FILESIZE goto :download_failed
if %FILESIZE% LSS 1000000 goto :size_error

REM -- 4. Silent Install --
echo [2/3] Installing Python %PYTHON_VERSION% ... (1-2 min)
echo(

"%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
if errorlevel 1 goto :install_failed

REM -- 5. Refresh PATH for current session --
echo [3/3] Refreshing PATH ...

for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
if defined USER_PATH set "PATH=%USER_PATH%;%PATH%"

set "PYTHON_HOME=%LOCALAPPDATA%\Programs\Python\Python311"
if exist "%PYTHON_HOME%\python.exe" set "PATH=%PYTHON_HOME%;%PYTHON_HOME%\Scripts;%PATH%"

REM -- 6. Verify --
python --version >nul 2>&1
if errorlevel 1 goto :path_error

echo(
echo [SUCCESS] Python installed:
python --version
pip --version
echo(

del "%INSTALLER%" >nul 2>&1
goto :done

:download_failed
echo(
echo [ERROR] Download failed. Check internet or proxy settings.
echo(
echo         Manual install:
echo         1. Go to https://www.python.org/downloads/
echo         2. Download Python 3.11.x
echo         3. Check "Add python.exe to PATH" during install
echo         4. Run setup_local.bat again
endlocal
exit /b 1

:size_error
echo [ERROR] Downloaded file is too small (%FILESIZE% bytes).
echo         Proxy may have returned a login page.
del "%INSTALLER%" >nul 2>&1
endlocal
exit /b 1

:install_failed
echo(
echo [ERROR] Python install failed.
echo         Try running %INSTALLER% manually.
echo         Check "Add python.exe to PATH" during install!
endlocal
exit /b 1

:path_error
echo(
echo [ERROR] Python installed but not found in PATH.
echo         Close this window and run setup_local.bat again.
del "%INSTALLER%" >nul 2>&1
endlocal
exit /b 1

:done
endlocal
exit /b 0