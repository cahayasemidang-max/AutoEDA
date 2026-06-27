import pandas as pd
import numpy as np
import os
import csv
import re
import chardet

NA_VARIANTS = [
    'n/a', 'na', 'null', 'none', 'nan', '-', '--', '?', 'unknown',
    'tidak ada', 'kosong', 'empty', '#n/a', '#n/a n/a', '#n/d',
    'n.a.', '-.', '\\n', '\\t',
    # Uppercase variants (case-insensitive handled in sanitizer)
    'N/A', 'NA', 'NULL', 'None', 'NaN', 'Unknown', 'UNKNOWN',
    '#N/A', '#N/A N/A', '#N/D', 'N.A.', 'KOSONG', 'EMPTY',
    # Mixed case
    'Null', 'None', 'Unknown',
]

# File size threshold for large-file optimizations (10 MB)
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024  # 10 MB in bytes

# Ordered list of encodings to try — covers almost every real-world file
ENCODINGS_TO_TRY = [
    'utf-8',
    'utf-8-sig',     # UTF-8 with BOM (common in Windows Excel exports)
    'utf-16',
    'utf-16-le',
    'utf-16-be',
    'cp1252',        # Windows Western European
    'latin1',        # ISO-8859-1 (very permissive, rarely raises errors)
    'iso-8859-1',
    'iso-8859-2',
    'cp1250',        # Windows Central/Eastern European
    'cp1251',        # Windows Cyrillic
    'gb18030',       # Chinese (superset of GBK and GB2312)
    'gbk',
    'big5',          # Traditional Chinese
    'shift_jis',     # Japanese
    'euc-jp',
    'euc-kr',        # Korean
    'tis-620',       # Thai
]


def _detect_encoding(file_path, n_bytes=50000):
    """
    Deteksi encoding file menggunakan chardet pada sample pertama.
    Fallback ke 'utf-8' jika deteksi gagal atau confidence rendah.
    """
    try:
        with open(file_path, 'rb') as f:
            raw = f.read(n_bytes)
        result = chardet.detect(raw)
        if result and result.get('confidence', 0) >= 0.70 and result.get('encoding'):
            return result['encoding']
    except Exception:
        pass
    return 'utf-8'


def get_delimiter(file_path, encoding='utf-8'):
    """
    Fungsi cerdas untuk mendeteksi separator (pemisah)
    pada file text atau csv (koma, tab, titik koma, dsb).
    """
    try:
        with open(file_path, 'r', encoding=encoding, errors='ignore') as file:
            sample = file.read(4096)
            dialect = csv.Sniffer().sniff(sample)
            return dialect.delimiter
    except Exception:
        try:
            with open(file_path, 'r', encoding=encoding, errors='ignore') as file:
                first_line = file.readline()
                if '\t' in first_line: return '\t'
                if ';' in first_line: return ';'
                if '|' in first_line: return '|'
                return ','
        except Exception:
            return ','


