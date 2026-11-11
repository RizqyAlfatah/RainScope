#!/usr/bin/env bash
set -u

# Pindah ke direktori tempat script berada
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "======================================================================"
echo "  RainScope Semarang - One-Click Launcher (Linux)"
echo "======================================================================"
echo ""

# 1. Validasi ketersediaan Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] Python 3 belum terpasang di sistem!"
    echo "Instal terlebih dahulu melalui package manager distro Anda (python3, pip, venv)."
    echo ""
    read -rp "Tekan Enter untuk keluar..."
    exit 1
fi

PY_VER="$(python3 --version 2>&1)"
echo "[OK] $PY_VER terdeteksi."

# 2. Cek Virtual Environment (.venv)
if [ ! -f ".venv/bin/activate" ]; then
    echo "[INFO] Virtual environment (.venv) belum ada. Membuat .venv baru..."
    if ! python3 -m venv .venv; then
        echo "[ERROR] Gagal membuat .venv! Pastikan modul python3-venv tersedia."
        read -rp "Tekan Enter untuk keluar..."
        exit 1
    fi

    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    echo "[INFO] Menginstal dependency Python yang diperlukan..."
    python3 -m pip install --upgrade pip >/dev/null 2>&1 || true

    if [ -f "requirements.txt" ]; then
        if ! pip install -r requirements.txt; then
            echo "[ERROR] Gagal menginstal dependency dari requirements.txt."
            read -rp "Tekan Enter untuk keluar..."
            exit 1
        fi
    else
        if ! pip install xarray netCDF4 pandas matplotlib; then
            echo "[ERROR] Gagal menginstal dependency wajib."
            read -rp "Tekan Enter untuk keluar..."
            exit 1
        fi
    fi
    echo "[OK] Seluruh dependency berhasil terpasang."
else
    echo "[INFO] Mengaktifkan virtual environment (.venv)..."
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
fi

echo ""
# 3. Buka browser otomatis jika xdg-open tersedia
if command -v xdg-open >/dev/null 2>&1; then
    echo "[INFO] Membuka dashboard di browser: http://localhost:4000"
    (sleep 1.5 && xdg-open http://localhost:4000 &> /dev/null) &
else
    echo "[INFO] xdg-open tidak tersedia. Buka manual di browser: http://localhost:4000"
fi

echo "[INFO] Menjalankan server Python (Ctrl+C untuk berhenti)..."
echo ""
python3 process_rain.py
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
    echo ""
    echo "[INFO] Proses berhenti dengan kode $EXIT_CODE."
    read -rp "Tekan Enter untuk menutup..."
fi
