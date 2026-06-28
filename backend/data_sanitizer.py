"""
backend/data_sanitizer.py
Centralized Data Sanitization Layer — Kelompok 2 ITSB

All statistical functions MUST call sanitize_series() or sanitize_numeric_cols()
before doing any math to prevent TypeError / ValueError on inconsistent data.

Rules enforced here:
  1. Automated Type Validation  — check dtype before stats
  2. Forced Conversion          — pd.to_numeric(errors='coerce') for string cols
  3. Empty Data Handling        — return 'N/A' safely if series becomes empty
  4. Safe Correlation Columns   — filter only truly numeric cols for df.corr()
"""

import numpy as np
import pandas as pd
import logging
import re

logger = logging.getLogger(__name__)


def clean_and_parse_numeric(val):
    """
    Clean currency symbols, thousands separators (dot vs comma), percent signs, 
    and other formatting to safely parse string values to floats.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    
    # Convert to string and clean whitespace
    s = str(val).strip()
    if not s:
        return np.nan
        
    s_lower = s.lower()
    is_rp = 'rp' in s_lower or 'idr' in s_lower
    
    # Strip any common non-numeric chars but keep signs, dots, commas, percent
    s_cleaned = re.sub(r'[^\d.,\-+%]', '', s)
    if not s_cleaned:
        return np.nan
        
    is_percent = False
    if '%' in s_cleaned:
        is_percent = True
        s_cleaned = s_cleaned.replace('%', '')
        
    # Resolve dot and comma
    if '.' in s_cleaned and ',' in s_cleaned:
        first_dot = s_cleaned.find('.')
        first_comma = s_cleaned.find(',')
        if first_dot < first_comma:
            # '.' is thousands, ',' is decimal: e.g., 1.234,56
            s_cleaned = s_cleaned.replace('.', '').replace(',', '.')
        else:
            # ',' is thousands, '.' is decimal: e.g., 1,234.56
            s_cleaned = s_cleaned.replace(',', '')
    elif '.' in s_cleaned:
        # Only dot(s) exist.
        if s_cleaned.count('.') > 1:
            s_cleaned = s_cleaned.replace('.', '')
        else:
            # Single dot. E.g. '187.542' or '12.5'.
            # If it has Rp/IDR, a single dot followed by exactly 3 digits is almost certainly thousands separator.
            parts = s_cleaned.split('.')
            if is_rp and len(parts) == 2 and len(parts[1]) == 3:
                s_cleaned = s_cleaned.replace('.', '')
    elif ',' in s_cleaned:
        # Only comma(s) exist.
        if s_cleaned.count(',') > 1:
            s_cleaned = s_cleaned.replace(',', '')
        else:
            # Single comma. E.g. '12,5' -> '12.5'.
            s_cleaned = s_cleaned.replace(',', '.')
            
    try:
        val_float = float(s_cleaned)
        if is_percent:
            val_float = val_float / 100.0
        return val_float
    except ValueError:
        return np.nan



# ─────────────────────────────────────────────────────────────────────────────
# CORE: sanitize a single series
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_series(series: pd.Series, col_name: str = "") -> pd.Series:
    """
    Return a clean, numeric-only pandas Series suitable for math operations.

    Steps:
      1. If already numeric dtype → drop NaN and return.
      2. If object/string → attempt pd.to_numeric(errors='coerce').
         - Values that fail conversion become NaN automatically.
      3. Drop NaN from result.

    Returns an empty Series (float64) if nothing can be salvaged —
    callers must check `.empty` before doing any math.
    """
    if series is None:
        return pd.Series(dtype=float)

    # Already numeric — just drop NaN
    if pd.api.types.is_numeric_dtype(series):
        return series.dropna()

    # Bool → treat as 0/1
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float).dropna()

    # Datetime → not numeric, return empty
    if pd.api.types.is_datetime64_any_dtype(series):
        logger.debug(f"[sanitizer] col '{col_name}' is datetime, skipping numeric sanitize")
        return pd.Series(dtype=float)

    # Object / string → forced conversion
    try:
        cleaned = series.map(clean_and_parse_numeric)
        converted = pd.to_numeric(cleaned, errors='coerce')
        n_valid = converted.notna().sum()
        if n_valid == 0:
            logger.debug(f"[sanitizer] col '{col_name}' has 0 numeric values after coerce")
            return pd.Series(dtype=float)
        if n_valid < len(series) * 0.1:
            # Less than 10% values converted → probably categorical, skip quietly
            logger.debug(f"[sanitizer] col '{col_name}' only {n_valid}/{len(series)} numeric after coerce")
        return converted.dropna()
    except Exception as exc:
        logger.warning(f"[sanitizer] forced conversion failed for col '{col_name}': {exc}")
        return pd.Series(dtype=float)


# ─────────────────────────────────────────────────────────────────────────────
# CORE: get the numeric-valid Series from a DataFrame column
# ─────────────────────────────────────────────────────────────────────────────

def get_numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    """
    Convenience wrapper: returns sanitize_series(df[col], col).
    Safe even if col doesn't exist in df.
    """
    if col not in df.columns:
        return pd.Series(dtype=float)
    return sanitize_series(df[col], col)


# ─────────────────────────────────────────────────────────────────────────────
# CORE: filter a list of columns to only the truly numeric ones
# ─────────────────────────────────────────────────────────────────────────────

def filter_numeric_cols(df: pd.DataFrame, cols: list) -> list:
    """
    From `cols`, keep only those whose sanitized series is non-empty AND
    has at least 2 distinct values (otherwise corr/std is meaningless).

    Use this before df.corr() to prevent TypeError.
    """
    valid = []
    for col in cols:
        if col not in df.columns:
            continue
        s = sanitize_series(df[col], col)
        if not s.empty and s.nunique() >= 2:
            valid.append(col)
    return valid


# ─────────────────────────────────────────────────────────────────────────────
# CORE: sanitize the entire DataFrame's numeric columns in-place (copy)
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_df_numeric_cols(df: pd.DataFrame, num_cols: list) -> pd.DataFrame:
    """
    Return a *copy* of df where each column in `num_cols` has been coerced
    to numeric (non-convertible values → NaN).

    Does NOT modify the original DataFrame.
    """
    df2 = df.copy()
    for col in num_cols:
        if col not in df2.columns:
            continue
        if not pd.api.types.is_numeric_dtype(df2[col]):
            cleaned = df2[col].map(clean_and_parse_numeric)
            df2[col] = pd.to_numeric(cleaned, errors='coerce')
    return df2


# ─────────────────────────────────────────────────────────────────────────────
# SAFE STAT HELPERS  (return 'N/A' when data is invalid)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(val, decimals: int = 2):
    """Format a scalar as rounded float or 'N/A'."""
    if val is None:
        return "N/A"
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return "N/A"
        return round(f, decimals)
    except (TypeError, ValueError):
        return "N/A"


def safe_mean(series: pd.Series):
    s = sanitize_series(series)
    if s.empty:
        return "N/A"
    try:
        return _fmt(s.mean())
    except Exception:
        return "N/A"


def safe_median(series: pd.Series):
    s = sanitize_series(series)
    if s.empty:
        return "N/A"
    try:
        return _fmt(s.median())
    except Exception:
        return "N/A"


def safe_std(series: pd.Series):
    s = sanitize_series(series)
    if s.empty or len(s) < 2:
        return "N/A"
    try:
        return _fmt(s.std())
    except Exception:
        return "N/A"


def safe_min(series: pd.Series):
    s = sanitize_series(series)
    if s.empty:
        return "N/A"
    try:
        return _fmt(s.min())
    except Exception:
        return "N/A"


def safe_max(series: pd.Series):
    s = sanitize_series(series)
    if s.empty:
        return "N/A"
    try:
        return _fmt(s.max())
    except Exception:
        return "N/A"


def safe_skew(series: pd.Series, decimals: int = 4):
    s = sanitize_series(series)
    if s.empty or s.nunique() < 2:
        return "N/A"
    try:
        return _fmt(s.skew(), decimals=decimals)
    except Exception:
        return "N/A"


def safe_kurt(series: pd.Series, decimals: int = 4):
    s = sanitize_series(series)
    if s.empty or s.nunique() < 2:
        return "N/A"
    try:
        return _fmt(s.kurt(), decimals=decimals)
    except Exception:
        return "N/A"


def safe_quantile(series: pd.Series, q: float, decimals: int = 3):
    s = sanitize_series(series)
    if s.empty:
        return "N/A"
    try:
        val = s.quantile(q)
        return _fmt(val, decimals=decimals)
    except Exception:
        return "N/A"


def safe_quantile_raw(series: pd.Series, q: float):
    """Return raw float or None (for math operations, not display)."""
    s = sanitize_series(series)
    if s.empty:
        return None
    try:
        val = float(s.quantile(q))
        if np.isnan(val) or np.isinf(val):
            return None
        return val
    except Exception:
        return None


def safe_iqr_outliers(series: pd.Series):
    """Return (q1, q3, iqr, outlier_count) or None if data invalid."""
    s = sanitize_series(series)
    if s.empty or len(s) < 4:
        return None
    try:
        q1  = float(s.quantile(0.25))
        q3  = float(s.quantile(0.75))
        iqr = q3 - q1
        if iqr == 0:
            return (q1, q3, 0.0, 0)
        lower  = q1 - 1.5 * iqr
        upper  = q3 + 1.5 * iqr
        count  = int(((s < lower) | (s > upper)).sum())
        return (q1, q3, iqr, count)
    except Exception:
        return None


# Max columns for correlation matrix to prevent OOM/timeout
MAX_CORR_COLS = 50


def safe_corr_matrix(df: pd.DataFrame, num_cols: list):
    """
    Compute correlation matrix using only the valid numeric columns.
    Returns (valid_cols, corr_df) or ([], None).
    Limited to MAX_CORR_COLS columns to prevent OOM on 100-column datasets.
    """
    valid = filter_numeric_cols(df, num_cols)
    if len(valid) < 2:
        return [], None
    if len(valid) > MAX_CORR_COLS:
        logger.warning(f"[sanitizer] corr matrix truncated from {len(valid)} to {MAX_CORR_COLS} cols")
        valid = valid[:MAX_CORR_COLS]
    try:
        # Work on a sanitized copy so string-encoded numbers are handled
        df2 = sanitize_df_numeric_cols(df, valid)
        corr = df2[valid].corr()
        return valid, corr
    except Exception as exc:
        logger.warning(f"[sanitizer] corr matrix failed: {exc}")
        return [], None
