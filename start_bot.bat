@echo off
chcp 65001 >nul
title Telegram Product Store Bot
color 0A

echo.
echo ================================
echo    🤖 TELEGRAM STORE BOT
echo ================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8+ from:
    echo https://www.python.org/downloads/
    echo.
    echo Make to check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ %PYTHON_VERSION% detected

:: Check if required files exist
if not exist "bot.py" (
    echo ❌ bot.py not found in current directory!
    echo.
    echo Please make sure all files are in the same folder:
    echo - bot.py
    echo - database.py  
    echo - add_products.py
    echo - requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo 📦 Checking dependencies...

:: Check if virtual environment exists
if exist "venv\" (
    echo 🚀 Activating virtual environment...
    call venv\Scripts\activate
) else (
    echo 🔧 Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate
    echo 📥 Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ❌ Failed to install dependencies!
        echo Please check your internet connection and try again.
        pause
        exit /b 1
    )
    echo ✅ Dependencies installed successfully!
)

:: Check if database needs initialization
if not exist "bot_database.db" (
    echo.
    echo 💾 First run detected - database will be created
    echo 🛍️ Run add_products.py later to add products
)

echo.
echo ================================
echo 🤖 STARTING TELEGRAM BOT...
echo 📅 Date: %date%
echo ⏰ Time: %time%
echo ================================
echo.
echo 📝 Log output:
echo.

:: Run the bot with error handling
:run_bot
python bot.py

set EXIT_CODE=%errorlevel%

if %EXIT_CODE% == 0 (
    echo.
    echo ✅ Bot stopped normally
) else if %EXIT_CODE% == 1 (
    echo.
    echo ❌ Bot configuration error!
    echo.
    echo Common issues:
    echo - Invalid Bot Token
    echo - No internet connection  
    echo - Admin ID not set properly
    echo.
    echo Check bot.py configuration and try again.
) else (
    echo.
    echo 🔄 Bot crashed with error code %EXIT_CODE%
    echo Restarting in 5 seconds...
    timeout /t 5 /nobreak >nul
    goto run_bot
)

echo.
echo ================================
echo 🤖 BOT SESSION ENDED
echo ================================
echo.
pause