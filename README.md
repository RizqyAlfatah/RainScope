# RainScope — Dashboard Curah Hujan & Hidrologi ERA5 Semarang

Aplikasi dashboard interaktif berbasis Python + HTML untuk menganalisis data curah hujan ERA5 Copernicus (NetCDF `.nc` / `.zip`) dalam zona waktu WIB (`UTC+7`) di **http://localhost:4000**.

---

## Panduan Menjalankan Aplikasi

> Catatan penting: jika memindahkan folder antar OS, hapus folder `.venv` lama terlebih dahulu agar launcher membuat `.venv` baru sesuai sistem operasi Anda.

### 1. Windows (10 / 11)
**Syarat:** Python 3 terpasang (saat instalasi centang **Add Python to PATH**).

- **Cara Cepat (One-Click):**
  Klik ganda file **`run_windows.bat`**. Script otomatis membuat `.venv` (jika belum ada), menginstal pustaka di `requirements.txt`, membuka browser ke `http://localhost:4000`, dan menyalakan server.
- **Cara Manual (CMD):**
  ```bat
  .venv\Scripts\activate.bat
  python process_rain.py
  ```
  Untuk keluar dari `.venv`: ketik `deactivate`.

---

### 2. Linux (Arch / CachyOS, Ubuntu, Fedora, dll.)
**Syarat:** `python3` (beserta modul `venv` & `pip`) terpasang.

- **Cara Cepat (One-Click / Terminal):**
  1. Beri izin eksekusi (cukup sekali):
     ```bash
     chmod +x run_linux.sh
     ```
  2. Jalankan:
     ```bash
     ./run_linux.sh
     ```
  Script otomatis menyiapkan `.venv`, menginstal `requirements.txt`, membuka browser lewat `xdg-open` ke `http://localhost:4000`, dan menyalakan server.
- **Cara Manual (Terminal):**
  ```bash
  source .venv/bin/activate
  python3 process_rain.py
  ```
  Untuk keluar dari `.venv`: ketik `deactivate`.

---

## Ringkasan File Penting

| File | Fungsi |
| :--- | :--- |
| `run_windows.bat` | Launcher one-click Windows |
| `run_linux.sh` | Launcher one-click Linux |
| `requirements.txt` | Daftar pustaka wajib (`xarray`, `netCDF4`, `pandas`, `matplotlib`) |
| `process_rain.py` | Entrypoint server dashboard & pemroses file `.nc` CLI |
| `app.py` | Server REST API lokal port `4000` |
| `index.html` | Antarmuka web dashboard (Grafik, Filter Island, Tabel Hidrologi, Upload `.nc`) |
