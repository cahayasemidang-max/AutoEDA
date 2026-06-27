"""
backend/preprocessing.py
Smart column type detection — robust untuk dataset apapun.

Logika deteksi:
  1. Kolom ID/index (Student_ID, user_id, zip_code, dll) → dikeluarkan dari num_cols
  2. Kolom numerik tapi isinya kode/kategori (< threshold unique ratio) → masuk cat_cols
  3. Kolom object tapi isinya angka semua → dicoba convert ke numerik
  4. Boolean → masuk cat_cols
  5. Datetime → dikeluarkan dari keduanya (ditangani time_series.py)
"""

import pandas as pd
import numpy as np
import re
from backend.data_sanitizer import clean_and_parse_numeric

# ── Threshold ────────────────────────────────────────────────────────────────
# Kolom numerik dengan unique ratio < ini DAN unique count < MAX_CAT_UNIQUE
# dianggap kolom kategorik (misal: rating 1-5, kode wilayah 1-10)
UNIQUE_RATIO_THRESHOLD = 0.05   # 5% dari total baris
MAX_CAT_UNIQUE         = 20     # maksimal 20 nilai unik untuk dianggap kategorik

# Kolom numerik dengan unique count < ini SELALU dianggap kategorik
# (misal: kolom binary 0/1, rating 1-5)
FORCE_CAT_UNIQUE = 2

# Pola nama kolom yang mengindikasikan ID / kode / nomor urut
ID_PATTERNS = re.compile(
    r'(\b|_)(id|index|idx|no|num|number|code|kode|nomor|nomer'
    r'|zip|postal|phone|telp|telpon|fax|nik|nip|nim|nrp'
    r'|barcode|sku|serial|uuid|guid|ref|reference)(\b|_)',
    re.IGNORECASE
)

# Pola nama kolom yang PASTI numerik meskipun unique-nya sedikit
FORCE_NUM_PATTERNS = re.compile(
    r'(\b|_)(price|harga|cost|biaya|salary|gaji|revenue|profit|loss'
    r'|amount|total|subtotal|qty|quantity|jumlah|berat|weight'
    r'|height|tinggi|width|lebar|length|panjang|area|luas'
    r'|age|umur|usia|tahun|year|score|nilai|grade|rate|ratio'
    r'|percent|pct|persen|suhu|temperature|temp|lat|lon|latitude|longitude'
    r'|distance|jarak|duration|durasi|time|waktu|hour|jam|minute|menit'
    r'|second|detik|speed|kecepatan|volume|kapasitas|capacity)(\b|_)',
    re.IGNORECASE
)


def _is_id_column(series, col_name):
    """
    Deteksi apakah kolom ini adalah ID / nomor urut yang tidak bermakna
    untuk analisis statistik.
    """
    col_lower = col_name.lower()

    # 1. Nama kolom cocok pola ID
    if ID_PATTERNS.search(col_lower):
        # Pengecualian: jika nama kolom juga cocok pola force_num, bukan ID
        if not FORCE_NUM_PATTERNS.search(col_lower):
            return True

    # 2. Kolom integer dengan nilai unik = jumlah baris (pure index)
    if pd.api.types.is_integer_dtype(series):
        n_unique = series.nunique()
        n_total  = len(series.dropna())
        if n_total > 0 and n_unique == n_total:
            # Pastikan nilainya sequential (1,2,3,... atau 0,1,2,...)
            sorted_vals = series.dropna().sort_values().reset_index(drop=True)
            diffs = sorted_vals.diff().dropna()
            if len(diffs) > 0 and diffs.nunique() == 1:
                return True

    return False


