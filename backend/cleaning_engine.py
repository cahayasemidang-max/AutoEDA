"""
backend/cleaning_engine.py
─────────────────────────────────────────────────────────────────────────────
Cleaning Engine — modular, stateful, dengan history/undo stack.

Arsitektur:
  - CleaningSession  : menyimpan df_raw, history stack (list of snapshots)
  - apply_step()     : terapkan 1 langkah cleaning, push ke stack
  - undo()           : pop stack → kembali ke state sebelumnya
  - preview_step()   : hitung dampak tanpa apply (untuk preview modal)
  - get_quality_report() : analisis kualitas lengkap (dipakai Overview + Cleaning tab)

Operations yang didukung:
  handle_missing   : mean | median | mode | drop_rows | fill_value
  remove_outliers  : iqr | zscore
  normalize        : minmax | standard
  drop_duplicates  : (no params)
  strip_whitespace : (no params)
  drop_high_missing: threshold (float 0-1)
  drop_col         : column name
─────────────────────────────────────────────────────────────────────────────
"""

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
import copy
import datetime
import json
import os
import pickle
import re
import gc
from backend.data_sanitizer import clean_and_parse_numeric


# ─── Snapshot model ──────────────────────────────────────────────────────────

class _Snapshot:
    """Satu titik dalam history stack."""
    def __init__(self, df, label, op_type, op_params, summary):
        self.df        = df.copy()           # state DataFrame saat itu
        self.label     = label               # deskripsi singkat, e.g. "Fill missing age with mean"
        self.op_type   = op_type             # jenis operasi
        self.op_params = op_params           # parameter yang dipakai
        self.summary   = summary             # dict ringkasan perubahan
        self.timestamp = datetime.datetime.now().isoformat()


# ─── Cleaning Session ─────────────────────────────────────────────────────────

