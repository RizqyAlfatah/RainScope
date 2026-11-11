"""
app.py
------
Backend Engine & Local Server (Port 4000) untuk Dashboard Cuaca & Hidrologi ERA5 Semarang.
Menyediakan REST API untuk data nyata, pemrosesan upload file .nc, dan penyajian antarmuka web.
"""

import os
import sys
import glob
import json
import zipfile
import http.server
import socketserver
import urllib.parse
from email.parser import BytesParser
from email import policy
import pandas as pd

PORT = 4000
CSV_FILE = "curah_hujan_semarang.csv"
TARGET_LAT = -6.99
TARGET_LON = 110.42

MONTH_NAMES_ID = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember"
}

_cached_data_json = None
_data_metadata = None


def process_nc_file(nc_file_path: str):
    """
    Mengekstrak data curah hujan titik Semarang (Lat -6.99, Lon 110.42)
    dari file NetCDF (.nc), mengonversi satuan ke mm, dan waktu ke WIB.
    """
    import xarray as xr
    print(f"[INFO] Memproses dataset NetCDF dari: {nc_file_path}...")
    ds = xr.open_dataset(nc_file_path)

    lat_k = 'latitude' if 'latitude' in ds.coords else 'lat'
    lon_k = 'longitude' if 'longitude' in ds.coords else 'lon'
    search_lon = TARGET_LON
    lon_vals = ds[lon_k].values
    if lon_vals.min() >= 0 and TARGET_LON < 0:
        search_lon = TARGET_LON % 360
    elif lon_vals.max() > 180 and TARGET_LON < 0:
        search_lon = (TARGET_LON + 360) % 360

    pt = ds.sel(method='nearest', **{lat_k: TARGET_LAT, lon_k: search_lon})
    tp_var = 'tp' if 'tp' in pt.data_vars else ('total_precipitation' if 'total_precipitation' in pt.data_vars else list(pt.data_vars.keys())[0])
    time_k = 'valid_time' if 'valid_time' in pt[tp_var].coords else 'time'

    # Konversi meter -> milimeter (* 1000.0)
    rain_series_mm = (pt[tp_var].to_series() * 1000.0).clip(lower=0.0)
    df = rain_series_mm.reset_index().rename(columns={tp_var: 'Curah_Hujan_mm'})

    # Konversi UTC -> WIB (+7 jam)
    df['Waktu_UTC'] = pd.to_datetime(df[time_k])
    df['Waktu_WIB'] = df['Waktu_UTC'] + pd.Timedelta(hours=7)
    df_clean = df[['Waktu_WIB', 'Curah_Hujan_mm']].sort_values('Waktu_WIB').reset_index(drop=True)

    df_clean.to_csv(CSV_FILE, index=False)
    print(f"[OK] File {CSV_FILE} berhasil diperbarui ({len(df_clean)} baris data).")
    return df_clean


def extract_nc_if_needed():
    """Memastikan file CSV tersedia dari file .nc atau .zip lokal."""
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 100:
        return

    print("[INFO] Mencari file data mentah ERA5 di folder lokal...")
    nc_files = sorted(glob.glob("*.nc"))
    if not nc_files:
        zip_files = sorted(glob.glob("*.zip"))
        if zip_files:
            print(f"[INFO] Mengekstrak arsip {zip_files[0]}...")
            with zipfile.ZipFile(zip_files[0], 'r') as z:
                z.extractall(".")
            nc_files = sorted(glob.glob("*.nc"))

    if nc_files:
        try:
            process_nc_file(nc_files[0])
        except Exception as e:
            print(f"[ERROR] Gagal memproses NetCDF: {e}")


