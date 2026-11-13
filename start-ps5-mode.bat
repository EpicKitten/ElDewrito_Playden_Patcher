@echo off
rem Starts ElDewrito the way it runs on the PS5 under Playden: the embedded
rem browser runs inside the game process, with no helper processes.
rem
rem   start-ps5-mode.bat          normal start
rem   start-ps5-mode.bat debug    also opens Chrome DevTools on http://127.0.0.1:8884
rem
rem Needs the bridge binkw32.dll (with the real one as binkw32_orig.dll) so the
rem web screens can talk to the game in this mode.

setlocal
cd /d "%~dp0"

if not exist "eldorado.exe" (
	echo eldorado.exe is not in %~dp0
	pause
	exit /b 1
)
if not exist "binkw32_orig.dll" (
	echo binkw32_orig.dll is missing: the bridge is not installed, so Settings and
	echo the other web screens will not open in this mode.
	pause
)

set ARGS=--single-process --in-process-gpu
if /i "%~1"=="debug" set ARGS=%ARGS% -webdebug -webdebug-port 8884 -webdebug-log

start "" "eldorado.exe" %ARGS%
endlocal
