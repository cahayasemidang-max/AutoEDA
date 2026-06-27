"""
backend/dashboard_overview.py
Dashboard Overview — KPI cards + grid visualisasi.

SLOT RULES (tidak ada chart duplikat, semua slot punya toggle):
  ov_hbar        → Pareto Chart            (cat_cols >= 1, toggle cat_cols)   ← ganti Count Plot
  ov_center      → Pie/Donut Chart         (cat_cols >= 1, toggle cat_cols)
  ov_top_right   → TS line / Scatter       (dt+num → TS tanpa toggle;
                                            num>=2 → Scatter dengan toggle X & Y)
  ov_vbar_left   → Histogram per num_col   (num_cols >= 1, toggle num_cols)
  ov_area_bottom → Boxplot per num_col     (num_cols >= 1, toggle num_cols)
  ov_vbar_right  → Bar Chart per cat_col   (cat_cols >= 1, toggle cat_cols)
"""

import numpy as np
import pandas as pd

from backend.data_sanitizer import sanitize_series, safe_iqr_outliers
from backend.viz_engine import (
    _chart_bar,
    _chart_pareto,
    _chart_histogram,
    _chart_boxplot,
    _chart_pie,
    _chart_scatter,
    _json,
    _axes,
    _layout,
    _to_list,
    PALETTE,
    PLOT_BG,
)
import plotly.graph_objects as go


# ─── helpers ─────────────────────────────────────────────────────────────────

def _fmt_num(val, decimals=2):
    try:
        f = float(val)
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:,.2f}M"
        if abs(f) >= 1_000:
            return f"{f:,.{decimals}f}"
        return round(f, decimals)
    except (TypeError, ValueError):
        return "N/A"


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[overview] chart error in {fn.__name__}: {e}")
        return None


# ─── Insight helpers for viz-engine slots ───────────────────────────────────

def _num_insights(s):
    if s.empty:
        return []
    return [
        {'icon': 'fa-calculator', 'text': f'Mean: {_fmt_num(s.mean())}'},
        {'icon': 'fa-arrows-h',   'text': f'Range: {_fmt_num(s.min())} — {_fmt_num(s.max())}'},
    ]

def _cat_insights(series):
    if series.empty:
        return []
    vc = series.value_counts()
    top = vc.index[0]
    pct = vc.iloc[0] / len(series) * 100
    return [
        {'icon': 'fa-tag',        'text': f'Top: {top} ({vc.iloc[0]}, {pct:.0f}%)'},
        {'icon': 'fa-layer-group','text': f'Unique: {len(vc)} categories'},
    ]

def _ts_insights(s):
    if s.empty:
        return []
    return [
        {'icon': 'fa-chart-line', 'text': f'Mean: {_fmt_num(s.mean())}'},
        {'icon': 'fa-arrow-up',   'text': f'Max: {_fmt_num(s.max())}'},
    ]

def _pair_insights(df, cx, cy):
    sx = sanitize_series(df[cx], cx)
    sy = sanitize_series(df[cy], cy)
    if sx.empty or sy.empty:
        return []
    corr = sx.corr(sy) if len(sx) > 1 and len(sy) > 1 else 0
    return [
        {'icon': 'fa-circle-dot',    'text': f'Correlation: {corr:.2f}'},
        {'icon': 'fa-arrows-h',      'text': f'{cx}: {_fmt_num(sx.mean())}  |  {cy}: {_fmt_num(sy.mean())}'},
    ]


# ─── KPI builder ─────────────────────────────────────────────────────────────

_EXEC_KEYWORDS = {
    'revenue' : ('fa-dollar-sign',  'Total Revenue'),
    'income'  : ('fa-dollar-sign',  'Total Income'),
    'profit'  : ('fa-chart-line',   'Total Profit'),
    'sales'   : ('fa-shopping-cart','Total Sales'),
    'amount'  : ('fa-coins',        'Total Amount'),
    'spend'   : ('fa-credit-card',  'Total Spend'),
    'expense' : ('fa-file-invoice-dollar', 'Total Expense'),
    'salary'  : ('fa-money-bill-wave', 'Total Salary'),
    'budget'  : ('fa-calculator',   'Total Budget'),
    'gmv'     : ('fa-chart-simple', 'Total GMV'),
    'quantity': ('fa-cubes',        'Total Quantity'),
    'qty'     : ('fa-cubes',        'Total Qty'),
    'price'   : ('fa-tag',          'Avg Price'),
    'cost'    : ('fa-receipt',      'Total Cost'),
    'fee'     : ('fa-hand-holding-dollar','Total Fee'),
    'discount': ('fa-percentage',   'Total Discount'),
    'tax'     : ('fa-receipt',      'Total Tax'),
    'value'   : ('fa-chart-pie',    'Total Value'),
    'count'   : ('fa-hashtag',      'Total Count'),
    'rating'  : ('fa-star',         'Avg Rating'),
    'score'   : ('fa-bullseye',     'Avg Score'),
    'age'     : ('fa-clock',        'Avg Age'),
    'year'    : ('fa-calendar',     'Avg Year'),
}

