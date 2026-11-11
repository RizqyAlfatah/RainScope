"""
process_rain.py
---------------
Script modular untuk mengekstrak, memproses, dan memvisualisasikan data curah hujan
ERA5 dari Copernicus CDS (format NetCDF / .zip) untuk Kota Semarang.

Fitur:
1. Konversi waktu UTC ke WIB (UTC+7).
2. Fleksibilitas akses file:
   - Prioritas 1: Argumen baris perintah CLI (contoh: `python process_rain.py /path/ke/file.nc`)
   - Prioritas 2: Prompt interaktif drag & drop langsung dengan pembersihan petik/spasi/URI otomatis
   - Fallback: Auto-scan folder lokal jika prompt dikosongkan (tekan Enter)
3. Pembacaan path file .nc langsung tanpa perantara agar proses cepat.
4. Mode Loop Interaktif: Setelah selesai memproses satu file, script tidak langsung keluar,
   melainkan kembali ke menu awal untuk menerima file .nc berikutnya (atau ketik 'q' untuk keluar).
5. Ekstraksi nearest-neighbor koordinat Semarang (-6.99, 110.42).
6. Konversi curah hujan 'tp' dari meter ke milimeter (x 1000).
7. Visualisasi deret waktu per jam dan bar akumulasi harian (berbasis WIB).
8. Ekspor hasil ke CSV dengan kolom 'Waktu_WIB'.
"""

import os
import sys
import glob
import zipfile
import urllib.parse
import xarray as xr
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Target koordinat Kota Semarang
TARGET_LAT = -6.99
TARGET_LON = 110.42
CSV_OUTPUT_PATH = "curah_hujan_semarang.csv"
PLOT_HOURLY_PATH = "curah_hujan_semarang_hourly.png"
PLOT_DAILY_PATH = "curah_hujan_semarang_daily.png"


def clean_path(raw_path: str) -> str:
    """
    Membersihkan string path hasil drag & drop dari terminal,
    menghilangkan tanda petik tunggal/ganda, spasi berlebih, format URI (file://),
    URL encoding (%20), dan escaped backslashes.
    """
    if not raw_path:
        return ""
    p = raw_path.strip()

    # Hapus prefix URI jika ada (misal: file:///path/ke/file)
    if p.startswith("file://"):
        p = p[7:]
        p = urllib.parse.unquote(p)

    # Hapus tanda petik pembungkus ('...' atau "...")
    if (p.startswith("'") and p.endswith("'")) or (p.startswith('"') and p.endswith('"')):
        p = p[1:-1].strip()

    # Tangani URL encoding seperti %20 jika ada
    if "%" in p:
        p_unquoted = urllib.parse.unquote(p)
        if os.path.exists(p_unquoted) or not os.path.exists(p):
            p = p_unquoted

    # Tangani escaped space dari terminal Linux/macOS (misal: path\ dengan\ spasi)
    if "\\" in p and not os.path.exists(p):
        p_unescaped = p.replace(r"\ ", " ")
        if os.path.exists(p_unescaped):
            p = p_unescaped

    # Expand tanda ~ ke home directory
    p = os.path.expanduser(p)
    return p