class CleaningSession:
    """
    Satu sesi cleaning per file.
    Disimpan di server memory (dict global) per filename.
    """

    MAX_HISTORY = 5    # batas undo stack (dikurangi dari 20 untuk hemat memori)

    @staticmethod
    def _get_max_history(df):
        """Dynamic history limit based on DataFrame memory footprint."""
        try:
            mem_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
            if mem_mb > 500:
                return 2
            if mem_mb > 100:
                return 3
            return CleaningSession.MAX_HISTORY
        except Exception:
            return CleaningSession.MAX_HISTORY

    def __init__(self, df_raw: pd.DataFrame, filename: str, session_key: str = None):
        self.filename     = filename
        self._session_key = session_key or filename
        self.df_raw       = df_raw.copy()
        self._history     : list[_Snapshot] = []   # history[0] = state paling awal setelah upload
        self.is_cleaned   = False
        self.ignored_cols = []

        # Push initial state (raw) ke history sebagai titik awal
        self._history.append(_Snapshot(
            df      = df_raw,
            label   = 'Upload awal (raw data)',
            op_type = 'initial',
            op_params = {},
            summary = self._build_summary(df_raw, df_raw, []),
        ))

    # ── Public: current df ────────────────────────────────────────────────────

    @property
    def df_current(self) -> pd.DataFrame:
        return self._history[-1].df

    @property
    def history_labels(self) -> list[dict]:
        """List ringkasan history untuk ditampilkan di UI."""
        result = []
        for i, snap in enumerate(self._history):
            log_lines = snap.summary.get('log', [])
            desc = '; '.join(log_lines[:3]) if log_lines else ''
            result.append({
                'index'    : i,
                'label'    : snap.label,
                'op_type'  : snap.op_type,
                'rows'     : len(snap.df),
                'cols'     : len(snap.df.columns),
                'missing'  : int(snap.df.isna().sum().sum()),
                'is_current': i == len(self._history) - 1,
                'is_initial': i == 0,
                'timestamp': getattr(snap, 'timestamp', ''),
                'description': desc,
            })
        return result

    # ── Apply step ────────────────────────────────────────────────────────────

    def apply_step(self, op_type: str, op_params: dict) -> dict:
        """
        Terapkan 1 langkah cleaning ke df_current.
        Return: dict hasil (ok, label, summary, preview_rows)
        """
        df_before = self.df_current.copy()

        try:
            df_after, label, log = _dispatch_op(df_before, op_type, op_params)
        except Exception as e:
            return {'ok': False, 'error': str(e)}

        summary = self._build_summary(df_before, df_after, log)

        # Trim history jika melebihi batas (dynamic based on memory)
        max_hist = self._get_max_history(df_before)
        if len(self._history) >= max_hist:
            # Pertahankan initial (index 0) + trim dari index 1
            self._history = [self._history[0]] + self._history[-(max_hist - 2):]

        snap = _Snapshot(
            df        = df_after,
            label     = label,
            op_type   = op_type,
            op_params = op_params,
            summary   = summary,
        )
        self._history.append(snap)
        self.is_cleaned = True
        self._save()
        del df_before
        gc.collect()

        return {
            'ok'         : True,
            'label'      : label,
            'summary'    : summary,
            'history'    : self.history_labels,
            'quality'    : get_quality_report(df_after),
            'rows_now'   : len(df_after),
            'cols_now'   : len(df_after.columns),
            'data_status': detect_data_status(df_after),
        }

    # ── Quick Fix ──────────────────────────────────────────────────────────────

    def quick_fix(self) -> dict:
        """
        Jalankan semua operasi cleaning sekaligus: drop duplikat, isi missing
        (mode untuk semua kolom), fix inconsistencies (title), auto-convert dtypes,
        cap outliers (IQR), dan drop kolom irrelevant.
        Disimpan sebagai 1 entry di history (satu undo untuk kembali).
        """
        df = self.df_current.copy()
        all_logs    = []
        step_labels = []

        # 1. Drop duplicates
        df, lbl, log = _op_drop_duplicates(df, {})
        all_logs.extend(log); step_labels.append(lbl)

        # 2b. Konversi empty string → NaN agar terdeteksi sebagai missing
        df, lbl, log = _op_empty_to_nan(df, {})
        all_logs.extend(log); step_labels.append(lbl)

        # 3. Handle missing — mode untuk semua kolom (fallback untuk edge case)
        df, lbl, log = _op_handle_missing(df, {'method': 'mode', 'scope': 'all'})
        all_logs.extend(log); step_labels.append(lbl)

        # 3b. Drop kolom yang 100% NaN (mode gagal isi) — agar tidak ada missing tersisa
        empty_cols = [c for c in df.columns if df[c].isna().all()]
        if empty_cols:
            df = df.drop(columns=empty_cols)
            all_logs.append(f'Menghapus {len(empty_cols)} kolom kosong total: {", ".join(empty_cols)}')

        # 3c. Isi sisa missing (jika ada) dengan median (numerik) / 'Tidak Ada' (teks)
        remaining = int(df.isna().sum().sum())
        if remaining > 0:
            for col in df.columns:
                n_rem = int(df[col].isna().sum())
                if n_rem == 0:
                    continue
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(df[col].median())
                else:
                    df[col] = df[col].fillna('Tidak Ada')
                all_logs.append(f'{col}: fallback isi {n_rem} missing')

        # 4. Fix text inconsistencies
        df, lbl, log = _op_fix_inconsistencies(df, {'method': 'title'})
        all_logs.extend(log); step_labels.append(lbl)

        # 5. Auto-convert dtypes (string→numeric) SEBELUM outlier removal agar
        #    kolom numerik yang tadinya string ikut diperiksa outlier-nya
        df, lbl, log = _op_convert_dtypes(df, {})
        all_logs.extend(log); step_labels.append(lbl)

        # 6. Remove outliers (IQR) — hapus baris, lakukan iterasi hingga benar-benar bersih
        #    Menggunakan 'remove' agar outlier hilang sepenuhnya sehingga deteksi ulang tidak
        #    menemukan outlier baru akibat IQR menyusut setelah capping.
        MAX_ITER = 5
        for _iter in range(MAX_ITER):
            rows_before = len(df)
            df, lbl, log = _op_remove_outliers(df, {'method': 'iqr', 'action': 'remove'})
            all_logs.extend(log)
            if _iter == 0:
                step_labels.append(lbl)
            rows_removed = rows_before - len(df)
            if rows_removed == 0:
                # Tidak ada outlier tersisa — selesai
                break

        # 7. Final safety: isi missing yang mungkin muncul dari convert_dtypes (errors='coerce')
        #    Gunakan median (bukan 0) agar tidak menciptakan outlier baru
        final_missing = int(df.isna().sum().sum())
        if final_missing > 0:
            for col in df.columns:
                n_rem = int(df[col].isna().sum())
                if n_rem == 0:
                    continue
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(df[col].median())
                else:
                    df[col] = df[col].fillna('Tidak Ada')
                all_logs.append(f'{col}: final isi {n_rem} missing (pasca-convert)')
            # Jika masih ada juga, drop baris
            still = int(df.isna().sum().sum())
            if still > 0:
                before = len(df)
                df = df.dropna()
                all_logs.append(f'Dropped {before - len(df)} baris dengan missing (final safety)')

        # 8. Drop irrelevant columns — di akhir karena duplicate/outlier removal
        #    bisa mengubah unique_ratio dan membuat kolom baru menjadi irrelevant
        df, lbl, log = _op_drop_irrelevant_cols(df, {})
        all_logs.extend(log); step_labels.append(lbl)

        # Hitung hanya step yang beneran mengubah data dan sesuai kartu kualitas
        issues_fixed = 0
        for l in step_labels:
            if '0 ' in l or 'tidak ada' in l.lower():
                continue
            # Abaikan langkah optimasi/preprocessing (bukan masalah kualitas)
            if any(s in l.lower() for s in ['empty string', 'convert dtype', 'fix inconsistent']):
                continue
            issues_fixed += 1
        if empty_cols or remaining > 0:
            issues_fixed += 1

        combined_label = f'Quick Fix — {issues_fixed} masalah diperbaiki'
        summary = self._build_summary(self.df_current, df, all_logs)

        snap = _Snapshot(
            df=df, label=combined_label,
            op_type='quick_fix', op_params={},
            summary=summary,
        )
        self._history.append(snap)
        self.is_cleaned = True
        self._save()

        # Free memory after heavy cleaning ops
        gc.collect()

        return {
            'ok'         : True,
            'label'      : combined_label,
            'summary'    : summary,
            'history'    : self.history_labels,
            'quality'    : get_quality_report(df),
            'rows_now'   : len(df),
            'cols_now'   : len(df.columns),
            'data_status': detect_data_status(df),
        }

    # ── Undo ──────────────────────────────────────────────────────────────────

    def undo(self) -> dict:
        """Kembali ke state sebelumnya."""
        if len(self._history) <= 1:
            return {'ok': False, 'error': 'Tidak ada langkah yang bisa di-undo. Ini sudah data awal.'}

        popped = self._history.pop()
        current = self._history[-1]

        # Jika sudah kembali ke state awal, is_cleaned = False
        if len(self._history) == 1:
            self.is_cleaned = False
        self._save()

        return {
            'ok'         : True,
            'undone_label': popped.label,
            'current_label': current.label,
            'history'    : self.history_labels,
            'quality'    : get_quality_report(current.df),
            'rows_now'   : len(current.df),
            'cols_now'   : len(current.df.columns),
            'data_status': detect_data_status(current.df),
        }

    def undo_to(self, index: int) -> dict:
        """Kembali ke snapshot tertentu berdasarkan index."""
        if index < 0 or index >= len(self._history):
            return {'ok': False, 'error': f'Index {index} tidak valid.'}

        self._history = self._history[:index + 1]
        current = self._history[-1]
        self.is_cleaned = len(self._history) > 1
        self._save()

        return {
            'ok'           : True,
            'current_label': current.label,
            'history'      : self.history_labels,
            'quality'      : get_quality_report(current.df),
            'rows_now'     : len(current.df),
            'cols_now'     : len(current.df.columns),
            'data_status'  : detect_data_status(current.df),
        }

    def reset(self) -> dict:
        """Reset ke raw data (state awal)."""
        self._history = [self._history[0]]
        self.is_cleaned = False
        self._save()
        return {
            'ok'      : True,
            'history' : self.history_labels,
            'quality' : get_quality_report(self.df_raw),
            'rows_now': len(self.df_raw),
            'cols_now': len(self.df_raw.columns),
        }

    # ── Disk persistence ─────────────────────────────────────────────────

    def _save(self):
        """Serialize session to disk."""
        _save_session(self)

    # ── Preview (tanpa apply) ─────────────────────────────────────────────────

    def preview_step(self, op_type: str, op_params: dict) -> dict:
        """
        Hitung dampak operasi TANPA menyimpan ke history.
        Return: dict berisi perubahan yang akan terjadi.
        """
        df_before = self.df_current.copy()
        try:
            df_after, label, log = _dispatch_op(df_before, op_type, op_params)
        except Exception as e:
            return {'ok': False, 'error': str(e)}

        rows_removed  = len(df_before) - len(df_after)
        cols_removed  = len(df_before.columns) - len(df_after.columns)
        miss_before   = int(df_before.isna().sum().sum())
        miss_after    = int(df_after.isna().sum().sum())
        miss_filled   = miss_before - miss_after

        return {
            'ok'          : True,
            'label'       : label,
            'log'         : log,
            'rows_before' : len(df_before),
            'rows_after'  : len(df_after),
            'rows_removed': rows_removed,
            'cols_before' : len(df_before.columns),
            'cols_after'  : len(df_after.columns),
            'cols_removed': cols_removed,
            'miss_before' : miss_before,
            'miss_after'  : miss_after,
            'miss_filled' : miss_filled,
            'preview_html': df_after.head(5).to_html(
                classes='data-table', index=False, border=0,
                max_cols=10,
            ),
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_summary(df_before, df_after, log):
        miss_b = int(df_before.isna().sum().sum())
        miss_a = int(df_after.isna().sum().sum())
        return {
            'rows_before'  : len(df_before),
            'rows_after'   : len(df_after),
            'cols_before'  : len(df_before.columns),
            'cols_after'   : len(df_after.columns),
            'missing_before': miss_b,
            'missing_after' : miss_a,
            'rows_removed' : len(df_before) - len(df_after),
            'cols_removed' : len(df_before.columns) - len(df_after.columns),
            'miss_filled'  : max(0, miss_b - miss_a),
            'log'          : log,
        }


# ─── Session registry (in-memory, per process) ───────────────────────────────
# Key: filename, Value: CleaningSession

_sessions: dict[str, CleaningSession] = {}


def get_session(filename: str, df_raw: pd.DataFrame = None) -> CleaningSession:
    """
    Ambil session yang sudah ada, atau buat baru jika df_raw diberikan.
    Jika session tidak ada dan df_raw None → coba load dari disk.
    Jika tidak ada di disk → return None.
    """
    if filename in _sessions:
        return _sessions[filename]

    # Coba load dari disk
    sess = _load_session(filename)
    if sess is not None:
        _sessions[filename] = sess
        return sess

    if df_raw is not None:
        sess = CleaningSession(df_raw, filename, session_key=filename)
        _sessions[filename] = sess
        return sess
    return None


def reset_session(filename: str, df_raw: pd.DataFrame) -> CleaningSession:
    """Buat ulang session (misalnya setelah upload ulang file)."""
    _delete_session_disk(filename)
    sess = CleaningSession(df_raw, filename, session_key=filename)
    _sessions[filename] = sess
    sess._save()
    return sess


def delete_session(filename: str):
    _sessions.pop(filename, None)
    _delete_session_disk(filename)


# ─── Disk persistence ────────────────────────────────────────────────────────

_session_storage_dir = None


def set_session_storage_dir(path: str):
    global _session_storage_dir
    _session_storage_dir = path
    os.makedirs(path, exist_ok=True)


def _get_session_path(session_key: str) -> str | None:
    if _session_storage_dir is None:
        return None
    safe = session_key.replace('/', '_').replace('\\', '_').replace(':', '_')
    return os.path.join(_session_storage_dir, f"{safe}.pkl")


def _save_session(session: CleaningSession):
    path = _get_session_path(session._session_key)
    if path is None:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # For large DataFrames, use parquet instead of pickle for efficiency
        try:
            mem_mb = session.df_current.memory_usage(deep=True).sum() / (1024 * 1024)
            if mem_mb > 50:
                ext = '.parquet'
                data_path = path.replace('.pkl', ext)
                session.df_current.to_parquet(data_path, index=False)
                # Save just the metadata without DataFrame
                meta = {
                    'session_key': session._session_key,
                    'filename': session.filename,
                    'is_cleaned': session.is_cleaned,
                    'ignored_cols': session.ignored_cols,
                    'history_labels': [
                        {'label': s.label, 'op_type': s.op_type, 'op_params': s.op_params,
                         'summary': s.summary, 'timestamp': s.timestamp}
                        for s in session._history
                    ],
                    'data_path': data_path,
                }
                with open(path, 'wb') as f:
                    pickle.dump(meta, f, protocol=pickle.HIGHEST_PROTOCOL)
                return
            else:
                with open(path, 'wb') as f:
                    pickle.dump(session, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            with open(path, 'wb') as f:
                pickle.dump(session, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        print(f"[cleaning_engine] Save error for {session._session_key}: {e}")


def _load_session(session_key: str) -> CleaningSession | None:
    path = _get_session_path(session_key)
    if path is None or not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            data = pickle.load(f)
        # Check if it's a metadata-only save (large DataFrame)
        if isinstance(data, dict) and 'data_path' in data:
            meta = data
            df = pd.read_parquet(meta['data_path'])
            sess = CleaningSession(df, meta['filename'], session_key=meta['session_key'])
            sess.is_cleaned = meta['is_cleaned']
            sess.ignored_cols = meta['ignored_cols']
            # Overwrite history with reconstructed snapshots
            sess._history = []
            for h in meta['history_labels']:
                snap = _Snapshot.__new__(_Snapshot)
                for k, v in h.items():
                    setattr(snap, k, v)
                snap.df = df
                sess._history.append(snap)
            return sess
        return data
    except Exception as e:
        print(f"[cleaning_engine] Load error for {session_key}: {e}")
        return None


def _delete_session_disk(session_key: str):
    path = _get_session_path(session_key)
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            print(f"[cleaning_engine] Delete error for {session_key}: {e}")
    # Also clean up parquet if exists
    parquet_path = path.replace('.pkl', '.parquet') if path else None
    if parquet_path and os.path.exists(parquet_path):
        try:
            os.remove(parquet_path)
        except Exception:
            pass


# ─── Session cleanup ──────────────────────────────────────────────────────────

def cleanup_old_sessions(max_age_hours=24, max_total_mb=500):
    """Remove old session files and limit total disk usage."""
    if _session_storage_dir is None or not os.path.exists(_session_storage_dir):
        return 0
    now = datetime.datetime.now()
    total_size = 0
    removed = 0
    files = []
    for fname in os.listdir(_session_storage_dir):
        fpath = os.path.join(_session_storage_dir, fname)
        if not os.path.isfile(fpath):
            continue
        fsize = os.path.getsize(fpath)
        fmtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
        age_hours = (now - fmtime).total_seconds() / 3600
        files.append((fpath, fsize, age_hours))
        total_size += fsize
    # Remove by age
    for fpath, fsize, age_hours in files:
        if age_hours > max_age_hours:
            try:
                os.remove(fpath)
                removed += 1
                total_size -= fsize
            except Exception:
                pass
    # If still over quota, remove oldest first
    if total_size > max_total_mb * 1024 * 1024:
        sorted_files = sorted(files, key=lambda x: x[2], reverse=True)
        for fpath, fsize, _ in sorted_files:
            if total_size <= max_total_mb * 1024 * 1024:
                break
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                    removed += 1
                    total_size -= fsize
                except Exception:
                    pass
    return removed


# ─── Operation dispatcher ─────────────────────────────────────────────────────

def _dispatch_op(df: pd.DataFrame, op_type: str, params: dict):
    """
    Dispatch operasi cleaning ke handler yang sesuai.
    Return: (df_result, label_str, log_list)
    """
    handlers = {
        'handle_missing'      : _op_handle_missing,
        'remove_outliers'     : _op_remove_outliers,
        'normalize'           : _op_normalize,
        'drop_duplicates'     : _op_drop_duplicates,
        'strip_whitespace'    : _op_strip_whitespace,
        'drop_high_missing'   : _op_drop_high_missing,
        'drop_col'            : _op_drop_col,
        'empty_to_nan'        : _op_empty_to_nan,
        'fix_inconsistencies' : _op_fix_inconsistencies,
        'drop_irrelevant_cols': _op_drop_irrelevant_cols,
        'convert_dtypes'      : _op_convert_dtypes,
        'standardize_numeric' : _op_standardize_numeric,
        'standardize_categorical': _op_standardize_categorical,
    }
    fn = handlers.get(op_type)
    if fn is None:
        raise ValueError(f"Operasi tidak dikenal: '{op_type}'")
    return fn(df, params)


# ─── Individual operation handlers ───────────────────────────────────────────

def _op_handle_missing(df: pd.DataFrame, params: dict):
    """
    Handle missing values.
    params:
      method    : 'mean' | 'median' | 'mode' | 'fill_value' | 'drop_rows'
      columns   : list of column names (opsional; default = semua kolom relevan)
      fill_value: value untuk method 'fill_value'
      scope     : 'numeric' | 'categorical' | 'all'
    """
    method     = params.get('method', 'mean')
    columns    = params.get('columns') or []
    fill_value = params.get('fill_value', 0)
    scope      = params.get('scope', 'all')
    df         = df.copy()
    log        = []
    total_filled = 0
    total_dropped = 0

    # Tentukan kolom target
    if columns:
        target_cols = [c for c in columns if c in df.columns]
    elif scope == 'numeric':
        target_cols = df.select_dtypes(include='number').columns.tolist()
    elif scope == 'categorical':
        target_cols = df.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
    else:
        target_cols = df.columns.tolist()

    if method == 'drop_rows':
        rows_before = len(df)
        df = df.dropna(subset=target_cols if target_cols else None)
        dropped = rows_before - len(df)
        if dropped:
            log.append(f'Dropped {dropped} rows with missing values')
            total_dropped = dropped
    else:
        for col in target_cols:
            n = int(df[col].isna().sum())
            if n == 0:
                continue
            if method == 'mean':
                if pd.api.types.is_numeric_dtype(df[col]):
                    val = df[col].mean()
                    df[col] = df[col].fillna(round(float(val), 4))
                    log.append(f'{col}: filled {n} missing → mean ({val:.4f})')
                    total_filled += n
            elif method == 'median':
                if pd.api.types.is_numeric_dtype(df[col]):
                    val = df[col].median()
                    df[col] = df[col].fillna(round(float(val), 4))
                    log.append(f'{col}: filled {n} missing → median ({val:.4f})')
                    total_filled += n
            elif method == 'mode':
                mode_val = df[col].mode()
                if not mode_val.empty:
                    df[col] = df[col].fillna(mode_val.iloc[0])
                    log.append(f'{col}: filled {n} missing → mode ({mode_val.iloc[0]})')
                    total_filled += n
            elif method == 'fill_value':
                df[col] = df[col].fillna(fill_value)
                log.append(f'{col}: filled {n} missing → "{fill_value}"')
                total_filled += n

    method_labels = {
        'mean': 'Mean', 'median': 'Median', 'mode': 'Mode',
        'fill_value': f'Nilai "{fill_value}"', 'drop_rows': 'Drop Rows',
    }
    label = f'Handle Missing: {method_labels.get(method, method)}'
    if total_filled:
        label += f' ({total_filled} sel diisi)'
    elif total_dropped:
        label += f' ({total_dropped} baris dihapus)'
    else:
        label += ' (0 sel)'

    if not log:
        log.append('Tidak ada missing value ditemukan pada kolom yang dipilih.')

    return df, label, log


def _op_remove_outliers(df: pd.DataFrame, params: dict):
    """
    Remove/cap outliers dengan iterative processing hingga bersih.
    
    Melakukan iterasi berulang: setiap iterasi mendeteksi outlier pada
    data yang tersisa, lalu menghapus/meng-cap-nya. Proses berhenti
    ketika tidak ada lagi outlier yang terdeteksi (convergence).
    
    params:
      method  : 'iqr' | 'zscore'
      action  : 'remove' | 'cap'
      columns : list (opsional; default = semua numerik)
      zscore_threshold: float (default 3.0)
    """
    method    = params.get('method', 'iqr')
    action    = params.get('action', 'remove')
    columns   = params.get('columns') or []
    z_thresh  = float(params.get('zscore_threshold', 3.0))
    df        = df.copy()
    log       = []
    rows_before = len(df)
    MAX_ITER  = 10

    num_cols = df.select_dtypes(include='number').columns.tolist()
    target   = [c for c in columns if c in num_cols] if columns else num_cols

    if not target:
        return df, 'Remove Outliers (tidak ada kolom numerik)', ['Tidak ada kolom numerik yang dipilih.']

    iteration = 0
    total_rows_removed = 0

    while iteration < MAX_ITER:
        iteration += 1
        any_outliers_this_round = False

        if method == 'iqr':
            mask = pd.Series([True] * len(df), index=df.index)
            for col in target:
                if col not in df.columns:
                    continue
                s = df[col].dropna()
                if len(s) < 4:
                    continue
                q1, q3 = s.quantile(0.25), s.quantile(0.75)
                iqr = q3 - q1
                lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                # IQR = 0 → fence = [Q1, Q3]; nilai ≠ Q1 akan terdeteksi sbg outlier
                if iqr == 0:
                    log.append(f'Iterasi {iteration}: {col}: IQR=0, fence=[{lo:.4f},{hi:.4f}]')
                outlier_mask = (df[col] < lo) | (df[col] > hi)
                n_out = int(outlier_mask.sum())
                if n_out == 0:
                    continue
                any_outliers_this_round = True
                if action == 'cap':
                    df[col] = df[col].clip(lower=lo, upper=hi)
                    log.append(f'Iterasi {iteration}: {col}: capped {n_out} outliers IQR [{lo:.2f}, {hi:.2f}]')
                else:
                    mask = mask & ~outlier_mask
                    log.append(f'Iterasi {iteration}: {col}: {n_out} outliers IQR ditandai untuk dihapus')
            if action == 'remove':
                new_df = df[mask]
                rows_removed_here = len(df) - len(new_df)
                total_rows_removed += rows_removed_here
                df = new_df

        elif method == 'zscore':
            mask = pd.Series([True] * len(df), index=df.index)
            for col in target:
                if col not in df.columns:
                    continue
                s = df[col].dropna()
                if len(s) < 4:
                    continue
                z_scores = np.abs(scipy_stats.zscore(s))
                outlier_idx = s.index[z_scores > z_thresh]
                n_out = len(outlier_idx)
                if n_out == 0:
                    continue
                any_outliers_this_round = True
                if action == 'cap':
                    mean_val = float(s.mean())
                    std_val = float(s.std())
                    lo, hi = mean_val - z_thresh * std_val, mean_val + z_thresh * std_val
                    df[col] = df[col].clip(lower=lo, upper=hi)
                    log.append(f'Iterasi {iteration}: {col}: capped {n_out} outliers Z-score >{z_thresh}σ')
                else:
                    mask = mask & ~df.index.isin(outlier_idx)
                    log.append(f'Iterasi {iteration}: {col}: {n_out} outliers Z-score ditandai untuk dihapus')
            if action == 'remove':
                new_df = df[mask]
                rows_removed_here = len(df) - len(new_df)
                total_rows_removed += rows_removed_here
                df = new_df

        if not any_outliers_this_round:
            break

    method_label = 'IQR' if method == 'iqr' else f'Z-Score (>{z_thresh}σ)'
    action_label = 'Dihapus' if action == 'remove' else 'Di-cap'
    label = f'Remove Outliers: {method_label} — {action_label}'

    if log:
        suffix_parts = []
        if total_rows_removed > 0:
            suffix_parts.append(f'{total_rows_removed} baris dihapus')
        if iteration > 1:
            suffix_parts.append(f'{iteration} iterasi')
        if suffix_parts:
            label += ' (' + ', '.join(suffix_parts) + ')'
        else:
            label += ' (0 baris)'
    else:
        label += ' (0 baris)'
        log.append('Tidak ada outlier yang ditemukan pada kolom yang dipilih.')

    return df, label, log


def _op_normalize(df: pd.DataFrame, params: dict):
    """
    Normalisasi data numerik.
    params:
      method  : 'minmax' | 'standard'
      columns : list (opsional; default = semua numerik)
    """
    method   = params.get('method', 'minmax')
    columns  = params.get('columns') or []
    df       = df.copy()
    log      = []

    num_cols = df.select_dtypes(include='number').columns.tolist()
    target   = [c for c in columns if c in num_cols] if columns else num_cols

    for col in target:
        s = df[col].dropna()
        if s.empty:
            continue
        if method == 'minmax':
            mn, mx = float(s.min()), float(s.max())
            if mx - mn == 0:
                log.append(f'{col}: dilewati (range = 0)')
                continue
            df[col] = (df[col] - mn) / (mx - mn)
            log.append(f'{col}: min-max scaled [{mn:.3f}, {mx:.3f}] → [0, 1]')
        elif method == 'standard':
            mean_v, std_v = float(s.mean()), float(s.std())
            if std_v == 0:
                log.append(f'{col}: dilewati (std = 0)')
                continue
            df[col] = (df[col] - mean_v) / std_v
            log.append(f'{col}: standardized μ={mean_v:.3f} σ={std_v:.3f}')

    method_label = 'Min-Max Scaling' if method == 'minmax' else 'Standard Scaling (Z-score)'
    label = f'Normalize: {method_label} ({len(target)} kolom)'

    if not log:
        log.append('Tidak ada kolom yang dinormalisasi.')

    return df, label, log


def _op_drop_duplicates(df: pd.DataFrame, params: dict):
    df         = df.copy()
    n_before   = len(df)
    df         = df.drop_duplicates()
    n_removed  = n_before - len(df)
    log        = [f'Removed {n_removed} duplicate row(s)'] if n_removed else ['Tidak ada baris duplikat.']
    label      = f'Drop Duplicates ({n_removed} baris dihapus)' if n_removed else 'Drop Duplicates (tidak ada duplikat)'
    return df, label, log


def _op_strip_whitespace(df: pd.DataFrame, params: dict):
    df   = df.copy()
    log  = []
    cols = df.select_dtypes(include=['object', 'string']).columns.tolist()
    for col in cols:
        df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
    if cols:
        log.append(f'Stripped whitespace dari {len(cols)} kolom teks.')
    label = f'Strip Whitespace ({len(cols)} kolom)'
    return df, label, log


def _op_drop_high_missing(df: pd.DataFrame, params: dict):
    """
    Drop kolom dengan missing value di atas threshold.
    params:
      threshold        : float 0-1 (default 0.5)
      exclude_datetime : bool (default True) — lindungi kolom datetime
      exclude_columns  : list[str] opsional — kolom yang TIDAK ikut di-drop
    """
    threshold        = float(params.get('threshold', 0.5))
    exclude_datetime = bool(params.get('exclude_datetime', True))
    user_exclude     = params.get('exclude_columns') or []
    df               = df.copy()
    log              = []

    # Tentukan kolom yang dilindungi
    protected = set(user_exclude)
    if exclude_datetime:
        protected |= _detect_datetime_cols(df)

    to_drop = [c for c in df.columns if c not in protected and df[c].isna().mean() > threshold]

    if to_drop:
        df = df.drop(columns=to_drop)
        log.append(f'Dropped {len(to_drop)} kolom dengan missing >{threshold*100:.0f}%: {", ".join(to_drop)}')
        if protected:
            log.append(f'{len(protected)} kolom dilindungi (datetime/dikecualikan)')
    else:
        log.append(f'Tidak ada kolom dengan missing >{threshold*100:.0f}%.')
    label = f'Drop High-Missing Columns (>{threshold*100:.0f}%) — {len(to_drop)} kolom'
    return df, label, log


def _op_drop_col(df: pd.DataFrame, params: dict):
    col = params.get('column', '')
    df  = df.copy()
    if col and col in df.columns:
        df  = df.drop(columns=[col])
        log = [f'Dropped column: {col}']
    else:
        log = [f'Kolom "{col}" tidak ditemukan.']
    label = f'Drop Column: {col}'
    return df, label, log


def _op_empty_to_nan(df: pd.DataFrame, params: dict):
    df   = df.copy()
    cols = df.select_dtypes(include=['object', 'string']).columns.tolist()
    changed = 0
    for col in cols:
        before = df[col].isna().sum()
        df[col] = df[col].replace(r'^\s*$', np.nan, regex=True)
        after = df[col].isna().sum()
        changed += int(after - before)
    log = [f'{changed} empty string(s) → NaN'] if changed else ['Tidak ada empty string yang perlu dikonversi.']
    label = f'Empty Strings → NaN ({changed} sel)'
    return df, label, log


def _op_fix_inconsistencies(df: pd.DataFrame, params: dict):
    """
    Fix text inconsistencies: strip whitespace dan/atau normalisasi casing.
    params:
      method  : 'strip' | 'lower' | 'upper' | 'title'
      columns : list[str] opsional — kolom spesifik (default: semua kolom teks)
    """
    method  = params.get('method', 'strip')
    columns = params.get('columns') or []
    df      = df.copy()
    log     = []
    total_fixed = 0

    method_labels = {
        'strip' : 'Strip Whitespace',
        'lower' : 'Strip + Lowercase',
        'upper' : 'Strip + Uppercase',
        'title' : 'Strip + Title Case',
    }

    target_cols = [c for c in columns if c in df.columns] if columns else df.columns
    for col in target_cols:
        s = df[col]
        if not pd.api.types.is_object_dtype(s) and not pd.api.types.is_string_dtype(s):
            continue
        if s.dropna().map(lambda x: not isinstance(x, str)).any():
            continue
        s_orig = s.astype(str)
        mask_str = s.apply(lambda x: isinstance(x, str))
        if method == 'strip':
            df[col] = s.where(~mask_str, s[mask_str].str.strip())
        elif method == 'lower':
            df[col] = s.where(~mask_str, s[mask_str].str.strip().str.lower())
        elif method == 'upper':
            df[col] = s.where(~mask_str, s[mask_str].str.strip().str.upper())
        elif method == 'title':
            df[col] = s.where(~mask_str, s[mask_str].str.strip().str.title())
        changed = int((df[col].astype(str) != s_orig).sum())
        if changed:
            log.append(f'{col}: {changed} nilai diperbaiki ({method_labels.get(method, method)})')
            total_fixed += changed

    if not log:
        log.append('Tidak ada inkonsistensi teks yang ditemukan pada kolom yang dipilih.')
    label = f'Fix Inconsistencies ({method_labels.get(method, method)}) — {total_fixed} nilai diperbaiki'
    return df, label, log


def _is_datetime_column(series, sample_size=200):
    """
    Quick check if a column contains datetime values.
    Returns True if 40%+ of non-null values can be parsed as datetime.
    Skips obviously non-text columns for performance.
    """
    s = series.dropna()
    if s.empty:
        return False
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if not pd.api.types.is_object_dtype(series) and not pd.api.types.is_string_dtype(series):
        # Numeric epoch check — only if values are in plausible epoch range
        if pd.api.types.is_numeric_dtype(series):
            vmax = float(s.max())
            is_plausible = (1e8 < vmax < 2e10) or (1e11 < vmax < 2e13)
            if is_plausible:
                sample = s.head(sample_size)
                try:
                    parsed = pd.to_datetime(sample, unit='s', errors='coerce')
                    if parsed.notna().mean() >= 0.90:
                        return True
                except Exception:
                    pass
        return False
    sample = s.head(sample_size)
    try:
        parsed = pd.to_datetime(sample, errors='coerce')
        return parsed.notna().mean() >= 0.40
    except Exception:
        return False


def _detect_datetime_cols(df, sample_size=200):
    """Return set of column names that are likely datetime columns."""
    return {col for col in df.columns if _is_datetime_column(df[col], sample_size)}


def detect_irrelevant_cols(df: pd.DataFrame, threshold: float = 0.95) -> list:
    """
    Return a list of column names that are deemed irrelevant based on uniqueness threshold or zero variance.
    Also detects columns with zero variance (single unique value).
    Auto-skips datetime columns to prevent accidental removal of date columns.
    """
    relevant = set()
    total_rows = len(df)
    # Pre-detect datetime columns to protect them
    datetime_cols = _detect_datetime_cols(df)

    for col in df.columns:
        # Skip datetime columns — they are relevant for time-series analysis
        if col in datetime_cols:
            continue
        n_unique = df[col].nunique()
        # Numeric columns with meaningful variance are relevant
        if pd.api.types.is_numeric_dtype(df[col]) and n_unique > 1:
            relevant.add(col)
            continue
        # 1. Zero variance column (constant values)
        if n_unique <= 1:
            continue  # These will be added to irrelevant below
        # 2. High uniqueness ratio (likely ID/UUID/free text)
        unique_ratio = n_unique / max(total_rows, 1)
        if unique_ratio > threshold and n_unique > 50:
            continue  # These will be added to irrelevant below
        relevant.add(col)

    # Everything not in relevant AND not datetime is irrelevant
    irrelevant = [c for c in df.columns if c not in relevant and c not in datetime_cols]
    return irrelevant


def _op_drop_irrelevant_cols(df: pd.DataFrame, params: dict):
    """
    Drop kolom yang kemungkinan tidak relevan (ID / free text).
    params:
      columns   : list[str] kolom spesifik yang ingin di-drop (opsional)
      threshold : float 0-1, unique ratio threshold (default 0.95)
      exclude_columns : list[str] opsional — kolom yang TIDAK ikut di-drop
    """
    threshold      = float(params.get('threshold', 0.95))
    selected_cols  = params.get('columns') or []
    user_exclude   = params.get('exclude_columns') or []
    df  = df.copy()
    log = []

    # Lindungi datetime columns dari auto-detection
    datetime_cols = _detect_datetime_cols(df)

    if selected_cols:
        # User memilih kolom spesifik — tetap hormati exclude
        protected = set(datetime_cols) | set(user_exclude)
        to_drop = [c for c in selected_cols if c in df.columns and c not in protected]
    else:
        to_drop = [c for c in detect_irrelevant_cols(df, threshold) if c not in user_exclude]

    if to_drop:
        for col in to_drop:
            if col in df.columns:
                n_unique = df[col].nunique()
                if n_unique <= 1:
                    log.append(f"Kolom {col} dihapus karena variansi nol")
                else:
                    log.append(f"Kolom {col} dihapus karena tingkat keunikan tinggi")
        df = df.drop(columns=[c for c in to_drop if c in df.columns])
    else:
        log.append('Tidak ada kolom irrelevant yang terdeteksi untuk dihapus.')
    
    label = f'Drop Irrelevant Columns — {len(to_drop)} kolom dihapus'
    return df, label, log


def _op_convert_dtypes(df: pd.DataFrame, params: dict):
    """
    Auto-convert column data types: detect and parse datetime columns,
    and convert string-encoded numbers to proper numeric types.

    params:
      target : 'all' | 'datetime' | 'numeric' (default: 'all')
    """
    target = params.get('target', 'all')
    df     = df.copy()
    log    = []
    converted_cols = []

    text_cols = df.select_dtypes(include=['object', 'string']).columns

    for col in text_cols:
        non_null = df[col].dropna()
        if non_null.empty:
            continue

        sample = non_null.head(200)
        orig_dtype = df[col].dtype

        # ── Try datetime parsing ──────────────────────────────────────────────
        if target in ('all', 'datetime'):
            try:
                parsed = pd.to_datetime(sample, errors='coerce')
                if parsed.notna().mean() >= 0.40:
                    full_parsed = pd.to_datetime(df[col], errors='coerce')
                    df[col] = full_parsed
                    converted_cols.append(col)
                    log.append(f'{col}: converted to datetime')
                    continue
            except Exception:
                pass

        # ── Try numeric conversion ────────────────────────────────────────────
        if target in ('all', 'numeric'):
            numeric_count = 0
            for v in sample:
                try:
                    float(v)
                    numeric_count += 1
                except (ValueError, TypeError):
                    pass
            if numeric_count / max(len(sample), 1) >= 0.80:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                converted_cols.append(col)
                log.append(f'{col}: converted to numeric')

    label = f'Convert Dtypes — {len(converted_cols)} kolom dikonversi'
    if not log:
        log.append('Tidak ada kolom yang perlu dikonversi.')
    return df, label, log


def _has_dirty_numeric(sample):
    """
    Check if a string series contains 'dirty' numeric data:
    currency symbols, Rp/IDR, mixed thousand/decimal separators, % signs, etc.
    """
    count_dirty = 0
    count_total = 0
    for v in sample:
        if not isinstance(v, str):
            continue
        count_total += 1
        v_stripped = v.strip()
        if re.search(r'[^\d.,\-+%\s]', v_stripped):
            count_dirty += 1
        elif re.search(r'[.,].*[.,]', v_stripped) and not re.match(r'^-?\d+\.\d+$', v_stripped):
            count_dirty += 1
    return count_total > 0 and (count_dirty / max(count_total, 1)) >= 0.20


def _op_standardize_numeric(df: pd.DataFrame, params: dict):
    """
    Standardize columns with dirty numeric formatting (currency symbols,
    mixed thousand/decimal separators, etc.) to clean numeric dtype.

    params:
      columns : list[str] opsional — kolom spesifik (default: auto-detect)
      drop_failed : bool (default False) — jika True, nilai gagal parse jadi NaN
    """
    df          = df.copy()
    log         = []
    columns     = params.get('columns') or []
    drop_failed = params.get('drop_failed', False)
    converted   = 0

    text_cols = df.select_dtypes(include=['object', 'string']).columns
    target_cols = [c for c in columns if c in df.columns] if columns else text_cols

    for col in target_cols:
        s = df[col].dropna()
        if s.empty:
            continue
        if s.map(lambda x: not isinstance(x, str)).all():
            continue

        sample = s.head(200)
        if not _has_dirty_numeric(sample):
            continue

        cleaned = df[col].map(clean_and_parse_numeric)
        n_valid = cleaned.notna().sum()
        n_total = len(df[col].dropna())
        if n_valid / max(n_total, 1) < 0.50:
            continue

        df[col] = cleaned
        if drop_failed:
            pass
        converted += 1
        log.append(f'{col}: {n_valid}/{n_total} nilai berhasil dinormalisasi → numeric')

    label = f'Standardize Numeric — {converted} kolom dikonversi'
    if not log:
        log.append('Tidak ada kolom numeric kotor yang terdeteksi.')
    return df, label, log


# ── Boolean-like & categorical value standardization ──────────────────────────

# Common boolean-like variants in Indonesian/English contexts
_BOOL_MAP = {
    'y': 'Yes', 'yes': 'Yes', 'ya': 'Yes', 'yess': 'Yes', 'yeps': 'Yes', 'yup': 'Yes',
    'n': 'No', 'no': 'No', 't': 'No', 'tidak': 'No', 'nope': 'No', 'nggak': 'No',
    'true': 'Yes', 't': 'No', 'false': 'No',
    '1': 'Yes', '0': 'No',
}

def _standardize_bool_like(val):
    """Map boolean-like variants to canonical 'Yes'/'No'."""
    if not isinstance(val, str):
        return val
    v = val.strip().lower()
    return _BOOL_MAP.get(v, val)


def _op_standardize_categorical(df: pd.DataFrame, params: dict):
    """
    Standardize categorical text values:
      - Boolean-like values: Y/yes/Ya → Yes, N/no/Tidak → No
      - Strip whitespace & collapse multiple spaces
      - Optional: title-case for consistent capitalization

    params:
      columns    : list[str] opsional — kolom spesifik (default: auto-detect)
      bool_normalize : bool (default True) — normalize boolean-like variants
      normalize_case : str (default '') — '' | 'lower' | 'upper' | 'title'
    """
    df             = df.copy()
    log            = []
    columns        = params.get('columns') or []
    bool_normalize = params.get('bool_normalize', True)
    normalize_case = params.get('normalize_case', '')
    total_fixed    = 0

    text_cols = df.select_dtypes(include=['object', 'string']).columns
    target_cols = [c for c in columns if c in df.columns] if columns else text_cols

    for col in target_cols:
        s = df[col].dropna()
        if s.empty:
            continue
        if s.map(lambda x: not isinstance(x, str)).all():
            continue
        n_unique_before = s.nunique()

        s_orig = df[col].astype(str)

        # Step 1: strip whitespace
        df[col] = df[col].apply(
            lambda x: x.strip() if isinstance(x, str) else x
        )
        df[col] = df[col].replace(r'\s+', ' ', regex=True)

        # Step 2: boolean-like normalization
        if bool_normalize:
            df[col] = df[col].apply(_standardize_bool_like)

        # Step 3: case normalization
        if normalize_case == 'lower':
            df[col] = df[col].apply(
                lambda x: x.lower() if isinstance(x, str) else x
            )
        elif normalize_case == 'upper':
            df[col] = df[col].apply(
                lambda x: x.upper() if isinstance(x, str) else x
            )
        elif normalize_case == 'title':
            df[col] = df[col].apply(
                lambda x: x.title() if isinstance(x, str) else x
            )

        changed = int((df[col].astype(str) != s_orig).sum())
        if changed:
            n_unique_after = df[col].dropna().nunique() if df[col].notna().any() else 0
            log.append(
                f'{col}: {changed} nilai diperbaiki '
                f'(unique: {n_unique_before} → {n_unique_after})'
            )
            total_fixed += changed

    label = f'Standardize Categorical — {total_fixed} nilai diperbaiki'
    if not log:
        log.append('Tidak ada nilai kategorikal yang perlu distandarisasi.')
    return df, label, log


# ─── Quality Report ───────────────────────────────────────────────────────────

def get_quality_report(df: pd.DataFrame) -> dict:
    """
    Analisis kualitas dataset lengkap untuk Overview + Cleaning tab.
    Return dict dengan kunci:
      summary    : dict ringkasan global
      columns    : list[dict] per kolom
      warnings   : list[str] peringatan utama
    """
    total_rows  = len(df)
    total_cols  = len(df.columns)
    total_cells = df.size
    missing_cells   = int(df.isna().sum().sum())
    duplicate_rows  = int(df.duplicated().sum())
    missing_pct     = round(missing_cells / total_cells * 100, 2) if total_cells else 0

    # Inconsistencies: object cols dengan leading-trailing spaces atau mixed casing NYATA
    inconsistency_count = 0
    for col in df.select_dtypes(include=['object', 'string']).columns:
        s = df[col].dropna().astype(str)
        if s.empty:
            continue
        # Leading/trailing whitespace
        if (s != s.str.strip()).any():
            inconsistency_count += 1
        # True mixed casing: jika lowercasing mengurangi jumlah unique → ada varian casing
        elif s.nunique() > s.str.lower().nunique():
            inconsistency_count += 1

    # Outliers (IQR) global count
    total_outliers = 0
    for col in df.select_dtypes(include='number').columns:
        s = df[col].dropna()
        if len(s) < 4:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        total_outliers += int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())

    # Irrelevant columns: unique ratio > 0.95 (kemungkinan ID/free text) OR unique values <= 1 (constant)
    # Datetime and numeric columns are excluded — they are relevant for analysis
    datetime_cols = _detect_datetime_cols(df)
    irrelevant_count = 0
    for col in df.columns:
        if col in datetime_cols:
            continue
        n_unique = df[col].nunique()
        if pd.api.types.is_numeric_dtype(df[col]) and n_unique > 1:
            continue
        unique_ratio = n_unique / max(total_rows, 1)
        if (unique_ratio > 0.95 and n_unique > 50) or (n_unique <= 1):
            irrelevant_count += 1

    # Data types breakdown
    dtypes_summary = {}
    for col in df.columns:
        dtype_str = str(df[col].dtype)
        if 'int' in dtype_str or 'float' in dtype_str:
            key = 'numeric'
        elif 'object' in dtype_str or 'string' in dtype_str:
            key = 'text'
        elif 'datetime' in dtype_str:
            key = 'datetime'
        elif 'bool' in dtype_str:
            key = 'boolean'
        else:
            key = 'other'
        dtypes_summary[key] = dtypes_summary.get(key, 0) + 1

    # Warnings
    warnings = []
    if missing_pct > 5:
        warnings.append(f'{missing_cells} sel missing ({missing_pct}% dari total data)')
    if duplicate_rows > 0:
        warnings.append(f'{duplicate_rows} baris duplikat ditemukan')
    if total_outliers > 0:
        warnings.append(f'{total_outliers} outlier terdeteksi (metode IQR)')
    if inconsistency_count > 0:
        warnings.append(f'{inconsistency_count} kolom memiliki inkonsistensi format teks')
    if irrelevant_count > 0:
        warnings.append(f'{irrelevant_count} kolom kemungkinan tidak relevan (ID/free text)')

    needs_cleaning = bool(warnings)

    # Per-column detail
    columns_detail = []
    for col in df.columns:
        series   = df[col]
        missing  = int(series.isna().sum())
        miss_pct = round(missing / total_rows * 100, 2) if total_rows else 0
        unique   = int(series.nunique(dropna=True))

        issues = []
        if miss_pct > 50:
            issues.append('High missing (>50%)')
        elif miss_pct > 0:
            issues.append('Has missing values')
        if unique <= 1 and total_rows > 0:
            issues.append('Constant column')
        if pd.api.types.is_object_dtype(series.dtype):
            stripped = series.dropna().astype(str).str.strip()
            if (stripped == '').any():
                issues.append('Empty strings')
            if (series.dropna().astype(str) != series.dropna().astype(str).str.strip()).any():
                issues.append('Whitespace issues')

        # Outliers per numeric col (skip boolean — quantile fails on bool)
        col_outliers = 0
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            s = series.dropna()
            if len(s) >= 4:
                q1, q3 = s.quantile(0.25), s.quantile(0.75)
                iqr    = q3 - q1
                col_outliers = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
                if col_outliers > 0:
                    issues.append(f'{col_outliers} outliers')

        n_unique    = series.nunique()
        uniq_ratio  = n_unique / max(total_rows, 1)
        if uniq_ratio > 0.95 and n_unique > 50:
            # Skip datetime and numeric columns — they naturally have high cardinality
            if not _is_datetime_column(series) and not pd.api.types.is_numeric_dtype(series):
                issues.append('Possible ID/free text')

        columns_detail.append({
            'column'     : col,
            'dtype'      : str(series.dtype),
            'missing'    : missing,
            'missing_pct': miss_pct,
            'unique'     : unique,
            'outliers'   : col_outliers,
            'issues'     : ', '.join(issues) if issues else 'OK',
            'status'     : 'warning' if issues else 'ok',
        })

    return {
        'summary': {
            'total_rows'          : total_rows,
            'total_cols'          : total_cols,
            'missing_cells'       : missing_cells,
            'missing_pct'         : missing_pct,
            'duplicate_rows'      : duplicate_rows,
            'total_outliers'      : total_outliers,
            'inconsistency_count' : inconsistency_count,
            'irrelevant_count'    : irrelevant_count,
            'needs_cleaning'      : needs_cleaning,
            'dtypes'              : dtypes_summary,
        },
        'columns'  : columns_detail,
        'warnings' : warnings,
    }


def detect_data_status(df) -> str:
    """
    Auto-detect dataset cleanliness status. Returns one of two values:

      'raw'                 — Quality issues exist: missing values, duplicate rows,
                              irrelevant columns (ID/constant), text inconsistencies,
                              or statistical outliers (IQR method).
                              Dashboard visualizations are blocked.

      'clean'               — Fully clean: no missing, no duplicates, no irrelevant cols,
                              no inconsistencies, no outliers.
    """
    total_rows = len(df)
    if total_rows == 0:
        return 'clean'

    # ── Critical checks (block dashboard) ────────────────────────────────────
    missing_cells  = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    # Text inconsistencies: leading/trailing whitespace or mixed casing NYATA
    inconsistency_count = 0
    for col in df.select_dtypes(include=['object', 'string']).columns:
        s = df[col].dropna().astype(str)
        if s.empty:
            continue
        if (s != s.str.strip()).any():
            inconsistency_count += 1
        elif s.nunique() > s.str.lower().nunique():
            inconsistency_count += 1

    # Irrelevant columns: zero variance (constant) or near-unique ID columns
    # Datetime and numeric columns are excluded — they are relevant for analysis
    datetime_cols = _detect_datetime_cols(df)
    irrelevant_count = 0
    for col in df.columns:
        if col in datetime_cols:
            continue
        n_unique = df[col].nunique()
        if pd.api.types.is_numeric_dtype(df[col]) and n_unique > 1:
            continue
        unique_ratio = n_unique / max(total_rows, 1)
        if (n_unique <= 1) or (unique_ratio > 0.95 and n_unique > 50):
            irrelevant_count += 1

    has_critical = (
        missing_cells > 0
        or duplicate_rows > 0
        or inconsistency_count > 0
        or irrelevant_count > 0
    )

    if has_critical:
        return 'raw'

    # ── Soft check: outliers only (IQR method) ────────────────────────────────
    total_outliers = 0
    for col in df.select_dtypes(include='number').columns:
        s = df[col].dropna()
        if len(s) < 4:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        total_outliers += int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())

    if total_outliers > 0:
        return 'raw'

    return 'clean'