def _detect_exec_col(col):
    """Return (icon, label_prefix) if col name matches an exec keyword."""
    cl = col.lower().replace('_', ' ').replace('-', ' ')
    for kw, (icon, label) in _EXEC_KEYWORDS.items():
        if kw in cl:
            return icon, label
    return None, None

def build_overview_kpis(df, num_cols, cat_cols, metrics):
    kpis = []

    # 1. Executive-friendly numeric columns — weighted by keyword match
    exec_matches = []
    other_nums   = []
    for col in num_cols:
        icon, label = _detect_exec_col(col)
        if icon:
            exec_matches.append((col, icon, label))
            continue
        other_nums.append(col)

    # Show matched exec columns first (up to 3), with smart aggregation
    shown_exec = set()
    for col, icon, label in exec_matches[:3]:
        if col in shown_exec:
            continue
        shown_exec.add(col)
        s = sanitize_series(df[col], col)
        if s.empty:
            continue
        # Sum for total-like, mean for rate/avg-like
        if any(kw in col.lower() for kw in ('rate','ratio','pct','avg','mean','index','price','rating','score','age','year')):
            val = _fmt_num(s.mean())
        else:
            val = _fmt_num(s.sum())
        kpis.append({
            'id': f'exec_{col}',
            'label': label,
            'value': val,
            'icon': icon,
            'color': 'blue',
        })

    # 2. Row count
    kpis.append({
        'id': 'rows',
        'label': 'Total Records',
        'value': metrics.get('total_rows', f'{len(df):,}'),
        'icon': 'fa-database',
        'color': 'green',
    })

    # 3. If no exec matches and we have other num cols, show avg of first
    if not exec_matches and other_nums:
        col = other_nums[0]
        s   = sanitize_series(df[col], col)
        kpis.append({
            'id': f'avg_{col}',
            'label': f'Avg — {col}',
            'value': _fmt_num(s.mean()) if not s.empty else 'N/A',
            'icon': 'fa-chart-line',
            'color': 'orange',
        })

    # 4. Missing ratio (data quality signal)
    kpis.append({
        'id': 'missing',
        'label': 'Missing Ratio',
        'value': metrics.get('missing_pct', '0%'),
        'icon': 'fa-exclamation-circle',
        'color': 'red',
    })

    # 5. Fill remaining slot if possible
    remaining = 5 - len(kpis)
    if remaining > 0 and len(cat_cols) > 0:
        col = cat_cols[0]
        kpis.append({
            'id': 'top_cat',
            'label': f'Top — {col}',
            'value': df[col].value_counts().index[0] if not df[col].empty else 'N/A',
            'icon': 'fa-trophy',
            'color': 'purple',
        })
    elif remaining > 0 and other_nums and len(other_nums) > 1:
        col = other_nums[1]
        s   = sanitize_series(df[col], col)
        kpis.append({
            'id': f'sum_{col}',
            'label': f'Total — {col}',
            'value': _fmt_num(s.sum()) if not s.empty else 'N/A',
            'icon': 'fa-calculator',
            'color': 'blue',
        })

    return kpis[:5]


# ─── Stats preview builder ────────────────────────────────────────────────────

