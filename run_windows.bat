@echo off
setlocal EnableExtensions
title RainScope - ERA5 Weather ^& Hydrology Server (Port 4000)

REM Pindah ke direktori tempat file batch berada
cd /d "%~dp0"

echo ======================================================================
echo   RainScope Semarang - One-Click Launcher (Windows)
echo ======================================================================
echo.

REM 1. Validasi ketersediaan Python di sistem & PATH
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python belum terpasang atau belum masuk ke PATH Windows!
    echo.
    echo Solusi:
    echo   1. Unduh Python 3 dari https://www.python.org/downloads/
    echo   2. Saat instalasi, WAJIB centang "Add Python to PATH".
    echo   3. Tutup jendela ini lalu jalankan ulang run_windows.bat.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] %PY_VER% terdeteksi.

REM 2. Cek Virtual Environment (.venv)
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment (.venv) belum ada. Membuat .venv baru...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Gagal membuat virtual environment .venv!
        echo.
        pause
        exit /b 1
    )

    call ".venv\Scripts\activate.bat"
    echo [INFO] Menginstal dependency Python yang diperlukan...
    python -m pip install --upgrade pip >nul 2>&1

    if exist "requirements.txt" (
        pip install -r requirements.txt
    ) else (
        pip install xarray netCDF4 pandas matplotlib
    )

    if errorlevel 1 (
        echo.
        echo [ERROR] Gagal menginstal dependency dari requirements.txt.
        echo Periksa koneksi internet Anda lalu coba jalankan ulang script ini.
        echo.
        pause
        exit /b 1
    )
    echo [OK] Seluruh dependency berhasil terpasang.
) else (
    echo [INFO] Mengaktifkan virtual environment (.venv)...
    call ".venv\Scripts\activate.bat"
)

echo.
echo [INFO] Membuka dashboard di browser: http://localhost:4000
start "" /b cmd /c "ping -n 3 127.0.0.1 >nul & start http://localhost:4000"

echo [INFO] Menjalankan server Python (Ctrl+C untuk berhenti)...
echo.
python process_rain.py

echo.
echo [INFO] Proses server berakhir.
pause
