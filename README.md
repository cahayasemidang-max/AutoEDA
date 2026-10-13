# AutoEDA

AutoEDA adalah aplikasi **web berbasis Flask** yang membantu pengguna melakukan Exploratory Data Analysis (EDA) dengan cepat dan terstruktur. Aplikasi ini menerima file dataset, memproses serta membersihkan data, kemudian menampilkan ringkasan statistik dan visualisasi interaktif untuk mendukung pengambilan insight.

---

## Project Overview

AutoEDA berfungsi untuk:
- Mengunggah dataset (mis. CSV / Excel / TXT).
- Melakukan deteksi tipe data (numerik, kategorik, dan time-series).
- Menganalisis kualitas data (missing values, duplikasi, outlier, dsb.).
- Melakukan proses cleaning berbasis pipeline.
- Menyajikan **visualisasi interaktif (Plotly)** dan tabel ringkasan di frontend.
- Mendukung pembuatan laporan (PDF/HTML/Excel/CSV) dari hasil analisis.

---

## Technical Workflow

Berikut alur kerja aplikasi secara teknis dari sisi backend hingga tampilan di frontend:

1. **User Upload Dataset**
   - User mengakses halaman upload dan mengunggah file.
   - Flask menerima file melalui endpoint upload dan menyimpannya ke folder **uploads/**.

2. **Session & Data Loading**
   - Backend menginisialisasi session analisis per dataset menggunakan modul cleaning engine.
   - Data dibaca menggunakan **pandas** (mis. `read_csv`, `read_excel`, atau format lain sesuai kebutuhan).
   - Dataset kemudian siap diproses untuk analisis lanjutan.

3. **Data Cleaning & Quality Analysis**
   - Backend menjalankan pipeline cleaning (opsional sesuai status user/atau quick fix).
   - Engine cleaning menyimpan history langkah cleaning sehingga user dapat melakukan undo/reset.
   - Backend menghitung metrik kualitas data seperti:
     - jumlah missing values
     - duplikasi
     - indikasi outlier
     - ringkasan perubahan sebelum dan sesudah cleaning.

4. **Feature Detection (Numerik/Kategorik/Time-Series)**
   - Backend mendeteksi kolom numerik, kategorik, dan kandidat time-series.
   - Deteksi time-series melibatkan identifikasi kolom bertipe datetime atau pola format tanggal.

5. **Statistical Summaries & Visualizations**
   - Ringkasan statistik dihitung menggunakan pandas/numpy (mis. descriptive statistics).
   - Visualisasi dibuat memakai **Plotly**:
     - histogram & boxplot (numerik)
     - bar & pie (kategorik)
     - scatter & heatmap (bivariate)
     - chart khusus time-series bila tersedia.
   - Hasil Plotly dikonversi ke format JSON agar dapat dirender oleh frontend.

6. **Render di Frontend**
   - Backend menyiapkan konteks halaman dashboard (mis. daftar kolom, preview tabel, metrics, dan plot JSON).
   - Flask merender template HTML (Jinja) di `frontend/templates/`.
   - Frontend menampilkan tabel dan chart:
     - tabel menggunakan HTML rendering dari pandas (`to_html`)
     - chart menggunakan Plotly JS.

---

## Folder Structure

- **`backend/`**
  - Berisi logika utama aplikasi: loading data, cleaning engine, analisis statistik, dan engine visualisasi.
  - Memuat modul-modul seperti:
    - `data_loader.py`, `data_cleaning.py`, `cleaning_engine.py`
    - `descriptive_stats.py`, `advanced_stats.py`
    - `viz_engine.py`, `time_series.py`
    - `report_generator.py` untuk ekspor laporan.

- **`frontend/`**
  - Berisi UI aplikasi:
    - `templates/` untuk halaman Flask (login, upload, dashboard, reporting).
    - `static/` untuk asset (CSS, JavaScript, library JS seperti Plotly).

- **`uploads/`**
  - Folder penyimpanan dataset yang diunggah user.
  - Termasuk subfolder untuk history/hasil sementara (mis. cache session, temp reports) sesuai implementasi aplikasi.

---

## How it Works (Deployment)

AutoEDA di-deploy menggunakan **Hugging Face Spaces** dengan dukungan **Docker**. Dengan cara ini, environment Python dan dependency aplikasi dapat konsisten antara development dan production.

---

## Prerequisites & Installation (Local Run)

### 1) Prasyarat
- Python 3.9+
- Docker (opsional untuk cara running berbasis container)

### 2) Install dependencies
Jika menjalankan lokal tanpa Docker:

```bash
python -m venv venv
.
venv\Scripts\activate
pip install -r requirements.txt
```

### 3) Jalankan aplikasi
```bash
# pada environment Windows PowerShell/CMD, atur variabel yang diperlukan:
set SECRET_KEY=dev

python app.py
```

Aplikasi akan berjalan pada port yang ditentukan (umumnya `7860`, sesuai konfigurasi di `app.py`).

### 4) Mengakses aplikasi
Buka browser dan arahkan ke:
- `http://localhost:7860`

---

## Catatan Penting
- Untuk fitur AI (jika digunakan), pastikan environment variable API key yang diperlukan sudah diset.
- Disarankan menggunakan Docker di lingkungan production agar dependency tidak berubah antar mesin.