def build_stats_preview(df, num_cols, cat_cols):
    num_rows = []
    for col in num_cols[:8]:
        try:
            # Sanitize: force numeric conversion, drop NaN
            s = sanitize_series(df[col] if col in df.columns else pd.Series(dtype=float), col)
            if s.empty:
                continue

            # IQR outlier detection — safe subtraction
            outliers = 0
            iqr_result = safe_iqr_outliers(s)
            if iqr_result is not None:
                _, _, _, outliers = iqr_result

            num_rows.append({
                'col':      col,
                'mean':     round(float(s.mean()), 3),
                'median':   round(float(s.median()), 3),
                'std':      round(float(s.std()), 3) if len(s) >= 2 else 0.0,
                'min':      round(float(s.min()), 3),
                'max':      round(float(s.max()), 3),
                'outliers': outliers,
                'missing':  int(df[col].isna().sum()) if col in df.columns else 0,
            })
        except Exception as exc:
            print(f"[overview] stats_preview num col '{col}' error: {exc}")

    cat_rows = []
    for col in cat_cols[:6]:
        s = df[col].dropna()
        if s.empty:
            continue
        vc = s.value_counts()
        mode_val = str(vc.index[0]) if not vc.empty else 'N/A'
        mode_pct = round(vc.iloc[0] / len(s) * 100, 1) if not vc.empty else 0
        cat_rows.append({
            'col':      col,
            'unique':   int(s.nunique()),
            'mode':     mode_val[:30],
            'mode_pct': mode_pct,
            'missing':  int(df[col].isna().sum()),
        })

    return {'num': num_rows, 'cat': cat_rows}


# ─── Chart builders ──────────────────────────────────────────────────────────

def _build_pareto_charts(df, cat_cols):
    """
    Pareto Chart per kolom kategorik (toggle semua cat_cols).
    Identik dengan Visualizations > Categorical > Pareto Chart.
    Unik: menampilkan bar frekuensi + garis kumulatif 80/20.
    BERBEDA dari ov_center (Pie) dan ov_vbar_right (Bar Chart).
    Return: dict {col_name: chart_json}
    """
    if not cat_cols:
        return {}
    result = {}
    for col in cat_cols[:6]:
        chart = _safe(_chart_pareto, df, col)
        if chart:
            result[col] = chart
    return result


def _build_pie_charts(df, cat_cols):
    """
    Pie/Donut Chart per kolom kategorik (toggle semua cat_cols).
    Identik dengan Visualizations > Categorical > Donut / Pie Chart.
    Return: dict {col_name: chart_json}
    """
    if not cat_cols:
        return {}
    result = {}
    for col in cat_cols[:6]:
        chart = _safe(_chart_pie, df, col)
        if chart:
            result[col] = chart
    return result


def _build_scatter_charts(df, num_cols):
    """
    Scatter Plot dengan pasangan kolom X dan Y (toggle independent).
    Identik dengan Visualizations > Bivariate > Scatter Plot.
    Return: dict of dict { col_x: { col_y: chart_json } }
    Digunakan saat tidak ada dt_cols (fallback dari TS).
    """
    if len(num_cols) < 2:
        return {}
    result = {}
    cols = num_cols[:6]
    for i, cx in enumerate(cols):
        result[cx] = {}
        for j, cy in enumerate(cols):
            if cx == cy:
                continue
            chart = _safe(_chart_scatter, df, cx, cy)
            if chart:
                result[cx][cy] = chart
    return result


def _build_top_right_ts(df, num_cols, dt_cols):
    """
    Time-series line chart — hanya dipanggil jika dt_cols tersedia.
    Tidak ada toggle (TS bersifat fixed ke dt_col × num_col utama).
    Return: chart_json atau None
    """
    if not (dt_cols and num_cols):
        return None
    try:
        from backend.time_series import prepare_ts
        dt_col, num_col = dt_cols[0], num_cols[0]
        ts, freq_label = prepare_ts(df, dt_col, num_col)
        if ts is None or len(ts) < 4:
            return None
        x_vals = ts['ds'].astype(str).tolist()
        y_vals = ts['y'].tolist()
        fig = go.Figure(go.Scatter(
            x=x_vals, y=y_vals,
            mode='lines',
            line=dict(color=PALETTE[0], width=2),
            fill='tozeroy',
            fillcolor='rgba(78,205,196,0.12)',
            hovertemplate='%{x}<br>' + num_col + ': %{y:,.2f}<extra></extra>',
        ))
        fig.update_layout(_layout(
            title=f'Trend — {num_col} ({freq_label})',
            xaxis=dict(type='date'),
        ))
        _axes(fig)
        return _json(fig)
    except Exception as e:
        print(f"[overview] ts top_right error: {e}")
        return None


