"""
backend/time_series.py
Week 15 — Time Series Analytics (Auto Detection)

Fitur:
  - Auto-detect kolom datetime
  - Time Series Line Chart
  - Trend Line (OLS)
  - Moving Average (7, 30 hari atau adaptif)
  - Rolling Mean
  - Insight ringkasan (trend, seasonality, fluktuasi)
"""

import json
import re
import threading
import warnings
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats as scipy_stats

warnings.filterwarnings('ignore')

# ─── Thread-local theme controller ───────────────────────────────────────────
_thread_local = threading.local()


def set_theme(theme):
    _thread_local.theme = theme


def get_theme():
    return getattr(_thread_local, 'theme', 'dark')


TS_THEME = {
    'dark': {
        'paper_bgcolor': 'rgba(0,0,0,0)',
        'plot_bgcolor' : 'rgba(0,0,0,0)',
        'font_color'   : '#C8D8F0',
        'grid_color'   : 'rgba(180,190,220,0.15)',
        'axis_line'    : 'rgba(180,190,220,0.3)',
        'hover_bg'     : 'rgba(10,18,48,0.93)',
        'hover_border' : 'rgba(100,160,235,0.45)',
        'hover_font'   : '#e8f4fc',
    },
    'light': {
        'paper_bgcolor': '#FFFFFF',
        'plot_bgcolor' : '#FFFFFF',
        'font_color'   : '#1F2937',
        'grid_color'   : '#E5E7EB',
        'axis_line'    : '#E5E7EB',
        'hover_bg'     : 'rgba(255,255,255,0.93)',
        'hover_border' : 'rgba(0,0,0,0.12)',
        'hover_font'   : '#1F2937',
    },
}


def _cfg():
    return TS_THEME[get_theme()]


# ─── Palette ────────────────────────────────────────────────────────────────
COLORS = ['#4318ff', '#05cd99', '#ffce20', '#ee5d50', '#868cff', '#17a2b8']

def _layout(**kw):
    c = _cfg()
    base = dict(
        paper_bgcolor=c['paper_bgcolor'],
        plot_bgcolor =c['plot_bgcolor'],
        font         =dict(family='Inter, sans-serif', size=12, color=c['font_color']),
        margin       =dict(l=40, r=20, t=52, b=40),
        hoverlabel   =dict(bgcolor=c['hover_bg'],
                           bordercolor=c['hover_border'],
                           font=dict(color=c['hover_font'], size=13)),
        hovermode    ='x unified',
    )
    base.update(kw)
    return base


def _axis_style():
    c = _cfg()
    return dict(
        showgrid=True, gridcolor=c['grid_color'],
        zeroline=False, linecolor=c['axis_line'],
    )

def _safe_json(fig):
    from backend.viz_engine import decode_typed_arrays
    return decode_typed_arrays(json.loads(fig.to_json()))


# ════════════════════════════════════════════════════════════════════════════
# AUTO-DETECTION
# ════════════════════════════════════════════════════════════════════════════

def _try_parse_dates(sample, threshold=0.50):
    """
    Coba parsing datetime dengan format='mixed' untuk menangani format campuran.
    Mengembalikan (parsed_series, success_rate) atau (None, 0) jika gagal.
    """
    if sample is None or sample.empty:
        return None, 0
    try:
        parsed = pd.to_datetime(sample, errors='coerce', format='mixed')
        rate = parsed.notna().mean()
        if rate >= threshold and _plausible_dates(parsed):
            return parsed, rate
    except Exception:
        pass
    return None, 0


def _plausible_dates(parsed_series):
    """
    Validasi bahwa hasil parsing datetime bukan false positive.
    False positive: pd.to_datetime() menginterpretasi angka kecil
    (tahun, bulan, durasi) sebagai epoch → semua hasil jadi tahun 1970.
    """
    if parsed_series is None or parsed_series.empty:
        return False
    min_date = parsed_series.min()
    max_date = parsed_series.max()
    if min_date.year == 1970 and max_date.year == 1970:
        return False
    if (max_date - min_date).total_seconds() < 1:
        return False
    if max_date.year < 1900 or max_date.year > 2100:
        return False
    if min_date.year < 1900 or min_date.year > 2100:
        return False
    return True