def _looks_categorical(series, col_name, n_rows):
    """
    Deteksi kolom numerik yang sebenarnya bersifat kategorik.
    Contoh: gender (0/1), rating (1-5), kode wilayah (1-10)
    """
    col_lower = col_name.lower()

    # Jika nama kolom cocok pola force_num → pasti numerik
    if FORCE_NUM_PATTERNS.search(col_lower):
        return False

    n_unique = series.nunique()

    # Binary (hanya 2 nilai unik) → kategorik
    if n_unique <= FORCE_CAT_UNIQUE:
        return True

    # Unique ratio sangat kecil DAN jumlah unik di bawah threshold → kategorik
    unique_ratio = n_unique / max(n_rows, 1)
    if unique_ratio < UNIQUE_RATIO_THRESHOLD and n_unique <= MAX_CAT_UNIQUE:
        return True

    return False


def _try_numeric_conversion(series):
    """
    Coba konversi kolom object ke numerik.
    Return series numerik jika berhasil, None jika tidak.
    """
    try:
        cleaned = series.map(clean_and_parse_numeric)
        converted = pd.to_numeric(cleaned, errors='coerce')
        # Jika lebih dari 80% nilai berhasil dikonversi → anggap numerik
        success_rate = converted.notna().sum() / max(len(series), 1)
        if success_rate >= 0.80:
            return converted
    except Exception:
        pass
    return None


def _parsed_dates_plausible(parsed_series):
    """
    Validasi bahwa hasil parsing datetime masuk akal (bukan false positive).
    False positive terjadi ketika pd.to_datetime() menginterpretasi angka kecil
    (tahun, bulan, hari, durasi) sebagai epoch sekon → semuanya jadi tahun 1970.
    """
    if parsed_series.empty:
        return False
    min_date = parsed_series.min()
    max_date = parsed_series.max()
    # Jika semua hasil parse berada di tahun 1970, hampir pasti false positive
    if min_date.year == 1970 and max_date.year == 1970:
        return False
    # Jika rentang kurang dari 1 sekon, dianggap noise
    if (max_date - min_date).total_seconds() < 1:
        return False
    return True


def detect_time_series_cols(df):
    """
    Smart Time-Series column detector.
    Memeriksa kolom berdasarkan:
       1. Nama kolom mengandung keyword waktu (date, time, tgl, dll)
          DAN berhasil dikonversi via pd.to_datetime()
       2. Sudah bertipe datetime64
       3. Numeric timestamp (epoch seconds)

    Returns:
        list[str]: Nama kolom yang terdeteksi sebagai time-series.
    """
    ts_cols = []

    # Keyword waktu — komponen kalender saja TIDAK termasuk (year, month, day, dll)
    # karena kolom seperti "Year" / "Month" berisi angka kecil yang akan
    # menghasilkan false positive saat di-parse sebagai datetime.
    TS_KEYWORDS = [
        'date', 'time', 'tanggal', 'waktu', 'tgl', 'dt_',
        'timestamp', 'datetime', 'created', 'updated',
        'order_date', 'order_datetime', 'invoice_date',
        'transaksi', 'transaction', 'periode', 'period',
        'arrival', 'departure', 'check_in', 'check_out',
        'start_date', 'end_date', 'due_date', 'birth',
        'lahir', 'expired', 'expiry',
    ]

    for col in df.columns:
        series = df[col]
        s = series.dropna()
        if s.empty:
            continue

        # 1. Sudah datetime64
        if pd.api.types.is_datetime64_any_dtype(series):
            ts_cols.append(col)
            continue

        # 2. Nama mengandung keyword waktu → coba parse
        col_lower = col.lower().replace(' ', '_').replace('-', '_')
        if any(kw in col_lower for kw in TS_KEYWORDS):
            sample = s.head(500)
            try:
                parsed = pd.to_datetime(sample, errors='coerce')
                if parsed.notna().mean() >= 0.40:
                    # Validasi: pastikan bukan false positive (tahun, bulan, durasi)
                    if _parsed_dates_plausible(parsed):
                        ts_cols.append(col)
                        continue
            except Exception:
                pass

        # 3. Object/string — coba parse langsung (tanpa keyword waktu)
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            sample = s.head(200)
            # Lewati jika sample berisi angka semua (sudah ditangani numerik)
            if sample.dtype == 'object' and sample.str.match(r'^\d+\.?\d*$').mean() > 0.8:
                continue
            try:
                parsed = pd.to_datetime(sample, errors='coerce')
                if parsed.notna().mean() >= 0.70:
                    if _parsed_dates_plausible(parsed):
                        ts_cols.append(col)
                        continue
            except Exception:
                pass

        # 4. Numeric — coba sebagai epoch seconds (hanya jika nilai masuk akal)
        if pd.api.types.is_numeric_dtype(series):
            vmax = float(s.max())
            vmin = float(s.min())
            # Epoch seconds biasanya di atas 1e8 (tahun 1973+) dan di bawah 2e9 (tahun 2033)
            # Epoch milliseconds di atas 1e11 dan di bawah 2e12
            is_plausible_epoch = (
                (1e8 < vmax < 2e10) or          # seconds range
                (1e11 < vmax < 2e13)             # milliseconds range
            )
            if not is_plausible_epoch:
                continue
            units = ['s', 'ms']
            for unit in units:
                try:
                    parsed = pd.to_datetime(s.head(200), unit=unit, errors='coerce')
                    if parsed.notna().mean() >= 0.90:
                        if _parsed_dates_plausible(parsed):
                            ts_cols.append(col)
                            break
                except Exception:
                    continue

    return ts_cols