def _build_ts_line_charts(df, num_cols, dt_cols):
    """
    Time-series line charts untuk setiap kolom numerik.
    Digunakan untuk toggle dropdown ov_ts_line.
    Return: dict {num_col: chart_json}
    """
    if not (dt_cols and num_cols):
        return {}
    result = {}
    from backend.time_series import prepare_ts
    dt_col = dt_cols[0]
    for col in num_cols[:6]:
        try:
            ts, freq_label = prepare_ts(df, dt_col, col)
            if ts is None or len(ts) < 4:
                continue
            x_vals = ts['ds'].astype(str).tolist()
            y_vals = ts['y'].tolist()
            fig = go.Figure(go.Scatter(
                x=x_vals, y=y_vals,
                mode='lines',
                line=dict(color=PALETTE[0], width=2),
                fill='tozeroy',
                fillcolor='rgba(78,205,196,0.12)',
                hovertemplate='%{x}<br>' + col + ': %{y:,.2f}<extra></extra>',
            ))
            fig.update_layout(_layout(
                title=f'Trend — {col} ({freq_label})',
                xaxis=dict(type='date'),
            ))
            _axes(fig)
            result[col] = _json(fig)
        except Exception as e:
            print(f"[overview] ts line chart error for {col}: {e}")
            continue
    return result


def _build_vbar_left_charts(df, num_cols):
    """
    Histogram per kolom numerik (toggle semua num_cols).
    Return: dict {col_name: chart_json}
    """
    if not num_cols:
        return {}
    result = {}
    for col in num_cols[:6]:
        chart = _safe(_chart_histogram, df, col)
        if chart:
            result[col] = chart
    return result


def _build_boxplot_charts(df, num_cols):
    """
    Box Plot per kolom numerik (toggle semua num_cols).
    Default kolom: num_cols[1] jika ada (beda dari histogram default).
    Return: dict {col_name: chart_json}
    """
    if not num_cols:
        return {}
    result = {}
    for col in num_cols[:6]:
        chart = _safe(_chart_boxplot, df, col)
        if chart:
            result[col] = chart
    return result


def _build_vbar_right_charts(df, cat_cols):
    """
    Bar Chart vertikal per kolom kategorik (toggle semua cat_cols).
    Return: dict {col_name: chart_json}
    """
    if not cat_cols:
        return {}
    result = {}
    for col in cat_cols[:6]:
        chart = _safe(_chart_bar, df, col)
        if chart:
            result[col] = chart
    return result


# ─── Toggle data builder helper ──────────────────────────────────────────────

def _make_toggle(charts_dict, default_col):
    if not charts_dict:
        return None
    keys    = list(charts_dict.keys())
    default = default_col if default_col in charts_dict else keys[0]
    return {
        'options': keys,
        'default': default,
        'charts' : charts_dict,
    }


# ─── MAIN ENTRY POINT ────────────────────────────────────────────────────────