def detect_datetime_cols(df):
    """
    Mendeteksi kolom datetime secara otomatis.
    Memeriksa tipe data asli dan mencoba parse kolom object/string.
    Mengembalikan list nama kolom datetime.
    """
    dt_cols = []

    # 1. Kolom yang sudah bertipe datetime
    for col in df.select_dtypes(include=['datetime64', 'datetimetz']).columns:
        dt_cols.append(col)

    # 2. Kolom object/string yang bisa di-parse sebagai datetime
    text_cols = df.select_dtypes(include=['object', 'string']).columns
    for col in text_cols:
        if col in dt_cols:
            continue
        sample = df[col].dropna().head(200)
        if sample.empty:
            continue
        parsed, rate = _try_parse_dates(sample, threshold=0.40)
        if parsed is not None and rate >= 0.40:
            dt_cols.append(col)

    # 3. Fallback: kolom dengan nama mengandung kata kunci datetime
    # NOTE: 'year', 'tahun', 'month', 'bulan', 'hari', 'day' tidak termasuk
    # karena kolom berisi komponen kalender (angka kecil) akan menjadi false positive.
    datetime_keywords = [
        'date', 'time', 'tanggal', 'waktu', 'tgl', 'dt_',
        'timestamp', 'datetime', 'created', 'updated',
        'periode', 'period', 'order_date', 'invoice', 'transaksi',
    ]
    for col in df.columns:
        if col in dt_cols:
            continue
        col_lower = col.lower().replace(' ', '_')
        if any(kw in col_lower for kw in datetime_keywords):
            sample = df[col].dropna().head(200)
            if sample.empty:
                continue
            parsed, rate = _try_parse_dates(sample, threshold=0.40)
            if parsed is not None and rate >= 0.40:
                dt_cols.append(col)

    # 4. Coba parse numerik timestamp (epoch seconds) — hanya nilai yang masuk akal
    # Skip kolom dengan nama yang jelas-jelas bukan timestamp
    non_epoch_keywords = [
        'price', 'sales', 'cost', 'amount', 'revenue', 'profit', 'harga',
        'penjualan', 'biaya', 'total', 'gross', 'net', 'discount', 'shipping',
        'quantity', 'qty', 'unit', 'rate', 'score', 'rating', 'fee', 'tax',
        'pajak', 'payment', 'charge', 'balance', 'saldo', 'fund', 'dana',
    ]
    financial_col_patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in non_epoch_keywords]

    for col in df.columns:
        if col in dt_cols:
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        if not pd.api.types.is_numeric_dtype(s):
            continue

        # Skip kolom yang namanya mengandung kata finansial/kuantitas
        col_lower = col.lower()
        if any(pat.search(col_lower) for pat in financial_col_patterns):
            continue

        vmax = float(s.max())
        vmin = float(s.min())

        # Pastikan nilai minimum juga masuk akal untuk epoch (bukan nol atau sangat kecil)
        is_seconds_epoch = (1e8 < vmin and vmax < 2e10)
        is_ms_epoch      = (1e11 < vmin and vmax < 2e13)

        if not (is_seconds_epoch or is_ms_epoch):
            continue

        sample = s.head(200)
        if is_seconds_epoch:
            try:
                parsed = pd.to_datetime(sample, unit='s', errors='coerce')
                if parsed.notna().mean() >= 0.90 and _plausible_dates(parsed):
                    dt_cols.append(col)
                    continue
            except Exception:
                pass
        if is_ms_epoch:
            try:
                parsed = pd.to_datetime(sample, unit='ms', errors='coerce')
                if parsed.notna().mean() >= 0.90 and _plausible_dates(parsed):
                    dt_cols.append(col)
            except Exception:
                pass

    return dt_cols


def validate_datetime_cols(df, dt_cols):
    """
    Validasi dan konversi kolom datetime dalam DataFrame.
    Mengembalikan (df_baru, dt_cols_valid, warning_list).
    """
    df = df.copy()
    valid = []
    warnings = []
    for col in dt_cols:
        if col not in df.columns:
            warnings.append(f"Kolom '{col}' tidak ditemukan.")
            continue
        try:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                valid.append(col)
                continue
            converted = pd.to_datetime(df[col], errors='coerce')
            n_total = len(converted)
            n_valid = int(converted.notna().sum())
            ratio = n_valid / max(n_total, 1)
            if ratio >= 0.50:
                df[col] = converted
                valid.append(col)
                if ratio < 0.90:
                    warnings.append(f"Kolom '{col}': {n_total - n_valid} dari {n_total} nilai tidak bisa di-parse sebagai datetime.")
            else:
                warnings.append(f"Kolom '{col}' diabaikan: hanya {ratio:.0%} nilai yang valid sebagai datetime (threshold 50%).")
        except Exception as e:
            warnings.append(f"Kolom '{col}' gagal dikonversi: {e}")
    return df, valid, warnings