def detect_data_types(df, time_series_cols=None):
    """
    Klasifikasi kolom menjadi numerik dan kategorik secara cerdas.
    
    Args:
        df: DataFrame
        time_series_cols: List kolom time-series (akan dikeluarkan dari num & cat).
    
    Returns:
        num_cols (list): Kolom yang bermakna untuk analisis numerik/statistik
        cat_cols (list): Kolom kategorik (termasuk numerik yang bersifat kategorik)
    
    Kolom yang dikeluarkan dari keduanya:
        - Kolom datetime / time-series
        - Kolom ID/index murni
        - Kolom dengan semua nilai kosong
    """
    n_rows   = len(df)
    ts_set   = set(time_series_cols or [])
    num_cols = []
    cat_cols = []

    for col in df.columns:
        series = df[col]

        # ── Skip kolom kosong total ───────────────────────────────────────────
        if series.isna().all():
            continue

        # ── Skip kolom datetime / time-series ─────────────────────────────────
        if col in ts_set or pd.api.types.is_datetime64_any_dtype(series):
            continue

        # ── Skip kolom boolean → masuk cat ───────────────────────────────────
        if pd.api.types.is_bool_dtype(series):
            cat_cols.append(col)
            continue

        # ── Kolom numerik (int / float) ───────────────────────────────────────
        if pd.api.types.is_numeric_dtype(series):
            # Skip jika ID column
            if _is_id_column(series, col):
                continue

            # Cek apakah numerik ini sebenarnya kategorik
            if _looks_categorical(series, col, n_rows):
                cat_cols.append(col)
            else:
                num_cols.append(col)
            continue

        # ── Kolom object / string ─────────────────────────────────────────────
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            # Coba konversi ke numerik dulu
            converted = _try_numeric_conversion(series)
            if converted is not None:
                # Berhasil dikonversi → cek apakah ID atau kategorik
                if _is_id_column(converted, col):
                    continue
                if _looks_categorical(converted, col, n_rows):
                    cat_cols.append(col)
                else:
                    num_cols.append(col)
            else:
                # Gagal dikonversi → kategorik
                # Skip jika terlalu banyak unique (misal: free text / alamat lengkap)
                n_unique     = series.nunique()
                unique_ratio = n_unique / max(n_rows, 1)
                if unique_ratio > 0.95 and n_unique > 50:
                    continue
                cat_cols.append(col)
            continue

        # ── Tipe lain (category dtype) ────────────────────────────────────────
        if hasattr(series, 'cat'):
            cat_cols.append(col)

    return num_cols, cat_cols