def extract_zip(zip_path: str, extract_to: str = ".") -> list[str]:
    """
    Mengekstrak file .zip dan mengembalikan daftar path file .nc yang ditemukan.
    """
    print(f"[INFO] Mengekstrak file zip: '{zip_path}' ke '{extract_to}'...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

    extracted_nc = sorted(glob.glob(os.path.join(extract_to, "*.nc")))
    return extracted_nc


def process_target_path(cleaned_path: str, extract_dir: str = ".") -> list[str]:
    """
    Memvalidasi dan membuka path target secara langsung.
    Jika berupa file .nc langsung, akan segera digunakan agar cepat.
    """
    if not os.path.exists(cleaned_path):
        print(f"\n[ERROR] File atau direktori tidak ditemukan di: '{cleaned_path}'")
        return []

    if os.path.isfile(cleaned_path):
        if cleaned_path.lower().endswith(".nc"):
            print(f"[INFO] Langsung menggunakan file .nc: '{cleaned_path}'")
            return [cleaned_path]
        elif cleaned_path.lower().endswith(".zip"):
            print(f"[INFO] Path berupa file arsip .zip: '{cleaned_path}'")
            return extract_zip(cleaned_path, extract_to=extract_dir)
        else:
            print(f"[WARNING] File '{cleaned_path}' bukan berformat .nc maupun .zip.")
            return []

    elif os.path.isdir(cleaned_path):
        nc_in_dir = sorted(glob.glob(os.path.join(cleaned_path, "*.nc")))
        if nc_in_dir:
            print(f"[INFO] Ditemukan {len(nc_in_dir)} file .nc di direktori: '{cleaned_path}'")
            return nc_in_dir
        zip_in_dir = sorted(glob.glob(os.path.join(cleaned_path, "*.zip")))
        if zip_in_dir:
            return extract_zip(zip_in_dir[0], extract_to=cleaned_path)

    return []


def load_era5_dataset(nc_files: list[str]) -> xr.Dataset:
    """
    Membaca satu atau kumpulan file NetCDF ERA5 menggunakan xarray.
    """
    if not nc_files:
        raise FileNotFoundError("Tidak ada file .nc yang tersedia untuk dibaca.")

    if len(nc_files) == 1:
        print(f"[INFO] Membuka dataset xarray dari: {nc_files[0]}")
        ds = xr.open_dataset(nc_files[0])
    else:
        print(f"[INFO] Membuka multi-file dataset ({len(nc_files)} files) dengan open_mfdataset...")
        ds = xr.open_mfdataset(nc_files, combine='by_coords')

    return ds


def extract_point_precipitation(
    ds: xr.Dataset,
    target_lat: float = TARGET_LAT,
    target_lon: float = TARGET_LON
) -> pd.DataFrame:
    """
    Mengambil data curah hujan ('tp') pada titik koordinat terdekat (nearest neighbor),
    mengonversi satuannya dari meter (m) ke milimeter (mm), dan mengubah waktu ke WIB (UTC+7).
    """
    lat_key = 'latitude' if 'latitude' in ds.coords else ('lat' if 'lat' in ds.coords else None)
    lon_key = 'longitude' if 'longitude' in ds.coords else ('lon' if 'lon' in ds.coords else None)

    if not lat_key or not lon_key:
        raise KeyError(f"Dimensi koordinat tidak dikenali. Koordinat yang tersedia: {list(ds.coords.keys())}")

    lon_values = ds[lon_key].values
    search_lon = target_lon
    if lon_values.min() >= 0 and target_lon < 0:
        search_lon = target_lon % 360
    elif lon_values.max() > 180 and target_lon < 0:
        search_lon = (target_lon + 360) % 360

    print(f"[INFO] Mengambil titik terdekat untuk Lat: {target_lat}, Lon: {search_lon}...")
    sel_kwargs = {lat_key: target_lat, lon_key: search_lon}
    point_ds = ds.sel(method='nearest', **sel_kwargs)

    actual_lat = float(point_ds[lat_key].values)
    actual_lon = float(point_ds[lon_key].values)
    print(f"[INFO] Koordinat grid ERA5 terdekat: Lat = {actual_lat:.4f}, Lon = {actual_lon:.4f}")

    tp_var = None
    if 'tp' in point_ds.data_vars:
        tp_var = 'tp'
    elif 'total_precipitation' in point_ds.data_vars:
        tp_var = 'total_precipitation'
    else:
        for var in point_ds.data_vars:
            if 'precip' in var.lower() or 'tp' in var.lower():
                tp_var = var
                break
        if not tp_var:
            available_vars = list(point_ds.data_vars.keys())
            if len(available_vars) == 1:
                tp_var = available_vars[0]
            else:
                raise KeyError(f"Variabel curah hujan 'tp' tidak ditemukan. Variabel: {available_vars}")

    print(f"[INFO] Menggunakan variabel curah hujan: '{tp_var}'")
    rain_data = point_ds[tp_var]

    time_key = 'valid_time' if 'valid_time' in rain_data.coords else ('time' if 'time' in rain_data.coords else None)
    if not time_key:
        raise KeyError(f"Koordinat waktu tidak ditemukan pada data. Koordinat: {list(rain_data.coords.keys())}")

    rain_series_mm = (rain_data.to_series() * 1000.0).clip(lower=0.0)

    df = rain_series_mm.reset_index()
    df = df.rename(columns={tp_var: 'Curah_Hujan_mm'})

    # Konversi Waktu ke WIB (UTC+7)
    df['Waktu_UTC'] = pd.to_datetime(df[time_key])
    df['Waktu_WIB'] = df['Waktu_UTC'] + pd.Timedelta(hours=7)

    df = df.sort_values('Waktu_WIB').reset_index(drop=True)
    df_clean = df[['Waktu_WIB', 'Curah_Hujan_mm']].copy()

    df_clean.attrs['grid_lat'] = actual_lat
    df_clean.attrs['grid_lon'] = actual_lon
    df_clean.attrs['target_lat'] = target_lat
    df_clean.attrs['target_lon'] = target_lon

    return df_clean


def plot_hourly_timeseries(df: pd.DataFrame, save_path: str = PLOT_HOURLY_PATH, show: bool = False):
    """
    Membuat grafik deret waktu per jam berbasis WIB (hourly time series).
    """
    plt.figure(figsize=(12, 5))
    plt.plot(df['Waktu_WIB'], df['Curah_Hujan_mm'], color='#1f77b4', linewidth=1.5, label='Curah Hujan per Jam (mm)')
    plt.fill_between(df['Waktu_WIB'], df['Curah_Hujan_mm'], color='#1f77b4', alpha=0.3)

    plt.title('Deret Waktu Curah Hujan Per Jam (WIB) - Kota Semarang (ERA5)', fontsize=14, fontweight='bold', pad=12)
    plt.xlabel('Waktu (WIB)', fontsize=11)
    plt.ylabel('Curah Hujan (mm)', fontsize=11)
    plt.grid(True, linestyle='--', alpha=0.6)

    ax = plt.gca()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b %H:%M'))
    plt.gcf().autofmt_xdate()

    plt.legend(loc='upper right')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300)
        print(f"[INFO] Grafik hourly disimpan ke: {save_path}")

    if show:
        plt.show()
    else:
        plt.close()


