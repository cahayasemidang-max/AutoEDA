"""
backend/data_cleaning.py
Data Cleaning — analisis kualitas & pembersihan dataset otomatis.
"""

import pandas as pd
import numpy as np


def analyze_quality(df):
    """
    Analisis kualitas per kolom sebelum/sesudah cleaning.

    Returns list[dict] dengan: column, dtype, missing, missing_pct,
    duplicates_in_col, unique, issues
    """
    total = len(df)
    rows = []

    for col in df.columns:
        series = df[col]
        missing = int(series.isna().sum())
        miss_pct = round(missing / total * 100, 2) if total else 0.0
        dup_in_col = int(series.duplicated().sum()) if series.notna().any() else 0
        unique = int(series.nunique(dropna=True))

        issues = []
        if miss_pct > 50:
            issues.append('High missing (>50%)')
        elif miss_pct > 0:
            issues.append('Has missing values')
        if unique <= 1 and total > 0:
            issues.append('Constant column')
        if pd.api.types.is_object_dtype(series.dtype):
            stripped = series.dropna().astype(str).str.strip()
            if (stripped == '').any():
                issues.append('Empty strings')

        rows.append({
            'column': col,
            'dtype': str(series.dtype),
            'missing': missing,
            'missing_pct': miss_pct,
            'unique': unique,
            'issues': ', '.join(issues) if issues else 'OK',
            'status': 'warning' if issues else 'ok',
        })

    return rows


def clean_dataset(df, options=None):
    """
    Membersihkan dataset berdasarkan opsi yang dipilih.

    Parameters
    ----------
    options : dict
        strip_whitespace      (bool, default True)
        empty_to_nan          (bool, default True)
        drop_duplicates       (bool, default True)
        drop_empty_cols       (bool, default True)  — kolom 100% kosong
        drop_high_missing     (float, default 0)    — threshold 0–1, 0 = off
        fill_missing_numeric  (str: 'none'|'mean'|'median')
        fill_missing_categorical (str: 'none'|'mode')
        cap_outliers          (bool, default False) — IQR cap pada numerik

    Returns
    -------
    df_clean : DataFrame
    log      : list[str]  — ringkasan langkah yang dilakukan
    """
    opts = {
        'strip_whitespace': True,
        'empty_to_nan': True,
        'drop_duplicates': True,
        'drop_empty_cols': True,
        'drop_high_missing': 0.0,
        'fill_missing_numeric': 'none',
        'fill_missing_categorical': 'none',
        'cap_outliers': False,
    }
    if options:
        opts.update(options)

    df = df.copy()
    log = []
    rows_before = len(df)
    cols_before = len(df.columns)

    # Normalisasi nama kolom
    new_cols = [str(c).strip() for c in df.columns]
    if list(df.columns) != new_cols:
        df.columns = new_cols
        log.append('Column names trimmed')

    # Auto-detect dan parse kolom datetime (sebelum operasi lain)
    datetime_converted = 0
    for col in df.select_dtypes(include=['object', 'string']).columns:
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        sample = non_null.head(200)
        try:
            parsed = pd.to_datetime(sample, errors='coerce')
            if parsed.notna().mean() >= 0.40:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                datetime_converted += 1
        except Exception:
            pass
    if datetime_converted:
        log.append(f'Auto-converted {datetime_converted} column(s) to datetime')

    # Strip whitespace pada kolom teks
    if opts['strip_whitespace']:
        for col in df.select_dtypes(include=['object', 'string']).columns:
            df[col] = df[col].apply(
                lambda x: x.strip() if isinstance(x, str) else x
            )
        log.append('Whitespace stripped from text columns')

    # String kosong → NaN
    if opts['empty_to_nan']:
        for col in df.select_dtypes(include=['object', 'string']).columns:
            df[col] = df[col].replace(r'^\s*$', np.nan, regex=True)
        log.append('Empty strings converted to NaN')

    # Hapus kolom 100% kosong
    if opts['drop_empty_cols']:
        empty_cols = [c for c in df.columns if df[c].isna().all()]
        if empty_cols:
            df = df.drop(columns=empty_cols)
            log.append(f'Dropped {len(empty_cols)} fully empty column(s): {", ".join(empty_cols)}')

    # Hapus kolom dengan missing sangat tinggi
    thresh = float(opts.get('drop_high_missing') or 0)
    if thresh > 0:
        high_miss = [c for c in df.columns if df[c].isna().mean() > thresh]
        if high_miss:
            df = df.drop(columns=high_miss)
            log.append(f'Dropped {len(high_miss)} column(s) with >{thresh*100:.0f}% missing')

    # Hapus baris duplikat
    if opts['drop_duplicates']:
        dup_count = int(df.duplicated().sum())
        if dup_count > 0:
            df = df.drop_duplicates()
            log.append(f'Removed {dup_count} duplicate row(s)')

    # Imputasi missing numerik
    fill_num = opts.get('fill_missing_numeric', 'none')
    if fill_num in ('mean', 'median'):
        num_cols = df.select_dtypes(include=['number']).columns
        filled = 0
        for col in num_cols:
            n = int(df[col].isna().sum())
            if n > 0:
                val = df[col].median() if fill_num == 'median' else df[col].mean()
                df[col] = df[col].fillna(val)
                filled += n
        if filled:
            log.append(f'Filled {filled} numeric missing value(s) with {fill_num}')

    # Imputasi missing kategorik
    fill_cat = opts.get('fill_missing_categorical', 'none')
    if fill_cat == 'mode':
        cat_cols = df.select_dtypes(include=['object', 'category', 'string']).columns
        filled = 0
        for col in cat_cols:
            n = int(df[col].isna().sum())
            if n > 0:
                mode_val = df[col].mode()
                if not mode_val.empty:
                    df[col] = df[col].fillna(mode_val.iloc[0])
                    filled += n
        if filled:
            log.append(f'Filled {filled} categorical missing value(s) with mode')

    # Cap outlier (IQR) — winsorize ke batas
    if opts.get('cap_outliers'):
        capped = 0
        for col in df.select_dtypes(include=['number']).columns:
            s = df[col].dropna()
            if len(s) < 4:
                continue
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            before = ((df[col] < lo) | (df[col] > hi)).sum()
            df[col] = df[col].clip(lower=lo, upper=hi)
            capped += int(before)
        if capped:
            log.append(f'Capped {capped} outlier value(s) using IQR method')

    rows_after = len(df)
    cols_after = len(df.columns)
    if not log:
        log.append('No changes needed — dataset already clean')

    log.insert(0, f'Shape: {rows_before}×{cols_before} → {rows_after}×{cols_after}')

    return df, log


def get_cleaning_summary(df_before, df_after, log):
    """Ringkasan before/after untuk KPI cards."""
    def _missing_cells(d):
        return int(d.isna().sum().sum())

    miss_before = _missing_cells(df_before)
    miss_after = _missing_cells(df_after)
    total_before = df_before.size
    total_after = df_after.size

    return {
        'rows_before': len(df_before),
        'rows_after': len(df_after),
        'cols_before': len(df_before.columns),
        'cols_after': len(df_after.columns),
        'missing_before': miss_before,
        'missing_after': miss_after,
        'missing_pct_before': round(miss_before / total_before * 100, 2) if total_before else 0,
        'missing_pct_after': round(miss_after / total_after * 100, 2) if total_after else 0,
        'duplicates_removed': len(df_before) - len(df_after) if len(df_before) > len(df_after) else 0,
        'log': log,
    }