def generate_overview_dashboard(df, num_cols, cat_cols, dt_cols=None, metrics=None, **kwargs):
    """
    Bangun payload lengkap untuk tab Dashboard Overview.
    """
    dt_cols = dt_cols or []
    metrics = metrics or {}

    result = {
        'kpis'         : build_overview_kpis(df, num_cols, cat_cols, metrics),
        'slots'        : {},
        'toggle_data'  : {},
        'viz_links'    : {},
        'stats_preview': build_stats_preview(df, num_cols, cat_cols),
    }

    def _slot(key, chart_json, title, viz_tab, viz_sub=None, insights=None):
        result['slots'][key] = {
            'visible': chart_json is not None,
            'title'  : title,
            'chart'  : chart_json,
            'insights': insights or [],
        }
        result['viz_links'][key] = {
            'tab': viz_tab,
            'sub': viz_sub or 'numerical',
        }

    def _reg(key, charts_dict, default_col):
        td = _make_toggle(charts_dict, default_col)
        if td:
            result['toggle_data'][key] = td

    def _add_insights(key, fn, dframe):
        td = result['toggle_data'].get(key)
        if not td:
            return
        td['insights'] = {}
        for opt in td['options']:
            s = sanitize_series(dframe[opt], opt) if opt in dframe.columns else pd.Series(dtype=float)
            td['insights'][opt] = fn(s)

    def _add_pair_insights(key, fn, dframe, pairs):
        td = result['toggle_data'].get(key)
        if not td:
            return
        td['insights'] = {}
        for label in td['options']:
            parts = label.split(' vs ')
            if len(parts) == 2:
                td['insights'][label] = fn(dframe, parts[0], parts[1])

    # ══════════════════════════════════════════════════════════════════
    # BARIS TENGAH
    # ══════════════════════════════════════════════════════════════════

    # ov_hbar: Pareto Chart — toggle semua cat_cols
    pareto_charts = _build_pareto_charts(df, cat_cols)
    default_cat0  = cat_cols[0] if cat_cols else ''
    _reg('ov_hbar', pareto_charts, default_cat0)
    _slot('ov_hbar',
          pareto_charts.get(default_cat0) if pareto_charts else None,
          title   = f'Pareto — {default_cat0}' if default_cat0 else '',
          viz_tab = 'visualizations',
          viz_sub = 'categorical')

    # ov_center: Pie/Donut — toggle semua cat_cols
    pie_charts = _build_pie_charts(df, cat_cols)
    _reg('ov_center', pie_charts, default_cat0)
    _slot('ov_center',
          pie_charts.get(default_cat0) if pie_charts else None,
          title   = f'Composition — {default_cat0}' if default_cat0 else '',
          viz_tab = 'visualizations',
          viz_sub = 'categorical')

    # ov_top_right: TS (fixed) → Scatter (toggle X & Y) → SKIP
    has_ts = bool(dt_cols and num_cols)
    if has_ts:
        # TS: chart tunggal, tidak ada toggle kolom
        ts_chart = _build_top_right_ts(df, num_cols, dt_cols)
        _slot('ov_top_right', ts_chart,
              title   = f'Trend — {num_cols[0]}' if ts_chart and num_cols else '',
              viz_tab = 'timeseries',
              viz_sub = None)
        # Tidak perlu toggle_data untuk slot ini (TS fixed)
    elif len(num_cols) >= 2:
        # Scatter dengan toggle X dan Y terpisah
        scatter_charts = _build_scatter_charts(df, num_cols)
        default_x      = num_cols[0]
        default_y      = num_cols[1]
        # Struktur toggle khusus scatter: nested { col_x: { col_y: chart } }
        default_chart  = (scatter_charts.get(default_x) or {}).get(default_y)
        result['toggle_data']['ov_top_right'] = {
            'type'    : 'scatter',          # penanda untuk JS
            'options_x': list(scatter_charts.keys()),
            'options_y': num_cols[:6],
            'default_x': default_x,
            'default_y': default_y,
            'charts'   : scatter_charts,    # nested dict
        }
        _slot('ov_top_right', default_chart,
              title   = f'Scatter — {default_x} × {default_y}' if default_chart else '',
              viz_tab = 'visualizations',
              viz_sub = 'bivariate')
    else:
        _slot('ov_top_right', None, '', 'visualizations', 'bivariate')

    # ══════════════════════════════════════════════════════════════════
    # BARIS BAWAH
    # ══════════════════════════════════════════════════════════════════

    # ov_vbar_left: Histogram + toggle semua num_cols
    vbar_left = _build_vbar_left_charts(df, num_cols)
    default_num0 = num_cols[0] if num_cols else ''
    _reg('ov_vbar_left', vbar_left, default_num0)
    _slot('ov_vbar_left',
          vbar_left.get(default_num0) if vbar_left else None,
          title   = f'Distribution — {default_num0}' if default_num0 else '',
          viz_tab = 'visualizations',
          viz_sub = 'numerical')

    # ov_area_bottom: Boxplot + toggle semua num_cols
    # Default: num_cols[1] jika ada (beda dari histogram default di vbar_left)
    boxplot_charts = _build_boxplot_charts(df, num_cols)
    default_num1   = num_cols[1] if len(num_cols) >= 2 else default_num0
    _reg('ov_area_bottom', boxplot_charts, default_num1)
    _slot('ov_area_bottom',
          boxplot_charts.get(default_num1) if boxplot_charts else None,
          title   = f'Spread — {default_num1}' if default_num1 else '',
          viz_tab = 'visualizations',
          viz_sub = 'numerical')

    # ov_vbar_right: Bar Chart + toggle semua cat_cols
    vbar_right = _build_vbar_right_charts(df, cat_cols)
    _reg('ov_vbar_right', vbar_right, default_cat0)
    _slot('ov_vbar_right',
          vbar_right.get(default_cat0) if vbar_right else None,
          title   = f'Frequency — {default_cat0}' if default_cat0 else '',
          viz_tab = 'visualizations',
          viz_sub = 'categorical')

    # ══════════════════════════════════════════════════════════════════
    # VIZ ENGINE — slot aliases expected by frontend templates
    # ══════════════════════════════════════════════════════════════════

    # Build scatter pairs whenever possible (independent of TS)
    scatter_pairs = {}
    if len(num_cols) >= 2:
        for i, cx in enumerate(num_cols[:6]):
            for j, cy in enumerate(num_cols[:6]):
                if cx >= cy:
                    continue
                chart = _safe(_chart_scatter, df, cx, cy)
                if chart:
                    scatter_pairs[f'{cx} vs {cy}'] = chart
    default_pair = list(scatter_pairs.keys())[0] if scatter_pairs else ''

    # ov_ts_line
    if has_ts:
        ts_line_charts = _build_ts_line_charts(df, num_cols, dt_cols)
        default_ts_col = num_cols[0] if num_cols else ''
        _slot('ov_ts_line',
              ts_line_charts.get(default_ts_col) if ts_line_charts else None,
              title=f'Trend — {default_ts_col}' if default_ts_col else '',
              viz_tab='timeseries', viz_sub='line',
              insights=_num_insights(sanitize_series(df[default_ts_col], default_ts_col)) if default_ts_col else None)
        _reg('ov_ts_line', ts_line_charts, default_ts_col)
        _add_insights('ov_ts_line', _num_insights, df)
    else:
        _slot('ov_ts_line', None, '', 'timeseries', 'line')

    # ov_scatter (always built when enough num_cols)
    if scatter_pairs:
        _slot('ov_scatter',
              scatter_pairs.get(default_pair) if scatter_pairs else None,
              title=f'Scatter — {default_pair}' if default_pair else '',
              viz_tab='visualizations', viz_sub='bivariate',
              insights=_pair_insights(df, *(default_pair.split(' vs ')[:2])) if default_pair and ' vs ' in default_pair else None)
        _reg('ov_scatter', scatter_pairs, default_pair)
        _add_pair_insights('ov_scatter', _pair_insights, df, scatter_pairs)
    else:
        _slot('ov_scatter', None, '', 'visualizations', 'bivariate')

    # ov_pie: same chart data as ov_center
    _slot('ov_pie',
          pie_charts.get(default_cat0) if pie_charts else None,
          title=f'Composition — {default_cat0}' if default_cat0 else '',
          viz_tab='visualizations', viz_sub='categorical',
          insights=_cat_insights(df[default_cat0]) if default_cat0 and default_cat0 in df.columns else None)
    _reg('ov_pie', pie_charts, default_cat0)
    _add_insights('ov_pie', _cat_insights, df)

    # ov_bar → Pareto chart (replaces redundant plain bar; shows 80/20)
    _slot('ov_bar',
          pareto_charts.get(default_cat0) if pareto_charts else None,
          title=f'Pareto — {default_cat0}' if default_cat0 else '',
          viz_tab='visualizations', viz_sub='categorical',
          insights=_cat_insights(df[default_cat0]) if default_cat0 and default_cat0 in df.columns else None)
    _reg('ov_bar', pareto_charts, default_cat0)
    _add_insights('ov_bar', _cat_insights, df)

    # ov_histogram: same chart data as ov_vbar_left
    default_hist_col = default_num0
    _slot('ov_histogram',
          vbar_left.get(default_hist_col) if vbar_left else None,
          title=f'Distribution — {default_hist_col}' if default_hist_col else '',
          viz_tab='visualizations', viz_sub='numerical',
          insights=_num_insights(sanitize_series(df[default_hist_col], default_hist_col)) if default_hist_col else None)
    _reg('ov_histogram', vbar_left, default_hist_col)
    _add_insights('ov_histogram', _num_insights, df)

    # ov_boxplot: same chart data as ov_area_bottom
    _slot('ov_boxplot',
          boxplot_charts.get(default_num1) if boxplot_charts else None,
          title=f'Spread — {default_num1}' if default_num1 else '',
          viz_tab='visualizations', viz_sub='numerical',
          insights=_num_insights(sanitize_series(df[default_num1], default_num1)) if default_num1 else None)
    _reg('ov_boxplot', boxplot_charts, default_num1)
    _add_insights('ov_boxplot', _num_insights, df)

    return result