def plot_daily_accumulation(df: pd.DataFrame, save_path: str = PLOT_DAILY_PATH, show: bool = False):
    """
    Membuat grafik bar total akumulasi hujan per hari berbasis WIB (daily accumulation).
    """
    df_daily = df.set_index('Waktu_WIB').resample('1D')['Curah_Hujan_mm'].sum().reset_index()
    df_daily = df_daily.rename(columns={'Waktu_WIB': 'Tanggal_WIB', 'Curah_Hujan_mm': 'Total_Hujan_Harian_mm'})

    plt.figure(figsize=(10, 5))
    bars = plt.bar(
        df_daily['Tanggal_WIB'].dt.strftime('%d-%m-%Y'),
        df_daily['Total_Hujan_Harian_mm'],
        color='#0d6efd',
        edgecolor='black',
        alpha=0.85,
        width=0.6,
        label='Akumulasi Harian (mm)'
    )

    for bar in bars:
        height = bar.get_height()
        if height > 0.05:
            plt.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + 0.3,
                f"{height:.1f}",
                ha='center',
                va='bottom',
                fontsize=9
            )

    plt.title('Total Akumulasi Curah Hujan Harian (WIB) - Kota Semarang (ERA5)', fontsize=14, fontweight='bold', pad=12)
    plt.xlabel('Waktu (WIB)', fontsize=11)
    plt.ylabel('Total Curah Hujan (mm/hari)', fontsize=11)
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.legend(loc='upper right')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300)
        print(f"[INFO] Grafik daily disimpan ke: {save_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return df_daily


def run_pipeline(nc_files: list[str]):
    """
    Menjalankan alur lengkap pengolahan data ERA5.
    """
    # 1. Buka dataset xarray
    ds = load_era5_dataset(nc_files)

    # 2. Ekstrak data curah hujan titik Semarang & konversi ke WIB
    df_rain = extract_point_precipitation(ds, target_lat=TARGET_LAT, target_lon=TARGET_LON)

    print("\n[PREVIEW DATA EKSTRAKSI (WIB)]")
    print(df_rain.head(10))
    print("...")
    print(f"Total baris data: {len(df_rain)}")

    # 3. Simpan ke CSV
    df_rain.to_csv(CSV_OUTPUT_PATH, index=False)
    print(f"\n[INFO] Data berhasil disimpan ke: '{CSV_OUTPUT_PATH}'")

    # 4. Visualisasi grafik berbasis WIB
    print("\n[INFO] Menghasilkan grafik dengan label Waktu (WIB)...")
    plot_hourly_timeseries(df_rain, save_path=PLOT_HOURLY_PATH, show=False)
    df_daily = plot_daily_accumulation(df_rain, save_path=PLOT_DAILY_PATH, show=False)

    print("\n[PREVIEW AKUMULASI HARIAN (WIB)]")
    print(df_daily.head(10))


def main():
    """
    Fungsi orkestrasi utama:
    - Jika dipanggil dengan argumen path file (misal: python process_rain.py file.nc),
      jalankan pipeline pemrosesan offline.
    - Jika dipanggil tanpa argumen (misal: python process_rain.py),
      langsung jalankan engine server lokal di port 4000.
    """
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--server"):
        raw_cli = sys.argv[1]
        cleaned_cli = clean_path(raw_cli)
        print(f"[INFO] Menerima input dari argumen CLI: '{cleaned_cli}'")
        nc_files = process_target_path(cleaned_cli)
        if nc_files:
            run_pipeline(nc_files)
            print("\n[SELESAI] Pemrosesan file CLI selesai.")
        return

    # Jalankan server HTTP lokal port 4000
    try:
        import app
        app.run_server()
    except Exception as e:
        print(f"[ERROR] Gagal menjalankan server: {e}")


if __name__ == "__main__":
    main()
