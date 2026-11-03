@echo off
setlocal
set "TIA_OPENNESS_V19=C:\Program Files\Siemens\Automation\Portal V19\PublicAPI\V19"
if not exist "%TIA_OPENNESS_V19%\Siemens.Engineering.dll" (
  echo Siemens.Engineering.dll not found. Edit TIA_OPENNESS_V19 in this file.
  pause
  exit /b 1
)
where msbuild >nul 2>nul
if errorlevel 1 (
  echo MSBuild not found. Open this project from Visual Studio 2022 Developer Command Prompt.
  pause
  exit /b 1
)
msbuild "%~dp0tia-bridge\TIAOpennessWorker\TIAOpennessWorker.csproj" /p:Configuration=Debug /p:Platform=x64 /p:TIA_OPENNESS_V19="%TIA_OPENNESS_V19%" /m
if errorlevel 1 (
  echo Build failed. Copy the first C# compiler error for troubleshooting.
) else (
  echo Worker build completed.
)
pause
