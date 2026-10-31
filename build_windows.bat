@echo off
REM Compila o Vorticis PDF Editor no Windows (requer Python 3.10+ instalado)
REM Resultado: dist\VorticisPDF\VorticisPDF.exe  e (se o Inno Setup estiver instalado)
REM            installer\Output\VorticisPDF-Setup-x.y.z.exe
setlocal
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller || goto :error
python tools\fetch_tessdata.py || goto :error
pyinstaller --noconfirm VorticisPDF.spec || goto :error
where iscc >nul 2>nul && iscc installer\vorticis.iss
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer\vorticis.iss
echo.
echo Pronto! Executavel em dist\VorticisPDF\VorticisPDF.exe
goto :eof
:error
echo Falha na compilacao.
exit /b 1
