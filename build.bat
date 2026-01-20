@echo off
REM Build script for The-Uplink Windows executable
REM Run this script from the project root directory

echo ============================================
echo Building The-Uplink Windows Executable
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip is not available
    pause
    exit /b 1
)

echo Step 1: Installing dependencies...
echo ------------------------------------------
pip install -r requirements.txt
pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo Step 2: Building executable with PyInstaller...
echo ------------------------------------------
pyinstaller The-Uplink.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)
echo.

echo ============================================
echo Build complete!
echo ============================================
echo.
echo The executable is located at: dist\The-Uplink\The-Uplink.exe
echo.
echo To create an installer:
echo 1. Download and install Inno Setup from https://jrsoftware.org/isinfo.php
echo 2. Open installer.iss in Inno Setup Compiler
echo 3. Click Build -^> Compile
echo 4. The installer will be created in installer_output\
echo.
pause