def prepare_ts(df, dt_col, num_col):
    """
    Menyiapkan DataFrame time-series yang sudah diurutkan dan di-resample jika perlu.
    Mengembalikan (ts_df, freq_label).
    """
    if dt_col not in df.columns or num_col not in df.columns:
        return pd.DataFrame(), 'original'

    temp = df[[dt_col, num_col]].copy()
    temp[dt_col] = pd.to_datetime(temp[dt_col], errors='coerce')

    # Validasi: pastikan hasil parsing datetime masuk akal
    valid_dates = temp[dt_col].dropna()
    if len(valid_dates) >= 2:
        min_d, max_d = valid_dates.min(), valid_dates.max()
        if min_d.year == 1970 and max_d.year == 1970:
            # False positive — kolom bukan datetime sebenarnya
            return pd.DataFrame(), 'original'
        if (max_d - min_d).total_seconds() < 1:
            return pd.DataFrame(), 'original'

    temp = temp.dropna(subset=[dt_col, num_col]).sort_values(dt_col)

    # Hitung rata-rata rentang waktu
    if len(temp) < 2:
        return temp.rename(columns={dt_col: 'ds', num_col: 'y'}), 'original'

    diffs   = temp[dt_col].diff().dropna()
    med_sec = diffs.median().total_seconds()

    # Pilih frekuensi resample adaptif
    if med_sec <= 3600:          # < 1 jam → hourly
        freq, label = 'H', 'Hourly'
    elif med_sec <= 86400:       # < 1 hari → daily
        freq, label = 'D', 'Daily'
    elif med_sec <= 86400 * 7:   # < 1 minggu → weekly
        freq, label = 'W', 'Weekly'
    elif med_sec <= 86400 * 31:  # < 1 bulan → monthly
        freq, label = 'ME', 'Monthly'
    else:
        freq, label = 'YE', 'Yearly'

    try:
        ts = temp.set_index(dt_col)[num_col].resample(freq).mean().dropna().reset_index()
        ts.columns = ['ds', 'y']
    except Exception:
        ts = temp.rename(columns={dt_col: 'ds', num_col: 'y'})

    return ts, label