def load_dataset_payload():
    """Membaca CSV dan mengompilasi struktur JSON lengkap untuk dashboard."""
    global _cached_data_json, _data_metadata
    extract_nc_if_needed()

    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) < 50:
        _cached_data_json = json.dumps({
            "status": "no_data",
            "message": "File data belum tersedia.",
            "has_data": False,
            "metadata": None,
            "records": [],
            "daily_summary": [],
            "months": []
        }).encode("utf-8")
        _data_metadata = {"has_data": False}
        return

    try:
        df = pd.read_csv(CSV_FILE)
        time_col = 'Waktu_WIB' if 'Waktu_WIB' in df.columns else df.columns[0]
        rain_col = 'Curah_Hujan_mm' if 'Curah_Hujan_mm' in df.columns else df.columns[1]

        df['dt'] = pd.to_datetime(df[time_col])
        df['rain'] = pd.to_numeric(df[rain_col], errors='coerce').fillna(0.0).clip(lower=0.0)
        df = df.sort_values('dt').reset_index(drop=True)

        df['date_str'] = df['dt'].dt.strftime('%Y-%m-%d')
        df['month_key'] = df['dt'].dt.strftime('%Y-%m')
        df['month_num'] = df['dt'].dt.month
        df['month_name'] = df['month_num'].map(MONTH_NAMES_ID)
        df['hour'] = df['dt'].dt.hour
        df['time_str'] = df['dt'].dt.strftime('%Y-%m-%d %H:%M:%S')

        # 1. Records jam-jaman
        records = [
            {
                "time": row['time_str'],
                "date": row['date_str'],
                "month": row['month_key'],
                "hour": int(row['hour']),
                "rain": round(float(row['rain']), 4)
            }
            for _, row in df.iterrows()
        ]

        # 2. Daily Summary
        daily_group = df.groupby('date_str')
        daily_summary = []
        for d_str, group in daily_group:
            total_rain = round(float(group['rain'].sum()), 4)
            max_idx = group['rain'].idxmax()
            i_maks = round(float(group.loc[max_idx, 'rain']), 4)
            peak_hour = int(group.loc[max_idx, 'hour'])
            active_hours = int((group['rain'] >= 0.1).sum())

            daily_summary.append({
                "date": d_str,
                "month": group['month_key'].iloc[0],
                "total_rain": total_rain,
                "i_maks": i_maks,
                "peak_hour": peak_hour,
                "active_hours": active_hours
            })

        # 3. Monthly Summary
        monthly_group = df.groupby('month_key')
        months_list = []
        for m_key, m_df in monthly_group:
            m_num = int(m_df['month_num'].iloc[0])
            m_name = m_df['month_name'].iloc[0]
            months_list.append({
                "key": m_key,
                "num": m_num,
                "name": m_name,
                "label": f"{m_name} {m_key.split('-')[0]}",
                "total_rain": round(float(m_df['rain'].sum()), 2),
                "days_count": len(m_df['date_str'].unique()),
                "max_daily": round(float(m_df.groupby('date_str')['rain'].sum().max()), 2)
            })

        months_list.sort(key=lambda x: x['key'])

        start_date = df['date_str'].min()
        end_date = df['date_str'].max()
        total_days = len(daily_summary)
        total_precip = round(float(df['rain'].sum()), 2)
        peak_day_row = max(daily_summary, key=lambda x: x['total_rain'])

        metadata = {
            "station_name": "Kota Semarang, Jawa Tengah",
            "grid_lat": TARGET_LAT,
            "grid_lon": TARGET_LON,
            "timezone": "WIB (UTC+7)",
            "start_date": start_date,
            "end_date": end_date,
            "total_records": len(df),
            "total_days": total_days,
            "total_precip_mm": total_precip,
            "peak_day": peak_day_row['date'],
            "peak_day_rain": peak_day_row['total_rain'],
            "has_data": True
        }

        payload = {
            "status": "success",
            "has_data": True,
            "metadata": metadata,
            "records": records,
            "daily_summary": daily_summary,
            "months": months_list
        }

        _cached_data_json = json.dumps(payload).encode("utf-8")
        _data_metadata = metadata
        print(f"[OK] Payload data siap: {total_days} hari ({start_date} s.d. {end_date}), {total_precip} mm hujan.")

    except Exception as e:
        print(f"[ERROR] Gagal memproses data CSV: {e}")
        _cached_data_json = json.dumps({
            "status": "error",
            "message": str(e),
            "has_data": False,
            "metadata": None,
            "records": [],
            "daily_summary": [],
            "months": []
        }).encode("utf-8")


class WeatherAppServer(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/upload":
            content_type = self.headers.get('Content-Type', '')
            content_length = int(self.headers.get('Content-Length', 0))

            if content_length <= 0:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "error", "message": "File kosong."}')
                return

            post_data = self.rfile.read(content_length)

            try:
                # Parse multipart/form-data
                header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
                msg = BytesParser(policy=policy.default).parsebytes(header_bytes + post_data)

                saved_filename = None
                for part in msg.iter_parts():
                    filename = part.get_filename()
                    if filename and (filename.lower().endswith(".nc") or filename.lower().endswith(".zip")):
                        payload_data = part.get_payload(decode=True)
                        save_path = os.path.join(".", filename)
                        with open(save_path, "wb") as f:
                            f.write(payload_data)
                        saved_filename = save_path
                        break

                if not saved_filename:
                    # Fallback jika upload binary langsung
                    save_path = os.path.join(".", "uploaded_dataset.nc")
                    with open(save_path, "wb") as f:
                        f.write(post_data)
                    saved_filename = save_path

                print(f"[INFO] File berhasil diupload: {saved_filename}")

                # Jika file zip, ekstrak dulu
                if saved_filename.lower().endswith(".zip"):
                    with zipfile.ZipFile(saved_filename, 'r') as z:
                        z.extractall(".")
                    nc_files = sorted(glob.glob("*.nc"))
                    target_nc = nc_files[0] if nc_files else saved_filename
                else:
                    target_nc = saved_filename

                # Jalankan ekstraksi NetCDF titik Semarang
                process_nc_file(target_nc)
                load_dataset_payload()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                resp = json.dumps({
                    "status": "success",
                    "message": "File NetCDF berhasil diunggah dan diproses oleh Python!",
                    "filename": os.path.basename(target_nc)
                })
                self.wfile.write(resp.encode("utf-8"))
                return

            except Exception as e:
                print(f"[ERROR] Upload processing error: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                resp = json.dumps({"status": "error", "message": f"Gagal memproses file: {str(e)}"})
                self.wfile.write(resp.encode("utf-8"))
                return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            if _cached_data_json is not None:
                self.wfile.write(_cached_data_json)
            else:
                self.wfile.write(b'{"has_data": false, "records": []}')
            return

        elif path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            has_data = _data_metadata is not None and _data_metadata.get("total_days", 0) > 0
            res = json.dumps({"status": "online", "has_data": has_data, "metadata": _data_metadata})
            self.wfile.write(res.encode("utf-8"))
            return

        elif path in ["", "/"]:
            self.path = "/index.html"
            return super().do_GET()

        return super().do_GET()

    def log_message(self, format, *args):
        # Membungkam log terminal berulang agar tampilan tetap bersih
        pass


def run_server():
    """Menjalankan server HTTP lokal di port 4000."""
    load_dataset_payload()

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), WeatherAppServer) as httpd:
        print("=" * 60)
        print("ERA5 Weather & Hydrology Engine Aktif!")
        print(f"Buka dashboard di browser Anda: http://localhost:{PORT}")
        print("Tekan Ctrl+C untuk menghentikan server.")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer dihentikan. Sampai jumpa!")
            httpd.server_close()


if __name__ == "__main__":
    run_server()
