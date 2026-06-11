@echo off
REM Build healthcheck-gui.exe on Windows
REM Run this on the Windows machine with Python installed

echo Installing PyInstaller...
pip install pyinstaller --quiet

echo.
echo Building healthcheck-gui.exe...
pyinstaller healthcheck-gui.spec --clean --noconfirm

echo.
echo Build complete! Check the dist\ folder:
dir dist\healthcheck-gui.exe

echo.
echo You can now run dist\healthcheck-gui.exe by double-clicking it.
pause