def _moving_window(n):
    """Pilih ukuran window moving average yang wajar berdasarkan panjang data."""
    if n >= 365: return 30
    if n >= 90:  return 7
    if n >= 30:  return 5
    return max(2, n // 5)


# ════════════════════════════════════════════════════════════════════════════
# CHART GENERATORS
# ════════════════════════════════════════════════════════════════════════════

def ts_line_chart(ts, dt_col_name, num_col_name, freq_label):
    """Time Series Line Chart utama."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ts['ds'], y=ts['y'],
        mode='lines', name=num_col_name,
        line=dict(color=COLORS[0], width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>' + num_col_name + ': %{y:,.2f}<extra></extra>',
    ))
    fig.update_layout(_layout(
        title=f' Time Series — {num_col_name} ({freq_label})',
        xaxis=dict(**_axis_style(), title=dt_col_name, rangeslider=dict(visible=True), type='date'),
        yaxis=dict(**_axis_style(), title=num_col_name),
    ))
    return _safe_json(fig)


def ts_trend_line(ts, num_col_name, freq_label):
    """Time Series + OLS Trend Line."""
    x_num = np.arange(len(ts))
    slope, intercept, r, p, _ = scipy_stats.linregress(x_num, ts['y'])
    trend = slope * x_num + intercept
    direction = '↑ Upward' if slope > 0 else '↓ Downward'

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ts['ds'], y=ts['y'],
        mode='lines', name='Actual',
        line=dict(color=COLORS[0], width=2), opacity=0.8,
        hovertemplate='%{x|%Y-%m-%d}<br>Actual: %{y:,.2f}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=ts['ds'], y=trend,
        mode='lines', name=f'Trend (R²={r**2:.3f})',
        line=dict(color=COLORS[3], width=2.5, dash='dash'),
        hovertemplate='%{x|%Y-%m-%d}<br>Trend: %{y:,.2f}<extra></extra>',
    ))
    fig.update_layout(_layout(
        title=f' Trend Line — {num_col_name} | {direction} | R²={r**2:.3f}',
        xaxis=dict(**_axis_style(), title='Date', type='date'),
        yaxis=dict(**_axis_style(), title=num_col_name),
    ))
    return _safe_json(fig)


def ts_moving_average(ts, num_col_name, freq_label):
    """Time Series + Moving Average overlay."""
    window = _moving_window(len(ts))
    ma = ts['y'].rolling(window, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ts['ds'], y=ts['y'],
        mode='lines', name='Actual',
        line=dict(color=COLORS[0], width=1.5), opacity=0.6,
        hovertemplate='%{x|%Y-%m-%d}<br>Actual: %{y:,.2f}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=ts['ds'], y=ma,
        mode='lines', name=f'MA({window})',
        line=dict(color=COLORS[1], width=2.5),
        hovertemplate='%{x|%Y-%m-%d}<br>MA(' + str(window) + '): %{y:,.2f}<extra></extra>',
    ))
    fig.update_layout(_layout(
        title=f' Moving Average (window={window}) — {num_col_name}',
        xaxis=dict(**_axis_style(), title='Date', type='date'),
        yaxis=dict(**_axis_style(), title=num_col_name),
    ))
    return _safe_json(fig)


def ts_rolling_mean(ts, num_col_name):
    """Rolling Mean dengan beberapa window berbeda."""
    windows = [_moving_window(len(ts)), _moving_window(len(ts)) * 3]
    windows = [w for w in windows if w < len(ts)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ts['ds'], y=ts['y'],
        mode='lines', name='Actual',
        line=dict(color=COLORS[0], width=1.5), opacity=0.5,
        hovertemplate='%{x|%Y-%m-%d}<br>Actual: %{y:,.2f}<extra></extra>',
    ))
    for i, w in enumerate(windows):
        rm = ts['y'].rolling(w, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=ts['ds'], y=rm,
            mode='lines', name=f'Rolling Mean ({w})',
            line=dict(color=COLORS[i + 1], width=2.5),
            hovertemplate='%{x|%Y-%m-%d}<br>RM(' + str(w) + '): %{y:,.2f}<extra></extra>',
        ))
    fig.update_layout(_layout(
        title=f' Rolling Mean — {num_col_name}',
        xaxis=dict(**_axis_style(), title='Date', type='date'),
        yaxis=dict(**_axis_style(), title=num_col_name),
    ))
    return _safe_json(fig)


def ts_overview_panel(ts, num_col_name, freq_label):
    """Panel 4-in-1: line, trend, MA, rolling std (volatility)."""
    window = _moving_window(len(ts))
    ma     = ts['y'].rolling(window, min_periods=1).mean()
    rs     = ts['y'].rolling(window, min_periods=1).std().fillna(0)
    x_num  = np.arange(len(ts))
    slope, intercept, _, _, _ = scipy_stats.linregress(x_num, ts['y'])
    trend  = slope * x_num + intercept

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            f'Line Chart — {num_col_name}',
            f'Trend Line (OLS)',
            f'Moving Average (window={window})',
            'Rolling Volatility (Std)',
        ],
        shared_xaxes=False,
    )

    kw = dict(x=ts['ds'], mode='lines')

    # Row 1 col 1 — Line
    fig.add_trace(go.Scatter(**kw, y=ts['y'],    name='Actual', line=dict(color=COLORS[0], width=1.8)), row=1, col=1)
    # Row 1 col 2 — Trend
    fig.add_trace(go.Scatter(**kw, y=ts['y'],    name='Actual', line=dict(color=COLORS[0], width=1.5), opacity=0.6, showlegend=False), row=1, col=2)
    fig.add_trace(go.Scatter(**kw, y=trend,      name='Trend',  line=dict(color=COLORS[3], width=2, dash='dash')), row=1, col=2)
    # Row 2 col 1 — MA
    fig.add_trace(go.Scatter(**kw, y=ts['y'],    name='Actual', line=dict(color=COLORS[0], width=1.2), opacity=0.4, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(**kw, y=ma,         name=f'MA({window})', line=dict(color=COLORS[1], width=2.2)), row=2, col=1)
    # Row 2 col 2 — Rolling Std
    fig.add_trace(go.Scatter(**kw, y=rs, fill='tozeroy', name='Rolling Std',
                             fillcolor='rgba(134,140,255,0.15)', line=dict(color=COLORS[4], width=1.8)), row=2, col=2)

    fig.update_layout(_layout(
        title=f' Time Series Overview — {num_col_name} ({freq_label})',
        height=520, showlegend=True,
    ))
    fig.update_xaxes(**_axis_style())
    fig.update_yaxes(**_axis_style())
    return _safe_json(fig)


# ════════════════════════════════════════════════════════════════════════════
# INSIGHT GENERATOR
# ════════════════════════════════════════════════════════════════════════════

def ts_insights(ts, num_col_name, dt_col_name, freq_label):
    """
    Menghasilkan ringkasan insight time series dengan kerangka O-A-I:
    - Trend (naik/turun/flat)
    - Seasonality (deteksi kasar via korelasi lag)
    - Fluktuasi (CV)
    - Nilai max & min beserta tanggalnya
    """
    insights = []
    y = ts['y'].values
    n = len(y)

    if n < 4:
        return [{
            'type': 'warning', 'icon': 'fa-clock',
            'title': 'Time Series Too Short',
            'desc': f'Kolom waktu {dt_col_name} terdeteksi namun data terlalu sedikit untuk analisis mendalam.',
            'observation': f'Data deret waktu {num_col_name} hanya memiliki {n} titik pengamatan.',
            'analysis': 'Jumlah titik data kurang dari 4 sehingga analisis tren dan musiman tidak dapat dilakukan secara statistik.',
            'implication': 'Kumpulkan lebih banyak data atau gunakan pendekatan kualitatif. Model time series memerlukan minimal 4 titik untuk regresi linier sederhana.',
        }]

    # ── Trend ────────────────────────────────────────────────────────────────
    x_num = np.arange(n)
    slope, _, r, p, _ = scipy_stats.linregress(x_num, y)
    direction = 'Meningkat (Upward) ↑' if slope > 0 else 'Menurun (Downward) ↓'
    dir_lower = 'meningkat' if slope > 0 else 'menurun'
    sig = 'signifikan secara statistik (p<0.05)' if p < 0.05 else 'belum signifikan (p≥0.05)'
    sig_label = 'signifikan' if p < 0.05 else 'belum signifikan'
    r2 = r ** 2
    obs_trend = (f'Variabel {num_col_name} menunjukkan tren {dir_lower} dengan slope={slope:.4f} '
                 f'per periode ({freq_label}), R²={r2:.3f}, p={p:.4f}.')
    ana_trend = (f'Tren yang {sig_label} ini mengindikasikan pola pergerakan {dir_lower} '
                 f'yang {"dapat diandalkan" if p < 0.05 else "masih perlu dikonfirmasi dengan data tambahan"} '
                 f'dalam periode pengamatan. '
                 f'R² sebesar {r2:.3f} berarti model linier menjelaskan {r2*100:.1f}% variasi data.')
    imp_trend = (f'{"Gunakan model peramalan yang menangani tren (SARIMA, Prophet) untuk prediksi ke depan." if abs(slope) > 0.001 else "Data relatif stasioner — gunakan model sederhana seperti rata-rata bergerak."} '
                 f'{"Nilai p<0.05 mengonfirmasi bahwa tren dapat digunakan sebagai dasar pengambilan keputusan." if p < 0.05 else "Tren belum cukup kuat — pertimbangkan analisis lebih lanjut dengan data periode tambahan."}')
    insights.append({
        'type': 'primary', 'icon': 'fa-chart-line',
        'title': f'Trend: {direction}',
        'desc': (f'Variabel {num_col_name} menunjukkan tren {direction.lower()} '
                 f'dengan slope={slope:.4f} per periode ({freq_label}). '
                 f'R²={r2:.3f} — tren {sig}.'),
        'observation': obs_trend,
        'analysis': ana_trend,
        'implication': imp_trend,
    })

    # ── Fluktuasi / Volatilitas ───────────────────────────────────────────────
    cv = (np.std(y) / np.mean(y) * 100) if np.mean(y) != 0 else 0
    vol_level = 'Tinggi (CV>30%)' if cv > 30 else ('Sedang (CV 10–30%)' if cv > 10 else 'Rendah (CV<10%)')
    vol_lower = 'tinggi' if cv > 30 else ('sedang' if cv > 10 else 'rendah')
    obs_vol = f'Koefisien variasi (CV) = {cv:.1f}% — masuk kategori volatilitas {vol_lower}.'
    ana_vol = (f'Volatilitas {vol_lower} mengindikasikan tingkat fluktuasi '
               f'{"yang signifikan dan perlu diwaspadai" if cv > 30 else "yang masih dalam batas wajar"} '
               f'pada {num_col_name} selama periode pengamatan.')
    imp_vol = (f'{"Pertimbangkan transformasi Box-Cox atau penstabil varians sebelum pemodelan parametrik. Model tree-based lebih robust terhadap volatilitas tinggi." if cv > 30 else "Model parametrik standar dapat digunakan tanpa transformasi khusus."} '
               f'{"Volatilitas tinggi juga mengindikasikan perlunya diversifikasi risiko dalam konteks bisnis." if cv > 30 else ""}')
    insights.append({
        'type': 'warning' if cv > 30 else 'success', 'icon': 'fa-wave-square',
        'title': f'Volatilitas: {vol_level}',
        'desc': (f'Koefisien variasi (CV) = {cv:.1f}%. '
                 f'Nilai ini menunjukkan tingkat fluktuasi yang {vol_level.lower()} '
                 f'pada {num_col_name} sepanjang periode waktu.'),
        'observation': obs_vol,
        'analysis': ana_vol,
        'implication': imp_vol,
    })

    # ── Max & Min ─────────────────────────────────────────────────────────────
    idx_max = ts['y'].idxmax()
    idx_min = ts['y'].idxmin()
    date_max = str(ts.loc[idx_max, 'ds'])[:10]
    date_min = str(ts.loc[idx_min, 'ds'])[:10]
    val_max  = ts.loc[idx_max, 'y']
    val_min  = ts.loc[idx_min, 'y']
    range_val = val_max - val_min
    obs_range = (f'Nilai tertinggi {num_col_name}: {val_max:,.2f} pada {date_max}. '
                 f'Nilai terendah: {val_min:,.2f} pada {date_min}. '
                 f'Rentang (range): {range_val:,.2f}.')
    ana_range = (f'Peak pada {date_max} dan trough pada {date_min} memberikan gambaran '
                 f'batas atas dan bawah historis variabel {num_col_name}. '
                 f'Selisih sebesar {range_val:,.2f} menunjukkan fluktuasi nilai '
                 f'{"yang lebar" if range_val > abs(np.mean(y)) * 1.5 else "yang moderat"} sepanjang periode.')
    imp_range = (f'Identifikasi faktor-faktor yang memengaruhi nilai ekstrem untuk mitigasi risiko. '
                 f'Gunakan batas ini sebagai referensi untuk penetapan threshold atau target bisnis.')
    insights.append({
        'type': 'info', 'icon': 'fa-calendar-check',
        'title': f'Peak & Trough — {num_col_name}',
        'desc': (f'Nilai tertinggi: {val_max:,.2f} pada {date_max}. '
                 f'Nilai terendah: {val_min:,.2f} pada {date_min}. '
                 f'Range: {range_val:,.2f}.'),
        'observation': obs_range,
        'analysis': ana_range,
        'implication': imp_range,
    })

    # ── Seasonality (autocorrelation lag) ─────────────────────────────────────
    if n >= 14:
        lags  = [7, 12, 30]
        found = []
        for lag in lags:
            if lag >= n:
                continue
            corr = np.corrcoef(y[:-lag], y[lag:])[0, 1]
            if abs(corr) > 0.40:
                found.append(f'lag={lag} (r={corr:.2f})')
        if found:
            found_str = ', '.join(found)
            obs_season = (f'Autocorrelation signifikan terdeteksi pada: {found_str}. '
                          f'Ini mengindikasikan pola berulang pada {num_col_name}.')
            ana_season = (f'Pola musiman yang terdeteksi menunjukkan bahwa nilai {num_col_name} '
                          f'dipengaruhi oleh siklus waktu tertentu. '
                          f'Korelasi lag positif mengindikasikan pengaruh periode sebelumnya terhadap nilai saat ini.')
            imp_season = (f'Gunakan model yang menangani komponen musiman seperti SARIMA atau Prophet '
                          f'untuk peramalan yang akurat. Pastikan frekuensi data sesuai dengan periode musiman '
                          f'yang terdeteksi untuk menghindari aliasing.')
            insights.append({
                'type': 'success', 'icon': 'fa-redo',
                'title': 'Pola Musiman (Seasonality) Terdeteksi',
                'desc': f'Autocorrelation tinggi ditemukan pada: {found_str}. '
                        f'Ini mengindikasikan adanya pola berulang pada {num_col_name}.',
                'observation': obs_season,
                'analysis': ana_season,
                'implication': imp_season,
            })
        else:
            obs_noseason = (f'Tidak ditemukan autocorrelation signifikan pada lag standar (7, 12, 30). '
                            f'Data {num_col_name} tampak tidak memiliki pola musiman yang kuat.')
            ana_noseason = (f'Tidak adanya korelasi lag yang signifikan mengindikasikan bahwa '
                            f'nilai {num_col_name} pada suatu periode tidak bergantung kuat pada nilai '
                            f'periode sebelumnya dalam siklus mingguan, bulanan, atau tahunan.')
            imp_noseason = (f'Model time series tanpa komponen musiman (ARIMA, simple exponential smoothing) '
                            f'sudah memadai. Jika diperlukan, lakukan uji stasionaritas (ADF test) untuk '
                            f'menentukan pendekatan differencing yang tepat.')
            insights.append({
                'type': 'muted', 'icon': 'fa-minus-circle',
                'title': 'Tidak Ada Pola Musiman Jelas',
                'desc': (f'Tidak ditemukan autocorrelation signifikan pada lag standar (7, 12, 30). '
                         f'Data {num_col_name} tampak tidak memiliki pola musiman yang kuat.'),
                'observation': obs_noseason,
                'analysis': ana_noseason,
                'implication': imp_noseason,
            })

    return insights


# ════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def generate_ts_plots(df, dt_cols, num_cols, theme='dark',
                      dt_col=None, num_col=None):
    """
    Menghasilkan semua plot & insight time series.

    Parameters
    ----------
    df       : DataFrame lengkap
    dt_cols  : list kolom datetime (dari detect_datetime_cols)
    num_cols : list kolom numerik
    theme    : 'dark' atau 'light'
    dt_col   : optional — datetime column override (else uses dt_cols[0])
    num_col  : optional — numeric column override (else uses num_cols[0])

    Returns
    -------
    ts_plots    : dict { key: plotly_json }
    ts_insights_list : list insight dicts
    ts_meta     : dict { dt_col, num_col, freq_label, n_points }
    """
    set_theme(theme)
    ts_plots         = {}
    ts_insights_list = []
    ts_meta          = {}

    if not dt_cols or not num_cols:
        return ts_plots, ts_insights_list, ts_meta

    dt_col  = dt_col or dt_cols[0]
    num_col = num_col or num_cols[0]

    ts, freq_label = prepare_ts(df, dt_col, num_col)

    if len(ts) < 4:
        return ts_plots, ts_insights_list, ts_meta

    ts_meta = {
        'dt_col'     : dt_col,
        'num_col'    : num_col,
        'freq_label' : freq_label,
        'n_points'   : len(ts),
        'date_start' : str(ts['ds'].min())[:10],
        'date_end'   : str(ts['ds'].max())[:10],
    }

    def _try(key, fn, *args):
        try:
            result = fn(*args)
            if result:
                ts_plots[key] = result
        except Exception as e:
            print(f"[time_series] Skipping '{key}': {e}")

    _try('ts_line',    ts_line_chart,    ts, dt_col, num_col, freq_label)
    _try('ts_trend',   ts_trend_line,    ts, num_col, freq_label)
    _try('ts_ma',      ts_moving_average,ts, num_col, freq_label)
    _try('ts_rolling', ts_rolling_mean,  ts, num_col)
    _try('ts_overview',ts_overview_panel,ts, num_col, freq_label)

    ts_insights_list = ts_insights(ts, num_col, dt_col, freq_label)

    return ts_plots, ts_insights_list, ts_meta