def _sanitize_loaded_df(df, is_large=False):
    """
    Post-load sanitization: bersihkan hasil import file agar lebih
    tahan banting terhadap berbagai tipe data bermasalah.

    Optimasi untuk file besar (is_large=True):
      - Gunakan operasi vectorized (str.strip, replace) bukan .apply()
      - Auto-cast numerik dilakukan dengan sampling lebih kecil
      - Skip date detection pada sample lebih kecil
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # 1. Trim whitespace dan ganti NA variants — VECTORIZED (jauh lebih cepat)
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            # Fully vectorized strip yang tetap mempertahankan object dtype
            # Gunakan where() agar nilai non-string tidak terpengaruh
            try:
                stripped = df[col].where(df[col].isna(), df[col].astype(str).str.strip())
                df[col] = stripped
            except Exception:
                pass  # Jika gagal (mixed types), biarkan as-is
            # Ganti NA variants secara vectorized
            df[col] = df[col].replace(NA_VARIANTS, np.nan)

    # 2. Ganti inf/-inf dengan NaN di semua kolom numerik
    num_cols = df.select_dtypes(include='number').columns
    if len(num_cols) > 0:
        df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)

    # 3. Auto-cast: kolom object yang sebagian besar numerik → float
    # Untuk file besar, kurangi sample size
    sample_size = 100 if is_large else 200
    date_sample_size = 50 if is_large else 200

    for col in df.columns:
        if not pd.api.types.is_object_dtype(df[col]):
            continue
        s = df[col].dropna()
        if s.empty:
            continue

        # Cek dulu apakah ini kolom tanggal — jika ya, jangan auto-cast
        sample = s.head(date_sample_size)
        try:
            parsed = pd.to_datetime(sample, errors='coerce')
            if parsed.notna().mean() >= 0.40:
                # Ini kolom tanggal — skip auto-cast numerik
                continue
        except Exception:
            pass

        # Hitung proporsi nilai yang bisa di-parse sebagai angka
        # Gunakan pd.to_numeric langsung pada sample — paling aman dan cepat
        sample = s.head(sample_size)
        try:
            numeric_sample = pd.to_numeric(sample, errors='coerce')
            numeric_ratio = numeric_sample.notna().mean()
            # Fallback: jika angka ratio rendah, coba juga dengan cleaning
            if numeric_ratio < 0.80:
                try:
                    cleaned_sample = sample.astype(str).str.strip() \
                        .str.replace(r'[^\d.\-+eE,]', '', regex=True) \
                        .str.replace(',', '.', regex=False)
                    numeric_sample2 = pd.to_numeric(cleaned_sample, errors='coerce')
                    numeric_ratio = max(numeric_ratio, numeric_sample2.notna().mean())
                except Exception:
                    pass
        except Exception:
            numeric_ratio = 0.0

        if numeric_ratio >= 0.80:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 4. Drop kolom yang seluruhnya NaN
    df = df.dropna(how='all', axis=1)

    return df


def _try_read_csv(file_path, sep, encoding):
    """
    Helper untuk mencoba membaca CSV dengan encoding dan separator tertentu.
    Mencoba engine 'c' dulu (cepat), fallback ke 'python' (lebih fleksibel).
    """
    try:
        return pd.read_csv(
            file_path, sep=sep, engine='c',
            on_bad_lines='skip', encoding=encoding,
            low_memory=False,
        )
    except Exception:
        return pd.read_csv(
            file_path, sep=sep, engine='python',
            on_bad_lines='skip', encoding=encoding,
        )


def _try_read_csv_all_encodings(file_path, sep):
    """
    Coba baca CSV dengan berbagai encoding. Kembalikan DataFrame pertama
    yang berhasil dimuat dengan kolom > 0 dan baris > 0.
    Urutan: chardet-detected → daftar ENCODINGS_TO_TRY.
    """
    # Deteksi encoding otomatis terlebih dahulu
    detected = _detect_encoding(file_path)
    encodings_ordered = [detected] + [e for e in ENCODINGS_TO_TRY if e != detected]

    last_err = None
    for enc in encodings_ordered:
        try:
            df = _try_read_csv(file_path, sep, enc)
            if df is not None and not df.empty and len(df.columns) > 0:
                return df
        except Exception as e:
            last_err = e
            continue

    # Jika semua gagal, coba dengan errors='replace' pada latin1 (paling permisif)
    try:
        df = pd.read_csv(
            file_path, sep=sep, engine='python',
            on_bad_lines='skip', encoding='latin1',
            encoding_errors='replace',
        )
        if df is not None and len(df.columns) > 0:
            return df
    except Exception as e:
        last_err = e

    if last_err:
        raise last_err
    return None


def _try_read_csv_with_multiple_seps(file_path):
    """
    Jika deteksi delimiter gagal, coba beberapa separator umum secara berurutan.
    Pilih yang menghasilkan paling banyak kolom bermakna.
    """
    seps_to_try = [',', ';', '\t', '|', ':']
    best_df = None
    best_cols = 0

    detected_enc = _detect_encoding(file_path)

    for sep in seps_to_try:
        try:
            df = _try_read_csv(file_path, sep, detected_enc)
            if df is not None and len(df.columns) > best_cols:
                best_cols = len(df.columns)
                best_df = df
        except Exception:
            continue

    return best_df


def load_data(file_path):
    """
    Loads dataset based on file extension — robust untuk berbagai encoding,
    separator, dan ukuran file.

    Optimasi untuk file besar (≥10 MB):
      - Sanitization menggunakan mode is_large=True
      - low_memory=False untuk CSV agar type detection lebih baik
    """
    try:
        ext = os.path.splitext(file_path)[1].lower()
        file_size = os.path.getsize(file_path)
        is_large = file_size >= LARGE_FILE_THRESHOLD

        if is_large:
            print(f"[data_loader] File besar terdeteksi ({file_size / 1024 / 1024:.1f} MB), menggunakan mode optimasi.")

        # ── CSV / TXT ──────────────────────────────────────────────────────────
        if ext in ['.csv', '.txt']:
            detected_enc = _detect_encoding(file_path)
            detected_sep = get_delimiter(file_path, encoding=detected_enc)

            # Coba baca dengan encoding yang terdeteksi
            df = None
            try:
                df = _try_read_csv(file_path, detected_sep, detected_enc)
                # Validasi: jika hanya 1 kolom, mungkin delimiter salah
                if df is not None and len(df.columns) == 1 and len(df) > 0:
                    # Coba semua encoding dengan separator yang sama
                    df_multi_enc = _try_read_csv_all_encodings(file_path, detected_sep)
                    if df_multi_enc is not None and len(df_multi_enc.columns) > 1:
                        df = df_multi_enc
                    else:
                        # Coba separator berbeda
                        df_multi_sep = _try_read_csv_with_multiple_seps(file_path)
                        if df_multi_sep is not None and len(df_multi_sep.columns) > len(df.columns):
                            df = df_multi_sep
            except Exception as e:
                print(f"[data_loader] Percobaan 1 gagal: {e}")
                df = None

            # Jika masih gagal, coba semua kombinasi encoding
            if df is None or df.empty:
                print("[data_loader] Mencoba semua encoding...")
                df = _try_read_csv_all_encodings(file_path, detected_sep)

            # Jika masih gagal, coba semua separator
            if df is None or df.empty:
                print("[data_loader] Mencoba semua separator...")
                df = _try_read_csv_with_multiple_seps(file_path)

            if df is None:
                return None

            return _sanitize_loaded_df(df, is_large=is_large)

        # ── Excel ──────────────────────────────────────────────────────────────
        elif ext in ('.xlsx', '.xls'):
            try:
                df = pd.read_excel(file_path)
            except Exception as e:
                print(f"[data_loader] Excel read gagal: {e}")
                # Coba dengan openpyxl/xlrd engine secara eksplisit
                try:
                    engine = 'openpyxl' if ext == '.xlsx' else 'xlrd'
                    df = pd.read_excel(file_path, engine=engine)
                except Exception as e2:
                    print(f"[data_loader] Excel fallback gagal: {e2}")
                    return None

            return _sanitize_loaded_df(df, is_large=is_large)

        else:
            raise ValueError(f"Format file tidak didukung: {ext}")

    except Exception as e:
        print(f"[data_loader] Error kritis saat memuat data: {e}")
        return None
