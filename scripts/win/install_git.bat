@echo off
REM SPRi Newsletter - Git for Windows auto-install script
REM Called by setup_local.bat / update.bat. Installs Git if not found.
chcp 65001 >nul

setlocal

set GIT_VERSION=2.45.2
set GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe
set INSTALLER=%TEMP%\git-installer-%GIT_VERSION%.exe

REM -- 1. Check if Git is already installed --
git --version >nul 2>&1
if not errorlevel 1 (
    echo [Git] Already installed:
    git --version
    goto :done
)

REM -- 2. Git not found --
echo(
echo ============================================================
echo  Git for Windows %GIT_VERSION% Auto Install
echo ============================================================
echo(
echo  Git is not installed.
echo  Downloading from github.com/git-for-windows ...
echo(

REM -- 3. Download --
echo [1/3] Downloading Git %GIT_VERSION% ...
echo       URL: %GIT_URL%
echo(

curl -L -o "%INSTALLER%" "%GIT_URL%" --progress-bar --ssl-no-revoke
if errorlevel 1 goto :download_failed

for %%F in ("%INSTALLER%") do set FILESIZE=%%~zF
if not defined FILESIZE goto :download_failed
if %FILESIZE% LSS 1000000 goto :size_error

REM -- 4. Silent Install --
echo [2/3] Installing Git %GIT_VERSION% ... (1-2 min)
echo(

"%INSTALLER%" /VERYSILENT /NORESTART /NOCANCEL /SUPPRESSMSGBOXES /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"
if errorlevel 1 goto :install_failed

REM -- 5. Refresh PATH for current session --
echo [3/3] Refreshing PATH ...

if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "PATH=%ProgramFiles(x86)%\Git\cmd;%PATH%"

REM -- 6. Verify --
git --version >nul 2>&1
if errorlevel 1 goto :path_error

echo(
echo [SUCCESS] Git installed:
git --version
echo(

del "%INSTALLER%" >nul 2>&1
goto :done

:download_failed
echo(
echo [ERROR] Download failed. Check internet or proxy settings.
echo(
echo         Manual install:
echo         1. Go to https://git-scm.com/download/win
echo         2. Download 64-bit Git for Windows installer
echo         3. Run installer with default options
echo         4. Verify: open new cmd and run "git --version"
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
echo [ERROR] Git install failed.
echo         Try running %INSTALLER% manually.
endlocal
exit /b 1

:path_error
echo(
echo [ERROR] Git installed but not found in PATH.
echo         Close this window and re-run the calling script.
del "%INSTALLER%" >nul 2>&1
endlocal
exit /b 1

:done
endlocal
exit /b 0
