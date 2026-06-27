"""
backend/viz_engine.py
Master Visualization Engine — 1 chart per view, dark pastel theme, dynamic columns.

FIX (bdata prevention):
  Semua array numerik/kategorik yang di-pass ke Plotly trace dikonversi ke
  plain Python list via .tolist() SEBELUM masuk go.* constructor.
  Ini mencegah Plotly men-serialize array sebagai bdata (base64 binary),
  yang tidak bisa di-decode oleh dashboardOverview.js karena chart di-embed
  langsung di HTML (bukan via AJAX).

  Chart yang di-render via AJAX (VizMaster) sudah punya decode di JS,
  tapi chart Overview di-embed via {{ overview | tojson }} — tidak ada
  decode step, sehingga bdata tampil sebagai angka salah/kosong.

  Solusi universal: hilangkan bdata dari sumbernya.
"""

import json
import os
import threading
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
from scipy import stats as scipy_stats
from backend.data_sanitizer import sanitize_series, filter_numeric_cols

# ─── Thread-local theme controller ───────────────────────────────────────────
_thread_local = threading.local()


def set_theme(theme):
    _thread_local.theme = theme


def get_theme():
    return getattr(_thread_local, 'theme', 'dark')


THEME_CONFIG = {
    'dark': {
        'template'        : 'plotly_dark',
        'paper_bgcolor'   : '#111A40',
        'plot_bgcolor'    : '#172254',
        'font_color'      : '#C8D8F0',
        'grid_color'      : 'rgba(255,255,255,0.06)',
        'zerolinecolor'   : 'rgba(255,255,255,0.12)',
        'axis_line'       : 'rgba(255,255,255,0.12)',
        'hover_bg'        : 'rgba(17,26,64,0.95)',
        'hover_border'    : 'rgba(126,169,255,0.4)',
        'hover_font'      : '#E8F0FF',
        'legend_bg'       : 'rgba(17,26,64,0.6)',
        'legend_border'   : 'rgba(255,255,255,0.08)',
        'annot_font_color': '#E8F0FF',
    },
    'light': {
        'template'        : 'plotly_white',
        'paper_bgcolor'   : '#FFFFFF',
        'plot_bgcolor'    : '#FFFFFF',
        'font_color'      : '#1F2937',
        'grid_color'      : '#E5E7EB',
        'zerolinecolor'   : '#9CA3AF',
        'axis_line'       : '#E5E7EB',
        'hover_bg'        : 'rgba(255,255,255,0.95)',
        'hover_border'    : 'rgba(0,0,0,0.12)',
        'hover_font'      : '#1F2937',
        'legend_bg'       : 'rgba(255,255,255,0.8)',
        'legend_border'   : 'rgba(0,0,0,0.08)',
        'annot_font_color': '#1F2937',
    },
}


def _cfg():
    return THEME_CONFIG[get_theme()]


# ─── High Visual Dark Palette ────────────────────────────────────────────────
PALETTE = ['#4ECDC4', '#7EA9FF', '#A8E6CF', '#C9B8FF', '#88D4E8', '#F4A9C8']
# Kept for backward compat — new code reads from _cfg()
BG_CONTAINER = '#111A40'
PLOT_BG      = '#172254'
GRID         = 'rgba(255,255,255,0.06)'
AXIS_LINE    = 'rgba(255,255,255,0.12)'
FONT_COLOR   = '#C8D8F0'

# ─── All category→chart-type lists (SINGLE SOURCE OF TRUTH) ──────────────────
CATEGORY_CHARTS = {
    'numerical'   : ['histogram', 'boxplot', 'density', 'qq', 'violin'],
    'categorical' : ['bar', 'pie', 'count', 'pareto'],
    'bivariate'   : ['scatter', 'heatmap', 'scatter_matrix', 'regression_plot', 'bubble_chart', 'line'],
    'catnum'      : ['box_cat_num', 'violin_cat_num', 'grouped_bar', 'strip_plot'],
    'compare'     : ['violin_compare', 'grouped_bar_compare', 'parallel_coords'],
    'heatmap_all' : ['heatmap_all'],
}

CHART_LABELS = {
    'histogram'           : 'Histogram + KDE',
    'boxplot'             : 'Box Plot',
    'density'             : 'Density Plot (KDE)',
    'qq'                  : 'QQ Plot — Normality',
    'violin'              : 'Violin Plot',
    'bar'                 : 'Bar Chart',
    'pie'                 : 'Donut / Pie Chart',
    'count'               : 'Count Plot',
    'pareto'              : 'Pareto Chart',
    'scatter'             : 'Scatter Plot',
    'heatmap'             : 'Correlation Heatmap',
    'scatter_matrix'      : 'Pair Plot / Scatter Matrix',
    'regression_plot'     : 'Regression + 95% CI',
    'bubble_chart'        : 'Bubble Chart',
    'box_cat_num'         : 'Boxplot by Category',
    'violin_cat_num'      : 'Violin by Category',
    'grouped_bar'         : 'Grouped Bar Chart',
    'strip_plot'          : 'Strip Plot',
    'violin_compare'      : 'Violin Comparison',
    'grouped_bar_compare' : 'Mean ± Std Comparison',
    'parallel_coords'     : 'Parallel Coordinates',
    'heatmap_all'         : 'Heatmap Semua Variabel',
    'line'                : 'Line Chart — Time Series',
}

PLACEHOLDERS = {
    'numerical'  : 'Gunakan dataset dengan minimal 1 kolom numerik untuk mengaktifkan halaman ini.',
    'categorical': 'Gunakan dataset dengan kolom kategorik untuk mengaktifkan halaman ini.',
    'bivariate'  : 'Gunakan dataset dengan minimal 2 kolom numerik untuk mengaktifkan halaman ini.',
    'catnum'     : 'Gunakan dataset dengan kolom numerik dan kategorik untuk mengaktifkan halaman ini.',
    'compare'    : 'Gunakan dataset dengan minimal 2 kolom numerik untuk perbandingan.',
    'heatmap_all': 'Gunakan dataset dengan minimal 2 kolom untuk heatmap semua variabel.',
}


def category_available(category, num_cols, cat_cols):
    n, c = len(num_cols), len(cat_cols)
    checks = {
        'numerical'  : n >= 1,
        'categorical': c >= 1,
        'bivariate'  : n >= 2,
        'catnum'     : n >= 1 and c >= 1,
        'compare'    : n >= 2,
    }
    checks['heatmap_all'] = n + c >= 2
    return checks.get(category, False)


# ─── Layout helpers ───────────────────────────────────────────────────────────

def _layout(**extra):
    c = _cfg()
    base = dict(
        template      = c['template'],
        paper_bgcolor = c['paper_bgcolor'],
        plot_bgcolor  = c['plot_bgcolor'],
        font          = dict(color=c['font_color'], family='Inter, sans-serif', size=12),
        margin        = dict(l=50, r=30, t=50, b=50),
        hoverlabel    = dict(
            bgcolor     = c['hover_bg'],
            bordercolor = c['hover_border'],
            font        = dict(color=c['hover_font'], size=12),
        ),
        legend = dict(
            bgcolor     = c['legend_bg'],
            bordercolor = c['legend_border'],
            font        = dict(color=c['font_color'], size=11),
        ),
    )
    base.update(extra)
    return base


def _axes(fig):
    c = _cfg()
    style = dict(
        gridcolor     = c['grid_color'],
        zerolinecolor = c['zerolinecolor'],
        linecolor     = c['axis_line'],
        tickfont      = dict(color=c['font_color'], size=12),
        title_font    = dict(color=c['font_color'], size=12),
    )
    fig.update_xaxes(**style)
    fig.update_yaxes(**style)
    return fig


def decode_typed_arrays(obj):
    """Recursively convert Plotly typed arrays ({bdata, dtype}) to plain lists."""
    import base64
    if isinstance(obj, dict):
        if 'bdata' in obj and 'dtype' in obj:
            bdata = base64.b64decode(obj['bdata'])
            dtype_map = {'i1':'i1','i2':'i2','i4':'i4','i8':'i8',
                         'u1':'u1','u2':'u2','u4':'u4','u8':'u8','f4':'f4','f8':'f8'}
            dt = dtype_map.get(obj['dtype'], 'f8')
            return [float(x) for x in np.frombuffer(bdata, dtype=np.dtype(dt))]
        return {k: decode_typed_arrays(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decode_typed_arrays(i) for i in obj]
    return obj

def _json(fig):
    return decode_typed_arrays(json.loads(fig.to_json()))


def _to_list(arr):
    """
    Konversi numpy array / pandas Series ke plain Python list.
    Ini WAJIB sebelum passing ke Plotly trace agar tidak di-encode
    sebagai bdata (base64 binary) dalam JSON output.
    """
    if arr is None:
        return []
    if isinstance(arr, (np.ndarray,)):
        return arr.tolist()
    if isinstance(arr, pd.Series):
        return arr.tolist()
    if hasattr(arr, 'tolist'):
        return arr.tolist()
    return list(arr)


# ─── KPI builders ────────────────────────────────────────────────────────────

def _kpis_numeric(series, col_name):
    s = series.dropna()
    if s.empty:
        return []
    return [
        {'label': 'Mean',    'value': f'{s.mean():,.2f}',  'icon': 'fa-calculator'},
        {'label': 'Median',  'value': f'{s.median():,.2f}','icon': 'fa-chart-line'},
        {'label': 'Std Dev', 'value': f'{s.std():,.2f}',   'icon': 'fa-ruler'},
        {'label': 'Min',     'value': f'{s.min():,.2f}',   'icon': 'fa-arrow-down'},
        {'label': 'Max',     'value': f'{s.max():,.2f}',   'icon': 'fa-arrow-up'},
    ]


def _kpis_categorical(series, col_name):
    s  = series.dropna()
    if s.empty:
        return []
    vc   = s.value_counts()
    mode = str(vc.index[0]) if not vc.empty else 'N/A'
    return [
        {'label': 'Unique',   'value': str(s.nunique()),                               'icon': 'fa-tags'},
        {'label': 'Mode',     'value': mode[:18],                                      'icon': 'fa-star'},
        {'label': 'Top Freq', 'value': str(int(vc.iloc[0])) if not vc.empty else '0', 'icon': 'fa-hashtag'},
        {'label': 'Missing',  'value': str(int(series.isna().sum())),                  'icon': 'fa-exclamation'},
        {'label': 'Rows',     'value': f'{len(series):,}',                             'icon': 'fa-list'},
    ]


def _kpis_bivariate(df, col_x, col_y):
    clean = df[[col_x, col_y]].dropna()
    if len(clean) < 2:
        return _kpis_numeric(df[col_x], col_x)[:5]
    r = clean[col_x].corr(clean[col_y])
    return [
        {'label': 'Correlation',        'value': f'{r:.3f}',                    'icon': 'fa-link'},
        {'label': 'Pairs',              'value': f'{len(clean):,}',             'icon': 'fa-circle-dot'},
        {'label': f'Mean {col_x[:12]}', 'value': f'{clean[col_x].mean():,.2f}', 'icon': 'fa-calculator'},
        {'label': f'Mean {col_y[:12]}', 'value': f'{clean[col_y].mean():,.2f}', 'icon': 'fa-chart-bar'},
        {'label': 'R²',                 'value': f'{r**2:.3f}',                 'icon': 'fa-square-root-alt'},
    ]


def build_kpis(category, df, col_x=None, col_y=None, num_cols=None):
    if category == 'numerical' and col_x:
        return _kpis_numeric(df[col_x], col_x)
    if category == 'categorical' and col_x:
        return _kpis_categorical(df[col_x], col_x)
    if category == 'bivariate' and col_x and col_y:
        return _kpis_bivariate(df, col_x, col_y)
    if category == 'catnum' and col_x and col_y:
        return [
            {'label': 'Groups',             'value': str(df[col_x].nunique()),   'icon': 'fa-layer-group'},
            {'label': f'Mean {col_y[:12]}', 'value': f'{df[col_y].mean():,.2f}', 'icon': 'fa-calculator'},
            {'label': 'Std',                'value': f'{df[col_y].std():,.2f}',  'icon': 'fa-ruler'},
            {'label': 'Rows',               'value': f'{len(df):,}',             'icon': 'fa-list'},
            {'label': 'Missing',            'value': str(int(df[[col_x, col_y]].isna().any(axis=1).sum())), 'icon': 'fa-exclamation'},
        ]
    if category == 'compare' and num_cols:
        return [
            {'label': 'Variables', 'value': str(len(num_cols)),                    'icon': 'fa-hashtag'},
            {'label': 'Rows',      'value': f'{len(df):,}',                        'icon': 'fa-list'},
            {'label': 'Cols',      'value': str(len(df.columns)),                  'icon': 'fa-columns'},
            {'label': 'Numeric',   'value': str(len(num_cols)),                    'icon': 'fa-chart-bar'},
            {'label': 'Complete',  'value': f'{df[num_cols].dropna().shape[0]:,}', 'icon': 'fa-check'},
        ]
    return []


# ─── a) NUMERICAL ────────────────────────────────────────────────────────────

def _chart_histogram(df, col):
    raw   = df[col] if col in df.columns else pd.Series(dtype=float)
    clean = sanitize_series(raw, col)   # forced numeric conversion
    if clean.empty:
        return None
    fig   = go.Figure()
    # FIX: .tolist() prevents bdata encoding
    fig.add_trace(go.Histogram(
        x=_to_list(clean), nbinsx=30,
        marker_color=PALETTE[0], opacity=0.85, name=col,
        hovertemplate='%{x}<br>Count: %{y}<extra></extra>',
    ))
    if len(clean) >= 3:
        try:
            kde_x = np.linspace(float(clean.min()), float(clean.max()), 200)
            kde   = scipy_stats.gaussian_kde(clean)
            scale = len(clean) * (float(clean.max()) - float(clean.min())) / 30
            # FIX: .tolist() on both kde_x and kde values
            fig.add_trace(go.Scatter(
                x=kde_x.tolist(), y=(kde(kde_x) * scale).tolist(),
                mode='lines', name='KDE',
                line=dict(color=PALETTE[1], width=2.5),
                hovertemplate='%{x:.2f}<br>Density: %{y:.4f}<extra></extra>',
            ))
        except Exception:
            pass  # KDE failed (e.g. constant data), skip overlay
    fig.update_layout(_layout(title=f' {CHART_LABELS["histogram"]}: {col}'))
    return _json(_axes(fig))


def _chart_boxplot(df, col):
    clean = sanitize_series(df[col] if col in df.columns else pd.Series(dtype=float), col)
    if clean.empty:
        return None
    fig = go.Figure(go.Box(
        y=_to_list(clean), name=col,
        marker_color=PALETTE[0],
        boxmean='sd', line_color=PALETTE[1],
        hovertemplate=f'{col}: %{{y:.2f}}<extra></extra>',
    ))
    fig.update_layout(_layout(title=f' {CHART_LABELS["boxplot"]}: {col}'))
    return _json(_axes(fig))


def _chart_density(df, col):
    clean = sanitize_series(df[col] if col in df.columns else pd.Series(dtype=float), col)
    if len(clean) < 3:
        return None
    try:
        kde_x = np.linspace(float(clean.min()), float(clean.max()), 300)
        kde   = scipy_stats.gaussian_kde(clean)
        fig   = go.Figure(go.Scatter(
            x=kde_x.tolist(), y=(kde(kde_x)).tolist(),
            fill='tozeroy', mode='lines',
            line=dict(color=PALETTE[0], width=2.5),
            fillcolor='rgba(78,205,196,0.18)', name=col,
            hovertemplate='%{x:.2f}<br>Density: %{y:.4f}<extra></extra>',
        ))
        fig.update_layout(_layout(title=f' {CHART_LABELS["density"]}: {col}'))
        return _json(_axes(fig))
    except Exception:
        return None


def _chart_qq(df, col):
    clean = sanitize_series(df[col] if col in df.columns else pd.Series(dtype=float), col)
    if len(clean) < 4:
        return None
    try:
        clean_arr = clean.values
        (osm, osr), (slope, intercept, _) = scipy_stats.probplot(clean_arr, dist='norm')
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=osm.tolist(), y=osr.tolist(), mode='markers',
            marker=dict(color=PALETTE[1], size=5, opacity=0.7),
            name='Data Points',
            hovertemplate='Theoretical: %{x:.3f}<br>Sample: %{y:.3f}<extra></extra>',
        ))
        x_line = np.array([osm.min(), osm.max()])
        fig.add_trace(go.Scatter(
            x=x_line.tolist(), y=(slope * x_line + intercept).tolist(),
            mode='lines', name='Normal Reference',
            line=dict(color=PALETTE[2], dash='dash', width=2),
        ))
        fig.update_layout(_layout(
            title=f' {CHART_LABELS["qq"]}: {col}',
            xaxis_title='Theoretical Quantiles',
            yaxis_title='Sample Quantiles',
        ))
        return _json(_axes(fig))
    except Exception:
        return None


def _chart_violin(df, col):
    clean = sanitize_series(df[col] if col in df.columns else pd.Series(dtype=float), col)
    if clean.empty:
        return None
    fig = go.Figure(go.Violin(
        y=_to_list(clean), name=col,
        fillcolor=PALETTE[0], line_color=PALETTE[1],
        box_visible=True, meanline_visible=True, opacity=0.8,
        hovertemplate=f'{col}: %{{y:.2f}}<extra></extra>',
    ))
    fig.update_layout(_layout(title=f' {CHART_LABELS["violin"]}: {col}'))
    return _json(_axes(fig))


# ─── b) CATEGORICAL ──────────────────────────────────────────────────────────

def _chart_bar(df, col):
    vc  = df[col].value_counts().head(12)
    fig = go.Figure(go.Bar(
        x=vc.index.astype(str).tolist(),
        y=vc.values.tolist(),          # FIX: .tolist()
        marker_color=PALETTE[0], opacity=0.9,
        hovertemplate='%{x}<br>Count: %{y:,}<extra></extra>',
    ))
    fig.update_layout(_layout(title=f' {CHART_LABELS["bar"]}: {col}'))
    return _json(_axes(fig))


def _chart_pie(df, col):
    vc  = df[col].value_counts().head(10)
    fig = go.Figure(go.Pie(
        labels=vc.index.astype(str).tolist(),
        values=vc.values.tolist(),     # FIX: .tolist()
        hole=0.45,
        marker_colors=PALETTE,
        textfont=dict(color=_cfg()['font_color']),
        hovertemplate='%{label}<br>Count: %{value:,}<br>%{percent}<extra></extra>',
    ))
    fig.update_layout(_layout(title=f' {CHART_LABELS["pie"]}: {col}'))
    return _json(fig)


def _chart_count(df, col):
    vc  = df[col].value_counts().head(15).sort_values()
    fig = go.Figure(go.Bar(
        x=vc.values.tolist(),          # FIX: .tolist()
        y=vc.index.astype(str).tolist(),
        orientation='h',
        marker_color=PALETTE[2], opacity=0.9,
        hovertemplate='%{y}<br>Count: %{x:,}<extra></extra>',
    ))
    fig.update_layout(_layout(title=f' {CHART_LABELS["count"]}: {col}'))
    return _json(_axes(fig))


def _chart_pareto(df, col):
    vc  = df[col].value_counts().head(12)
    cum = (vc.cumsum() / vc.sum() * 100)
    x_labels = vc.index.astype(str).tolist()
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    fig.add_trace(go.Bar(
        x=x_labels,
        y=vc.values.tolist(),          # FIX: .tolist()
        marker_color=PALETTE[0], opacity=0.85,
        name='Count',
        hovertemplate='%{x}<br>Count: %{y:,}<extra></extra>',
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=x_labels,
        y=cum.tolist(),                # FIX: .tolist()
        mode='lines+markers',
        line=dict(color=PALETTE[3], width=2.5),
        name='Cumulative %',
        hovertemplate='%{x}<br>Cumulative: %{y:.1f}%<extra></extra>',
    ), secondary_y=True)
    fig.add_hline(y=80, line_dash='dash', line_color=PALETTE[2],
                  annotation_text='80%', secondary_y=True)
    fig.update_yaxes(title_text='Count',        secondary_y=False)
    fig.update_yaxes(title_text='Cumulative %', secondary_y=True, range=[0, 105])
    fig.update_layout(_layout(title=f' {CHART_LABELS["pareto"]}: {col} (80/20 Rule)'))
    return _json(_axes(fig))


# ─── c) BIVARIATE ────────────────────────────────────────────────────────────

def _chart_scatter(df, col_x, col_y):
    clean = df[[col_x, col_y]].dropna()
    fig = go.Figure(go.Scatter(
        x=_to_list(clean[col_x]),
        y=_to_list(clean[col_y]),
        mode='markers',
        marker=dict(color=PALETTE[0], size=6, opacity=0.65),
        hovertemplate=f'{col_x}: %{{x:.2f}}<br>{col_y}: %{{y:.2f}}<extra></extra>',
    ))
    fig.update_layout(_layout(
        title=f' {CHART_LABELS["scatter"]}: {col_x} vs {col_y}',
        xaxis_title=col_x,
        yaxis_title=col_y,
    ))
    return _json(_axes(fig))


def _chart_heatmap(df, num_cols):
    """
    Correlation heatmap — only valid numeric cols enter df.corr().
    FIX: filter_numeric_cols guards against TypeError in df.corr().
    """
    # Safe: keep only truly numeric, non-empty, non-constant columns
    valid_cols = filter_numeric_cols(df, num_cols[:12])
    if len(valid_cols) < 2:
        return None
    try:
        # Work on coerced copy to handle any remaining string-encoded numbers
        from backend.data_sanitizer import sanitize_df_numeric_cols
        df2  = sanitize_df_numeric_cols(df, valid_cols)
        corr = df2[valid_cols].corr()
        z_values = corr.values.tolist()
        z_text   = [[f'{v:.2f}' if not (isinstance(v, float) and (v != v)) else 'N/A'
                     for v in row] for row in corr.values.tolist()]
        col_list = corr.columns.tolist()

        c        = _cfg()
        is_dark  = get_theme() == 'dark'
        clr_low  = c['plot_bgcolor'] if is_dark else '#F3F4F6'
        fig = go.Figure(go.Heatmap(
            z=z_values,
            x=col_list,
            y=col_list,
            colorscale=[[0, clr_low], [0.5, PALETTE[1]], [1, PALETTE[0]]],
            zmid=0,
            text=z_text,
            texttemplate='%{text}',
            textfont=dict(color=c['annot_font_color'], size=11),
            hovertemplate='%{x} × %{y}<br>r = %{z:.3f}<extra></extra>',
        ))
        fig.update_layout(_layout(title=f' {CHART_LABELS["heatmap"]}'))
        return _json(fig)
    except Exception as exc:
        print(f"[viz_engine] heatmap error: {exc}")
        return None


def _chart_heatmap_all(df):
    """
    Correlation heatmap menggunakan SEMUA kolom:
    - Kolom numerik langsung diambil
    - Kolom kategorikal dengan ≤10 unique value di-label-encode via pd.factorize
    """
    try:
        encoded_parts = []

        numeric_df = df.select_dtypes(include=['number'])
        if not numeric_df.empty:
            encoded_parts.append(numeric_df)

        cat_df = df.select_dtypes(include=['object', 'category'])
        for col in cat_df.columns:
            if cat_df[col].nunique() <= 10 and cat_df[col].nunique() > 1:
                codes, _ = pd.factorize(cat_df[col].astype(str))
                encoded_parts.append(pd.DataFrame({col: codes}, index=df.index))

        if len(encoded_parts) < 2:
            return None

        combined = pd.concat(encoded_parts, axis=1)
        if combined.shape[1] < 2:
            return None

        corr = combined.corr(numeric_only=False)
        z_values = corr.values.tolist()
        z_text = [[f'{v:.2f}' if not (isinstance(v, float) and (v != v)) else 'N/A'
                   for v in row] for row in corr.values.tolist()]
        col_list = corr.columns.tolist()

        c = _cfg()
        is_dark = get_theme() == 'dark'
        clr_low = c['plot_bgcolor'] if is_dark else '#F3F4F6'
        fig = go.Figure(go.Heatmap(
            z=z_values,
            x=col_list,
            y=col_list,
            colorscale=[[0, clr_low], [0.5, PALETTE[1]], [1, PALETTE[0]]],
            zmid=0,
            text=z_text,
            texttemplate='%{text}',
            textfont=dict(color=c['annot_font_color'], size=9),
            hovertemplate='%{x} × %{y}<br>r = %{z:.3f}<extra></extra>',
        ))
        fig.update_layout(
            _layout(title=f' {CHART_LABELS["heatmap_all"]}'),
        )
        fig.update_xaxes(tickangle=45)
        return _json(fig)
    except Exception as exc:
        print(f"[viz_engine] heatmap_all error: {exc}")
        return None


def _chart_scatter_matrix(df, num_cols):
    cols = num_cols[:5]
    df_s = df[cols].dropna()
    if df_s.empty:
        return None
    fig = px.scatter_matrix(
        df_s, dimensions=cols,
        color_discrete_sequence=PALETTE,
        title=f' {CHART_LABELS["scatter_matrix"]}',
    )
    fig.update_traces(
        diagonal_visible=False,
        marker=dict(size=3, opacity=0.55),
        hovertemplate='%{xaxis.title.text}: %{x:.2f}<br>%{yaxis.title.text}: %{y:.2f}<extra></extra>',
    )
    fig.update_layout(_layout())
    return _json(fig)


def _chart_regression_plot(df, col_x, col_y):
    if col_x == col_y:
        return _chart_scatter(df, col_x, col_y)

    df_r = df[[col_x, col_y]].dropna()
    if len(df_r) < 4:
        return None
    if df_r[col_x].nunique() < 2:
        return _chart_scatter(df, col_x, col_y)

    slope, intercept, r, p, se = scipy_stats.linregress(df_r[col_x], df_r[col_y])

    x_line = np.linspace(float(df_r[col_x].min()), float(df_r[col_x].max()), 200)
    y_line = slope * x_line + intercept

    n   = len(df_r)
    t_c = scipy_stats.t.ppf(0.975, df=n - 2)
    x_m = df_r[col_x].mean()
    s_e = np.sqrt(np.sum((df_r[col_y] - (slope * df_r[col_x] + intercept)) ** 2) / (n - 2))
    ci  = t_c * s_e * np.sqrt(1/n + (x_line - x_m)**2 / np.sum((df_r[col_x] - x_m)**2))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_to_list(df_r[col_x]), y=_to_list(df_r[col_y]),
        mode='markers', name='Data',
        marker=dict(color=PALETTE[0], size=6, opacity=0.6),
        hovertemplate=f'{col_x}: %{{x:.2f}}<br>{col_y}: %{{y:.2f}}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=x_line.tolist(), y=y_line.tolist(),
        mode='lines', name=f'OLS (R²={r**2:.3f})',
        line=dict(color=PALETTE[3], width=2.5),
    ))
    ci_x = np.concatenate([x_line, x_line[::-1]])
    ci_y = np.concatenate([y_line + ci, (y_line - ci)[::-1]])
    fig.add_trace(go.Scatter(
        x=ci_x.tolist(), y=ci_y.tolist(),
        fill='toself', fillcolor='rgba(238,93,80,0.10)',
        line=dict(color='rgba(0,0,0,0)'),
        name='95% CI',
    ))
    fig.update_layout(_layout(
        title=f' {CHART_LABELS["regression_plot"]}: {col_x} → {col_y} | R²={r**2:.3f}',
        xaxis_title=col_x,
        yaxis_title=col_y,
    ))
    return _json(_axes(fig))


def _chart_bubble_chart(df, col_x, col_y, col_z):
    df_b = df[[col_x, col_y, col_z]].dropna()
    if df_b.empty:
        return None
    size_range = float(df_b[col_z].max()) - float(df_b[col_z].min())
    if size_range == 0:
        size_scaled = [20] * len(df_b)
    else:
        size_scaled = ((df_b[col_z] - df_b[col_z].min()) / size_range * 35 + 5).tolist()
    fig = go.Figure(go.Scatter(
        x=_to_list(df_b[col_x]), y=_to_list(df_b[col_y]),
        mode='markers',
        marker=dict(
            size=size_scaled,
            color=PALETTE[0], opacity=0.65,
            line=dict(width=0.5, color='white'),
            sizemode='diameter',
        ),
        hovertemplate=f'{col_x}: %{{x:.2f}}<br>{col_y}: %{{y:.2f}}<br>{col_z}: %{{marker.size:.1f}}<extra></extra>',
    ))
    fig.update_layout(_layout(
        title=f' {CHART_LABELS["bubble_chart"]}: {col_x} × {col_y} (size={col_z})',
        xaxis_title=col_x,
        yaxis_title=col_y,
    ))
    return _json(_axes(fig))


# ─── d) CATEGORICAL vs NUMERICAL ─────────────────────────────────────────────

def _chart_box_cat_num(df, cat_col, num_col):
    top = df[cat_col].value_counts().head(8).index
    sub = df[df[cat_col].isin(top)]
    fig = px.box(
        sub, x=cat_col, y=num_col, color=cat_col,
        color_discrete_sequence=PALETTE,
        title=f' {CHART_LABELS["box_cat_num"]}: {num_col} by {cat_col}',
        points='outliers',
    )
    fig.update_layout(_layout(showlegend=False))
    return _json(_axes(fig))


def _chart_violin_cat_num(df, cat_col, num_col):
    top = df[cat_col].value_counts().head(8).index
    sub = df[df[cat_col].isin(top)]
    fig = px.violin(
        sub, x=cat_col, y=num_col, color=cat_col,
        color_discrete_sequence=PALETTE, box=True, points='outliers',
        title=f' {CHART_LABELS["violin_cat_num"]}: {num_col} by {cat_col}',
    )
    fig.update_layout(_layout(showlegend=False))
    return _json(_axes(fig))


def _chart_grouped_bar(df, cat_col, num_col):
    grp = df.groupby(cat_col)[num_col].mean().head(12).sort_values(ascending=False)
    fig = go.Figure(go.Bar(
        x=grp.index.astype(str).tolist(),
        y=grp.values.tolist(),         # FIX: .tolist()
        marker_color=PALETTE[1], opacity=0.9,
        hovertemplate='%{x}<br>Mean: %{y:,.2f}<extra></extra>',
    ))
    fig.update_layout(_layout(title=f' {CHART_LABELS["grouped_bar"]}: Mean {num_col} by {cat_col}'))
    return _json(_axes(fig))


def _chart_strip_plot(df, cat_col, num_col):
    top = df[cat_col].value_counts().head(10).index
    sub = df[df[cat_col].isin(top)]
    fig = px.strip(
        sub, x=cat_col, y=num_col,
        color_discrete_sequence=[PALETTE[0]],
        title=f' {CHART_LABELS["strip_plot"]}: {num_col} by {cat_col}',
    )
    fig.update_layout(_layout(showlegend=False))
    return _json(_axes(fig))


# ─── e) COMPARISON ───────────────────────────────────────────────────────────

def _chart_violin_compare(df, num_cols):
    cols = [c for c in num_cols if c in df.columns]
    if not cols:
        return None
    fig = go.Figure()
    for i, col in enumerate(cols[:8]):
        fig.add_trace(go.Violin(
            y=_to_list(df[col].dropna()), name=col,
            line_color=PALETTE[i % len(PALETTE)],
            fillcolor=PALETTE[i % len(PALETTE)],
            opacity=0.75, box_visible=True, meanline_visible=True,
            hovertemplate=f'{col}: %{{y:.2f}}<extra></extra>',
        ))
    suffix = ', '.join(cols[:4]) + ('…' if len(cols) > 4 else '')
    fig.update_layout(_layout(title=f' {CHART_LABELS["violin_compare"]} — {suffix}'))
    return _json(_axes(fig))


def _chart_grouped_bar_compare(df, num_cols):
    cols = [c for c in num_cols if c in df.columns][:10]
    if not cols:
        return None
    means = []
    stds  = []
    valid_cols = []
    for c in cols:
        try:
            s = sanitize_series(df[c], c)
            if not s.empty:
                means.append(float(s.mean()))
                stds.append(float(s.std()) if len(s) >= 2 else 0.0)
                valid_cols.append(c)
        except Exception:
            pass
    if not valid_cols:
        return None
    suffix = ', '.join(valid_cols[:4]) + ('…' if len(valid_cols) > 4 else '')
    fig = go.Figure(go.Bar(
        x=valid_cols, y=means,
        error_y=dict(
            type='data', array=stds, visible=True,
            color='rgba(200,216,240,0.6)', thickness=1.5, width=6,
        ),
        marker_color=PALETTE[0], opacity=0.9,
        hovertemplate='%{x}<br>Mean: %{y:,.3f}<extra></extra>',
    ))
    fig.update_layout(_layout(title=f' {CHART_LABELS["grouped_bar_compare"]} — {suffix}'))
    return _json(_axes(fig))


def _chart_parallel_coords(df, num_cols):
    cols = [c for c in num_cols if c in df.columns][:6]
    if not cols:
        return None
    sub  = df[cols].dropna()
    if sub.empty:
        return None
    sub  = sub.sample(min(500, len(sub)), random_state=42)
    dims = [dict(label=c, values=sub[c].tolist()) for c in cols]
    color_vals = list(range(len(sub)))
    fig = go.Figure(go.Parcoords(
        line=dict(
            color=color_vals,
            colorscale=[[0, PALETTE[0]], [0.5, PALETTE[4]], [1, PALETTE[3]]],
            showscale=True,
            colorbar=dict(title='Index', thickness=12, tickfont=dict(color=_cfg()['font_color'], size=9)),
        ),
        dimensions=dims,
        unselected=dict(line=dict(opacity=0.15)),
    ))
    fig.update_layout(_layout(title=f' {CHART_LABELS["parallel_coords"]} — Multivariable Pattern'))
    return _json(fig)


def _chart_all_numerical(df, num_cols, chart_type):
    import math
    cols_to_plot = [c for c in num_cols if c in df.columns]
    n_cols = len(cols_to_plot)
    if n_cols == 0:
        return None
    
    n_plot_cols = 2 if n_cols > 1 else 1
    n_plot_rows = math.ceil(n_cols / n_plot_cols)
    
    fig = make_subplots(
        rows=n_plot_rows, cols=n_plot_cols,
        subplot_titles=cols_to_plot,
        vertical_spacing=0.15 / max(1, n_plot_rows - 1) if n_plot_rows > 1 else 0.1,
    )
    
    for i, col in enumerate(cols_to_plot):
        r = (i // n_plot_cols) + 1
        c = (i % n_plot_cols) + 1
        clean = df[col].dropna()
        if clean.empty:
            continue
        
        color = PALETTE[i % len(PALETTE)]
        
        if chart_type == 'boxplot':
            fig.add_trace(go.Box(
                y=_to_list(clean), name=col,
                marker_color=color, boxmean='sd',
                hovertemplate=f'{col}: %{{y:.2f}}<extra></extra>',
            ), row=r, col=c)
        elif chart_type == 'violin':
            fig.add_trace(go.Violin(
                y=_to_list(clean), name=col,
                fillcolor=color, line_color=color,
                box_visible=True, meanline_visible=True, opacity=0.8,
                hovertemplate=f'{col}: %{{y:.2f}}<extra></extra>',
            ), row=r, col=c)
        elif chart_type == 'density':
            if len(clean) >= 3:
                kde_x = np.linspace(float(clean.min()), float(clean.max()), 100)
                kde = scipy_stats.gaussian_kde(clean)
                fig.add_trace(go.Scatter(
                    x=kde_x.tolist(), y=(kde(kde_x)).tolist(),
                    fill='tozeroy', mode='lines',
                    line=dict(color=color, width=2),
                    name=col,
                    hovertemplate='%{x:.2f}<br>Density: %{y:.4f}<extra></extra>',
                ), row=r, col=c)
        elif chart_type == 'qq':
            if len(clean) >= 4:
                (osm, osr), (slope, intercept, _) = scipy_stats.probplot(clean, dist='norm')
                fig.add_trace(go.Scatter(
                    x=osm.tolist(), y=osr.tolist(), mode='markers',
                    marker=dict(color=color, size=4, opacity=0.6),
                    name=f'{col} Points',
                    showlegend=False,
                ), row=r, col=c)
                x_line = np.array([osm.min(), osm.max()])
                fig.add_trace(go.Scatter(
                    x=x_line.tolist(), y=(slope * x_line + intercept).tolist(),
                    mode='lines', line=dict(color='#FF7A00', dash='dash', width=1.5),
                    name=f'{col} Ref',
                    showlegend=False,
                ), row=r, col=c)
        else: # default histogram
            fig.add_trace(go.Histogram(
                x=_to_list(clean), nbinsx=20,
                marker_color=color, opacity=0.8, name=col,
                hovertemplate='%{x}<br>Count: %{y}<extra></extra>',
            ), row=r, col=c)
            
    height = max(450, n_plot_rows * 300)
    fig.update_layout(_layout(
        title=f' Visualisasi Semua Variabel Numerik ({CHART_LABELS.get(chart_type, chart_type)})',
        height=height,
        showlegend=False,
    ))
    return _json(_axes(fig))


def _chart_all_categorical(df, cat_cols, chart_type):
    import math
    cols_to_plot = [c for c in cat_cols if c in df.columns]
    n_cols = len(cols_to_plot)
    if n_cols == 0:
        return None
        
    n_plot_cols = 2 if n_cols > 1 else 1
    n_plot_rows = math.ceil(n_cols / n_plot_cols)
    
    fig = make_subplots(
        rows=n_plot_rows, cols=n_plot_cols,
        subplot_titles=cols_to_plot,
        vertical_spacing=0.15 / max(1, n_plot_rows - 1) if n_plot_rows > 1 else 0.1,
    )
    
    for i, col in enumerate(cols_to_plot):
        r = (i // n_plot_cols) + 1
        c = (i % n_plot_cols) + 1
        
        vc = df[col].value_counts().head(10)
        if vc.empty:
            continue
            
        color = PALETTE[i % len(PALETTE)]
        
        if chart_type == 'pie':
            fig.add_trace(go.Pie(
                labels=vc.index.astype(str).tolist(),
                values=vc.values.tolist(),
                hole=0.4,
                name=col,
                showlegend=False,
            ), row=r, col=c)
        elif chart_type == 'count':
            vc_sorted = vc.sort_values()
            fig.add_trace(go.Bar(
                x=vc_sorted.values.tolist(),
                y=vc_sorted.index.astype(str).tolist(),
                orientation='h',
                marker_color=color, opacity=0.85, name=col,
                hovertemplate='%{y}<br>Count: %{x:,}<extra></extra>',
            ), row=r, col=c)
        elif chart_type == 'pareto':
            cum = (vc.cumsum() / vc.sum() * 100)
            x_labels = vc.index.astype(str).tolist()
            fig.add_trace(go.Bar(
                x=x_labels,
                y=vc.values.tolist(),
                marker_color=color, opacity=0.85,
                name=col,
            ), row=r, col=c)
            fig.add_trace(go.Scatter(
                x=x_labels,
                y=vc.values.tolist(),
                mode='lines+markers',
                line=dict(color='#FF7A00', width=1.5),
                showlegend=False,
            ), row=r, col=c)
        else: # default bar
            fig.add_trace(go.Bar(
                x=vc.index.astype(str).tolist(),
                y=vc.values.tolist(),
                marker_color=color, opacity=0.85, name=col,
                hovertemplate='%{x}<br>Count: %{y:,}<extra></extra>',
            ), row=r, col=c)
            
    height = max(450, n_plot_rows * 300)
    fig.update_layout(_layout(
        title=f' Visualisasi Semua Variabel Kategorik ({CHART_LABELS.get(chart_type, chart_type)})',
        height=height,
        showlegend=False,
    ))
    return _json(_axes(fig))


# ─── Time-Series Line Chart ──────────────────────────────────────────────────

def _resample_time_series(series, max_points=200):
    """
    Resampling otomatis untuk time-series agar line chart tetap bersih.
    - <50 points: return as-is
    - 50–500: resample per week (W)
    - 500–5000: resample per month (M)
    - >5000: resample per quarter (Q)
    Returns: (resampled_series, freq_label)
    """
    s = series.dropna()
    if len(s) == 0:
        return s, ''

    n = len(s)
    if n <= max_points:
        return s, f'{n} points'

    try:
        s_idx = s.copy()
        if not isinstance(s_idx.index, pd.DatetimeIndex):
            s_idx.index = pd.to_datetime(s_idx.index, errors='coerce')
            s_idx = s_idx[s_idx.index.notna()]

        if len(s_idx) > 5000:
            rule, label = 'QE', 'quarterly'
        elif len(s_idx) > 500:
            rule, label = 'ME', 'monthly'
        else:
            rule, label = 'W', 'weekly'

        resampled = s_idx.resample(rule).mean()
        return resampled, label
    except Exception:
        return s, f'{n} points (no resample)'


def _chart_line(df, col_x, col_y=None):
    """
    Line chart untuk time-series.
    col_x: column datetime
    col_y: column numerik (opsional; default = count per tanggal)
    """
    if col_x not in df.columns:
        return None

    ts_df = df[[col_x]].copy()
    ts_df.columns = ['x']
    ts_df = ts_df.dropna(subset=['x'])
    ts_df['x'] = pd.to_datetime(ts_df['x'], errors='coerce')
    ts_df = ts_df.dropna(subset=['x'])
    if ts_df.empty:
        return None

    if col_y and col_y in df.columns:
        ts_df['y'] = df.loc[ts_df.index, col_y].astype(float)
    else:
        ts_df['y'] = 1.0

    ts_df = ts_df.set_index('x')

    # Resample jika perlu
    n_unique = ts_df.index.nunique()
    if n_unique > 50:
        rule = 'ME' if n_unique > 500 else 'W'
        try:
            if col_y and col_y in df.columns:
                ts_df = ts_df.resample(rule).mean().dropna()
            else:
                ts_df = ts_df.resample(rule).size().to_frame('y')
        except Exception:
            pass

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_to_list(ts_df.index),
        y=_to_list(ts_df['y']),
        mode='lines',
        fill='tozeroy',
        fillcolor='rgba(78,205,196,0.12)',
        line=dict(color=PALETTE[0], width=2),
        hovertemplate='%{x}<br>%{y:,.2f}<extra></extra>',
    ))
    feq_label = {'ME': 'monthly', 'W': 'weekly'}.get(rule, '')
    title = f'Time Series — {col_x}'
    if col_y:
        title += f' / {col_y}'
    if feq_label:
        title += f' ({feq_label})'
    fig.update_layout(_layout(title=title))
    return _json(_axes(fig))


# ─── Smart Visualization Router ──────────────────────────────────────────────

def get_plot(df, col, time_series_cols=None, is_numeric=False):
    """
    Routing cerdas untuk menentukan jenis visualisasi berdasarkan tipe kolom.

    Rules:
      - TIME_SERIES (jika col ada di time_series_cols):
          Gunakan Line Chart. Resample otomatis jika >50 unique.
      - Bukan TIME_SERIES & nunique <= 10:
          Bar Chart (atau Pie Chart jika diminta).
      - Bukan TIME_SERIES & nunique > 10 & is_numeric:
          Histogram.
      - Bukan TIME_SERIES & nunique > 10 & not is_numeric:
          Bar Chart dengan top 10 kategori.

    Args:
        df: DataFrame
        col: Nama kolom
        time_series_cols: List kolom time-series (optional)
        is_numeric: True jika kolom numerik (optional, auto-detect if None)

    Returns:
        dict chart JSON atau None
    """
    if col not in df.columns:
        return None

    ts_set = set(time_series_cols or [])
    series = df[col]

    if is_numeric is None:
        is_numeric = pd.api.types.is_numeric_dtype(series)

    n_unique = series.nunique()

    # 1. TIME_SERIES → Line Chart (fallback ke Histogram/Bars jika gagal)
    if col in ts_set:
        result = _chart_line(df, col)
        if result is not None:
            return result
        # Fallthrough ke logic di bawah

    # 2. Low cardinality → Bar Chart
    if n_unique <= 10:
        return _chart_bar(df, col)

    # 3. High cardinality numeric → Histogram
    if is_numeric:
        return _chart_histogram(df, col)

    # 4. High cardinality categorical → Bar Chart (top 10)
    vc = series.value_counts().head(10)
    fig = go.Figure(go.Bar(
        x=vc.index.astype(str).tolist(),
        y=vc.values.tolist(),
        marker_color=PALETTE[0],
        opacity=0.9,
        hovertemplate='%{x}<br>Count: %{y:,}<extra></extra>',
    ))
    fig.update_layout(_layout(
        title=f' Top 10 Categories — {col}',
        xaxis_title=col,
        yaxis_title='Count',
    ))
    return _json(_axes(fig))


# ─── PNG Export Helper ───────────────────────────────────────────────────────

def save_figure(fig_or_json, save_path, width=700, height=400, scale=2):
    """
    Convert a Plotly figure (or JSON dict) to a PNG image and save to disk.
    Used by both dashboard and PDF to ensure identical chart rendering.
    """
    if isinstance(fig_or_json, dict):
        fig = pio.from_json(json.dumps(fig_or_json), skip_invalid=True)
    else:
        fig = fig_or_json
    fig.update_layout(
        width=width, height=height,
        margin=dict(l=60, r=30, t=50, b=50),
        font=dict(size=10),
    )
    fig.update_xaxes(title_font=dict(size=11), tickfont=dict(size=9))
    fig.update_yaxes(title_font=dict(size=11), tickfont=dict(size=9))
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    pio.write_image(fig, save_path, format='png', scale=scale)
    return save_path


# ─── Unified Single-Column Plot Generator ────────────────────────────────────

def generate_plot(df, column, chart_type='auto', num_cols=None, cat_cols=None,
                  save_path=None, theme='light', width=700, height=400):
    """
    Generate a Plotly chart for a single column, auto-detecting chart type.
    Both dashboard and PDF use this function for consistent output.

    Parameters:
        df         : DataFrame (must be the cleaned version)
        column     : Column name to plot
        chart_type : 'auto' | 'histogram' | 'boxplot' | 'bar' | 'pie' | 'line'
        num_cols   : List of numeric column names (auto-detected if None)
        cat_cols   : List of categorical column names (auto-detected if None)
        save_path  : If provided, save PNG to this path
        theme      : 'light' (PDF) or 'dark' (dashboard)
        width,height : Figure dimensions in pixels

    Returns:
        Plotly Figure object, or None if chart cannot be generated
    """
    set_theme(theme)

    if num_cols is None or cat_cols is None:
        from backend.preprocessing import detect_data_types
        num_cols, cat_cols = detect_data_types(df)

    if chart_type == 'auto':
        in_num = column in (num_cols or [])
        in_cat = column in (cat_cols or [])
        if in_num:
            chart_type = 'histogram'
        elif in_cat:
            chart_type = 'bar'
        else:
            chart_type = 'histogram'

    builders = {
        'histogram': lambda: _chart_histogram(df, column),
        'boxplot'  : lambda: _chart_boxplot(df, column),
        'bar'      : lambda: _chart_bar(df, column),
        'pie'      : lambda: _chart_pie(df, column),
        'line'     : lambda: _chart_line(df, column),
    }
    builder = builders.get(chart_type)
    if builder is None:
        return None

    chart_json = builder()
    if chart_json is None:
        return None

    fig = pio.from_json(json.dumps(chart_json), skip_invalid=True)
    fig.update_layout(width=width, height=height)

    if save_path:
        save_figure(fig, save_path)

    return fig


# ─── VIZMASTER INSIGHT GENERATOR ────────────────────────────────────────────

def _generate_vizmaster_insights(chart_type, df, col_x=None, col_y=None, col_z=None, num_cols=None, cat_cols=None):
    """
    Generate visual insight dengan kerangka O-A-I (Observation → Analysis → Implication).
    Setiap insight item berisi:
      - observation:   fakta statistik yang terlihat
      - analysis:      mengapa hal itu terjadi / hubungan kausal
      - implication:   dampak terhadap pemodelan / keputusan
      - text:          ringkasan singkat (backward compat)
      - icon:          ikon FontAwesome
    """
    insights = []
    try:
        if chart_type in ('histogram', 'density') and col_x and col_x in df.columns:
            s = df[col_x].dropna()
            skew = s.skew()
            mean_v = s.mean()
            median_v = s.median()
            std_v = s.std()
            cv = (std_v / abs(mean_v) * 100) if mean_v != 0 else 0

            # ── Shape classification ──
            if abs(skew) < 0.5:
                shape_label = 'simetris'
                shape_desc = f'Distribusi {col_x} relatif simetris (skewness={skew:.3f}).'
                model_rec = 'Distribusi simetris mendukung penggunaan model parametrik seperti regresi linier tanpa transformasi.'
            elif skew > 0:
                shape_label = 'menceng kanan (positif)'
                shape_desc = f'Distribusi {col_x} menceng kanan (skewness={skew:.3f}) — mayoritas nilai rendah dengan ekor panjang ke kanan.'
                model_rec = 'Skewness positif menyarankan transformasi log atau Box-Cox sebelum regresi linier. Tree-based models (Random Forest, XGBoost) lebih toleran terhadap distribusi ini.'
            else:
                shape_label = 'menceng kiri (negatif)'
                shape_desc = f'Distribusi {col_x} menceng kiri (skewness={skew:.3f}) — mayoritas nilai tinggi dengan ekor panjang ke kiri.'
                model_rec = 'Skewness negatif sering kali dapat diperbaiki dengan refleksi + transformasi log, atau gunakan model non-parametrik.'

            insights.append({
                'icon': 'fa-chart-bar', 'text': shape_desc,
                'observation': shape_desc,
                'analysis': f'Coefficient of Variation (CV)={cv:.1f}% mengindikasikan '
                            f'{"variabilitas tinggi" if cv > 30 else "variabilitas moderat" if cv > 15 else "variabilitas rendah"}. '
                            f'Mean ({mean_v:.2f}) vs Median ({median_v:.2f}) menunjukkan '
                            f'{"adanya outlier atau skew" if abs(mean_v - median_v) / max(abs(mean_v), 0.001) > 0.1 else "distribusi yang relatif simetris"}.',
                'implication': model_rec,
            })

        elif chart_type in ('boxplot', 'violin') and col_x and col_x in df.columns:
            s = df[col_x].dropna()
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            n_out = ((s < q1 - 1.5*iqr) | (s > q3 + 1.5*iqr)).sum()
            out_pct = n_out / len(s) * 100 if len(s) > 0 else 0

            obs = f'Rentang interkuartil (IQR) {col_x}: {q1:.2f} – {q3:.2f}, mencakup 50% data tengah.'
            if n_out > 0:
                obs += f' Terdeteksi {n_out} outlier ({out_pct:.1f}% data).'
            else:
                obs += ' Tidak ada outlier terdeteksi berdasarkan metode IQR.'

            if out_pct > 5:
                ana = f'Proporsi outlier ({out_pct:.1f}%) cukup tinggi. Outlier dapat merepresentasikan kesalahan pengukuran, transaksi abnormal, atau distribusi heavy-tailed. Perlu validasi domain.'
                imp = 'Outlier pada tingkat ini dapat mengganggu regresi OLS, PCA, dan k-means. Gunakan robust scaling, winsorization, atau model berbasis tree (Random Forest, Gradient Boosting).'
            elif out_pct > 0:
                ana = f'Proporsi outlier ({out_pct:.1f}%) rendah. Kemungkinan merupakan variasi alami data.'
                imp = 'Dampak minimal terhadap sebagian besar model. Namun periksa leverage points pada regresi linear.'
            else:
                ana = 'Data tidak memiliki nilai ekstrem yang melampaui 1.5×IQR.'
                imp = 'Model sensitif terhadap outlier (OLS, PCA) dapat diterapkan tanpa preprocessing outlier khusus.'

            insights.append({
                'icon': 'fa-exclamation-triangle', 'text': obs,
                'observation': obs,
                'analysis': ana,
                'implication': imp,
            })

        elif chart_type == 'qq' and col_x and col_x in df.columns:
            s = df[col_x].dropna()
            obs = 'QQ plot membandingkan kuantil data terhadap kuantil distribusi normal teoritis.'
            if len(s) >= 8:
                _, pval = scipy_stats.shapiro(s)
                if pval > 0.05:
                    obs += f' Shapiro-Wilk p={pval:.4f} > 0.05 — data {col_x} tidak menyimpang signifikan dari normal.'
                    ana = 'Titik-titik pada QQ plot akan mengikuti garis referensi diagonal. Normalitas terpenuhi.'
                    imp = 'Parametric tests (t-test, ANOVA, Pearson, OLS) dan model yang mengasumsikan normalitas dapat digunakan tanpa transformasi.'
                else:
                    obs += f' Shapiro-Wilk p={pval:.4f} ≤ 0.05 — data {col_x} menyimpang signifikan dari normal.'
                    ana = 'Penyimpangan dari garis diagonal pada QQ plot (terutama di ujung-ujung) mengindikasikan ekor distribusi yang tidak normal.'
                    imp = 'Gunakan non-parametric tests (Spearman, Mann-Whitney) atau transformasi data (log, Box-Cox, Yeo-Johnson). Untuk regresi, robust standard errors disarankan.'
                insights.append({
                    'icon': 'fa-check' if pval > 0.05 else 'fa-times', 'text': obs,
                    'observation': obs,
                    'analysis': ana,
                    'implication': imp,
                })
            else:
                insights.append({
                    'icon': 'fa-chart-line', 'text': obs,
                    'observation': obs,
                    'analysis': 'Jumlah sampel terlalu kecil (<8) untuk uji normalitas yang andal.',
                    'implication': 'Interpretasi normalitas dilakukan secara visual saja. Pertimbangkan collect more data.',
                })

        elif chart_type in ('bar', 'pie', 'count') and col_x and col_x in df.columns:
            vc = df[col_x].value_counts()
            top = vc.index[0]; top_pct = (vc.iloc[0] / vc.sum()) * 100
            n_unique = df[col_x].nunique()

            obs = f'"{top}" adalah kategori terbanyak ({top_pct:.1f}% dari {n_unique} kategori).'
            if len(vc) >= 3:
                bot = vc.index[-1]; bot_pct = (vc.iloc[-1] / vc.sum()) * 100
                obs += f' Kategori paling sedikit: "{bot}" ({bot_pct:.1f}%).'
                ratio = top_pct / max(bot_pct, 0.01)
                obs += f' Rasio dominasi: {ratio:.1f}x.'

            if top_pct > 70:
                ana = f'Distribusi sangat timpang — kategori "{top}" mendominasi >70% observasi. Ketidakseimbangan ekstrem dapat menyebabkan model bias ke kelas mayoritas.'
                imp = 'Gunakan stratified cross-validation. Terapkan SMOTE/ADASYN untuk oversampling atau class_weight="balanced". Evaluasi dengan precision-recall/F1-score, bukan akurasi.'
            elif top_pct > 50:
                ana = f'Distribusi cukup timpang — kategori "{top}" mendominasi >50% observasi. Kelas minoritas berisiko diabaikan model.'
                imp = 'Pertimbangkan class weighting atau oversampling. Pantau recall per kelas selama evaluasi.'
            else:
                ana = 'Distribusi kategori relatif merata — tidak ada dominasi signifikan.'
                imp = 'Model klasifikasi standar cocok digunakan. Accuracy adalah metrik valid untuk data seimbang.'

            insights.append({
                'icon': 'fa-crown' if top_pct > 50 else 'fa-balance-scale', 'text': obs,
                'observation': obs,
                'analysis': ana,
                'implication': imp,
            })

        elif chart_type == 'pareto' and col_x and col_x in df.columns:
            vc = df[col_x].value_counts()
            top3 = vc.iloc[:3].sum()
            total = vc.sum()
            pct = (top3 / total) * 100
            obs = f'3 kategori teratas mencakup {pct:.1f}% dari total ({top3}/{total}).'
            ana = f'Prinsip Pareto (80/20): {pct:.1f}% dampak berasal dari kategori minoritas. Identifikasi kategori dengan kontribusi terbesar untuk optimasi.'
            imp = 'Fokus rekayasa fitur dan analisis pada kategori-kategori dominan. Pertimbangkan penggabungan kategori minoritas ke dalam bucket "Lainnya" untuk menyederhanakan model.'
            insights.append({
                'icon': 'fa-chart-pie', 'text': obs,
                'observation': obs, 'analysis': ana, 'implication': imp,
            })

        elif chart_type == 'scatter' and col_x and col_y and col_x in df.columns and col_y in df.columns:
            valid = df[[col_x, col_y]].dropna()
            if len(valid) >= 4:
                r = valid[col_x].corr(valid[col_y])
                direction = 'positif' if r > 0 else 'negatif'
                strength = 'sangat kuat' if abs(r) > 0.8 else 'kuat' if abs(r) > 0.6 else 'sedang' if abs(r) > 0.4 else 'lemah'
                r2 = r**2
                obs = f'Korelasi {strength} {direction} antara {col_x} & {col_y} (r={r:.3f}, R²={r2:.3f}).'
                n_total = len(df)
                n_valid = len(valid)
                if n_valid < n_total:
                    obs += f' {n_total - n_valid} baris dihapus karena missing.'

                if abs(r) > 0.7:
                    ana = f'Korelasi kuat ({abs(r):.3f}) mengindikasikan hubungan linier yang erat. {col_x} dan {col_y} berbagi {r2*100:.1f}% varians.'
                    imp = f'Jika kedua variabel akan digunakan sebagai prediktor, waspadai multikolinearitas (VIF>5). Pertimbangkan untuk hanya menggunakan salah satu, atau terapkan PCA/Ridge regression.'
                elif abs(r) > 0.4:
                    ana = f'Korelasi moderat ({abs(r):.3f}). Terdapat hubungan linier namun tidak dominan. {r2*100:.1f}% varians bersama.'
                    imp = 'Kedua variabel umumnya dapat dimasukkan bersama dalam model tanpa risiko multikolinearitas signifikan.'
                else:
                    ana = f'Korelasi lemah ({abs(r):.3f}). Hanya {r2*100:.1f}% varians bersama — hubungan linier minimal.'
                    imp = 'Kedua variabel memberikan informasi yang largely independent. Dapat digunakan bersama tanpa khawatir redundansi.'

                insights.append({
                    'icon': 'fa-link', 'text': obs,
                    'observation': obs, 'analysis': ana, 'implication': imp,
                })

        elif chart_type in ('heatmap', 'heatmap_all', 'scatter_matrix') and num_cols and len(num_cols) >= 2:
            corr = df[num_cols].corr()
            max_pair = None; max_val = 0
            for i, c1 in enumerate(num_cols):
                for c2 in num_cols[i+1:]:
                    v = abs(corr.loc[c1, c2])
                    if v > max_val: max_val = v; max_pair = (c1, c2)

            if max_pair:
                r_val = corr.loc[max_pair[0], max_pair[1]]
                direction = 'positif' if r_val > 0 else 'negatif'
                strength = 'sangat kuat' if max_val > 0.8 else 'kuat' if max_val > 0.6 else 'sedang' if max_val > 0.4 else 'lemah'
                r2 = r_val**2
                obs = f'Korelasi {strength} {direction} antara {max_pair[0]} & {max_pair[1]} (r={max_val:.3f}). R²={r2:.3f} — {r2*100:.1f}% varians bersama.'

                if max_val > 0.7:
                    ana = f'Korelasi tinggi ({max_val:.3f}) menimbulkan risiko multikolinearitas jika kedua variabel digunakan bersama dalam model regresi. Identifikasi apakah salah satu merupakan turunan dari yang lain.'
                    imp = f'Langkah yang disarankan: (1) Hitung VIF — jika >10, hapus salah satu; (2) Terapkan Ridge atau Lasso regression; (3) Gunakan PCA untuk mengortogonalisasi prediktor.'
                elif max_val > 0.4:
                    ana = f'Korelasi moderat ({max_val:.3f}) — hubungan linier cukup berarti namun tidak mengkhawatirkan untuk multikolinearitas.'
                    imp = 'Kedua variabel umumnya aman digunakan bersama. Tetap monitor VIF sebagai langkah precautionary.'
                else:
                    ana = f'Korelasi lemah ({max_val:.3f}) — tidak ada hubungan linier yang berarti.'
                    imp = 'Tidak ada risiko multikolinearitas dari pasangan ini. Kedua variabel memberikan informasi independen.'

                insights.append({
                    'icon': 'fa-link', 'text': obs,
                    'observation': obs, 'analysis': ana, 'implication': imp,
                })

            # Count high-correlation pairs for multicollinearity warning
            high_pairs = []
            cols_list = list(corr.columns)
            for i in range(len(cols_list)):
                for j in range(i + 1, len(cols_list)):
                    v = abs(corr.iloc[i, j])
                    if pd.notna(v) and v >= 0.7:
                        high_pairs.append((cols_list[i], cols_list[j], round(v, 3)))
            if len(high_pairs) >= 2:
                mc_obs = f'Terdeteksi {len(high_pairs)} pasangan dengan |r|≥0.7: ' + '; '.join([f'{a}↔{b}(r={v})' for a, b, v in high_pairs[:3]])
                if len(high_pairs) > 3:
                    mc_obs += f' (+{len(high_pairs)-3} lainnya).'
                insights.append({
                    'icon': 'fa-exclamation-triangle', 'text': mc_obs,
                    'observation': mc_obs,
                    'analysis': 'Multikolinearitas antar prediktor dapat menginflasi varians koefisien regresi dan membuat interpretasi tidak andal.',
                    'implication': 'Gunakan VIF-based feature selection, Regularized Regression (Ridge/Lasso), atau PCA sebelum pemodelan regresi.',
                })

        elif chart_type == 'regression_plot' and col_x and col_y and col_x in df.columns and col_y in df.columns:
            valid = df[[col_x, col_y]].dropna()
            if len(valid) >= 4:
                r = valid[col_x].corr(valid[col_y])
                slope = np.polyfit(valid[col_x], valid[col_y], 1)[0]
                trend = 'positif' if slope > 0 else 'negatif'
                r2 = r**2
                obs = f'Regresi {col_y} ~ {col_x}: slope={slope:.4f} (tren {trend}), r={r:.3f}, R²={r2:.3f}.'
                ana = f'Setiap kenaikan 1 unit {col_x} diikuti perubahan {col_y} sebesar {slope:.4f}. Model menjelaskan {r2*100:.1f}% varians {col_y}.'
                if abs(r) > 0.7:
                    imp = 'Hubungan linier kuat — regresi linier sederhana dapat menjadi model yang efektif. Validasi asumsi (normalitas residual, homoskedastisitas) sebelum digunakan untuk inferensi.'
                elif abs(r) > 0.4:
                    imp = 'Hubungan linier moderat — regresi linier berguna namun mungkin perlu variabel tambahan untuk meningkatkan prediktivitas.'
                else:
                    imp = 'Hubungan linier lemah — pertimbangkan transformasi variabel atau model non-linier (polynomial regression, splines).'
                insights.append({
                    'icon': 'fa-chart-line', 'text': obs,
                    'observation': obs, 'analysis': ana, 'implication': imp,
                })

        elif chart_type == 'bubble_chart' and col_x and col_y and col_z:
            valid = df[[col_x, col_y]].dropna()
            obs = f'Bubble chart: sumbu X={col_x}, Y={col_y}, ukuran gelembung={col_z}.'
            ana = ''
            imp = ''
            if len(valid) >= 4:
                r = valid[col_x].corr(valid[col_y])
                obs += f' Korelasi X-Y: r={r:.3f}.'
                if abs(r) > 0.5:
                    ana = f'Terdapat hubungan linier antara {col_x} dan {col_y}. Ukuran gelembung ({col_z}) menambah dimensi ketiga untuk analisis multivariat.'
                    imp = 'Gunakan bubble chart untuk identifikasi segmentasi atau outlier multivariat sebelum clustering atau pemodelan.'
                else:
                    ana = f'Hubungan antara {col_x} dan {col_y} lemah. Variabel mungkin independen.'
                    imp = 'Bubble chart membantu visualisasi 3 dimensi simultan — berguna untuk eksplorasi awal anteseden clustering.'
            insights.append({
                'icon': 'fa-circle', 'text': obs,
                'observation': obs, 'analysis': ana, 'implication': imp,
            })

        elif chart_type in ('box_cat_num', 'violin_cat_num', 'grouped_bar', 'strip_plot') and col_x and col_y:
            if col_x in df.columns and col_y in df.columns:
                valid = df[[col_x, col_y]].dropna()
                groups = valid.groupby(col_x)[col_y]
                means = groups.mean()
                stds = groups.std()
                top_g = means.idxmax(); bot_g = means.idxmin()
                top_v = means.max(); bot_v = means.min()
                ratio = top_v / bot_v if bot_v != 0 else float('inf')

                obs = f'Rata-rata {col_y} tertinggi pada kategori "{top_g}" ({top_v:.2f}), terendah pada "{bot_g}" ({bot_v:.2f}). Rasio: {ratio:.1f}x.'
                if ratio > 3:
                    ana = f'Perbedaan sangat signifikan (rasio {ratio:.1f}x) — kategori memiliki pengaruh besar terhadap {col_y}.'
                    imp = 'Kategorik ini merupakan kandidat kuat sebagai fitur dalam model. Pertimbangkan interaksi dengan variabel lain. Uji ANOVA untuk konfirmasi statistik.'
                elif ratio > 2:
                    ana = f'Perbedaan signifikan (rasio {ratio:.1f}x) — kategori memengaruhi {col_y}.'
                    imp = 'Fitur kategorik ini informatif untuk model prediktif. Pastikan encoding tepat (one-hot/label encoding sesuai algoritma).'
                else:
                    ana = f'Perbedaan kecil antar kategori — variabel kategorik mungkin tidak memberikan daya prediksi signifikan.'
                    imp = 'Pertimbangkan untuk tidak menyertakan fitur ini jika performa model tidak meningkat signifikan.'

                insights.append({
                    'icon': 'fa-layer-group', 'text': obs,
                    'observation': obs, 'analysis': ana, 'implication': imp,
                })

                # Standard deviation insight
                top_std_g = stds.idxmax() if len(stds) > 1 else None
                if top_std_g and stds.max() > 0:
                    obs2 = f'Variabilitas {col_y} tertinggi pada kategori "{top_std_g}" (std={stds.max():.2f}).'
                    ana2 = 'Standar deviasi tinggi dalam suatu kategori menunjukkan heterogenitas internal yang perlu dieksplorasi lebih lanjut.'
                    imp2 = 'Heteroskedastisitas antar kategori dapat memengaruhi asumsi regresi. Pertimbangkan weighted least squares atau robust standard errors.'
                    insights.append({
                        'icon': 'fa-ruler', 'text': obs2,
                        'observation': obs2, 'analysis': ana2, 'implication': imp2,
                    })

        elif chart_type in ('violin_compare', 'grouped_bar_compare') and num_cols and len(num_cols) >= 2:
            means_list = []
            for c in num_cols:
                if c in df.columns:
                    s = df[c].dropna()
                    if not s.empty:
                        means_list.append((c, float(s.mean()), float(s.std())))
            if means_list:
                sorted_m = sorted(means_list, key=lambda x: x[1], reverse=True)
                top_name, top_mean, top_std = sorted_m[0]
                bot_name, bot_mean, bot_std = sorted_m[-1]
                range_pct = ((top_mean - bot_mean) / max(abs(bot_mean), 0.001)) * 100

                obs = f'Nilai tertinggi: {top_name} ({top_mean:.2f}), terendah: {bot_name} ({bot_mean:.2f}). Rentang: {range_pct:.1f}%.'
                if range_pct > 200:
                    ana = f'Perbedaan sangat besar ({range_pct:.1f}%) antar variabel — indikasi perbedaan skala yang signifikan.'
                    imp = 'Standardisasi (Z-score) atau normalisasi (Min-Max) WAJIB sebelum analisis multivariat (PCA, clustering, regresi dengan banyak fitur).'
                elif range_pct > 50:
                    ana = f'Perbedaan cukup besar ({range_pct:.1f}%) — variabel memiliki skala yang berbeda.'
                    imp = 'Standardisasi disarankan untuk model berbasis jarak dan gradien (SVM, KNN, neural networks).'
                else:
                    ana = f'Perbedaan kecil ({range_pct:.1f}%) — variabel berada dalam skala yang relatif sama.'
                    imp = 'Standardisasi tidak kritis namun tetap disarankan untuk konsistensi.'

                insights.append({
                    'icon': 'fa-trophy', 'text': obs,
                    'observation': obs, 'analysis': ana, 'implication': imp,
                })

                # CV comparison
                cv_items = [(n, std/abs(m)*100 if m != 0 else 0) for n, m, std in means_list]
                max_cv = max(cv_items, key=lambda x: x[1])
                if max_cv[1] > 50:
                    cv_obs = f'Variabilitas tertinggi: {max_cv[0]} (CV={max_cv[1]:.1f}%) — sebaran data sangat lebar.'
                    cv_imp = 'Model tree-based umumnya lebih robust terhadap varians tinggi. Untuk model linier, pertimbangkan transformasi penstabil varians.'
                    insights.append({
                        'icon': 'fa-ruler-horizontal', 'text': cv_obs,
                        'observation': cv_obs,
                        'analysis': f'CV > 50% mengindikasikan ketidakstabilan yang dapat memengaruhi konvergensi model.',
                        'implication': cv_imp,
                    })

        elif chart_type == 'parallel_coords' and num_cols and len(num_cols) >= 2:
            obs = f'Parallel coordinates menampilkan {len(num_cols)} dimensi: {", ".join(num_cols[:5])}.'
            corr_m = df[num_cols].corr().abs().unstack().sort_values(ascending=False)
            corr_m = corr_m[corr_m < 1]
            if len(corr_m) > 0:
                top_pair = corr_m.index[0]
                r_top = corr_m.iloc[0]
                obs += f' Korelasi terkuat: {top_pair[0]} & {top_pair[1]} (r={r_top:.3f}).'
                ana = f'Parallel coordinates efektif untuk mengidentifikasi pola multivariat dan outlier di seluruh {len(num_cols)} dimensi.'
                imp = 'Gunakan untuk eksplorasi pola segmentasi sebelum clustering. Jika banyak garis saling overlapping, pertimbangkan subset fitur atau PCA.'
            else:
                ana = 'Visualisasi multidimensional untuk mengidentifikasi pola dan outlier.'
                imp = 'Berguna untuk eksplorasi anteseden clustering atau reduksi dimensi.'

            insights.append({
                'icon': 'fa-bezier-curve', 'text': obs,
                'observation': obs, 'analysis': ana, 'implication': imp,
            })

        elif chart_type == 'line' and col_x and col_x in df.columns:
            s = df[col_x].dropna()
            ts_df = df[[col_x]].copy()
            ts_df.columns = ['x']
            ts_df['x'] = pd.to_datetime(ts_df['x'], errors='coerce')
            ts_df = ts_df.dropna(subset=['x'])
            if col_y and col_y in df.columns:
                ts_df['y'] = df.loc[ts_df.index, col_y].astype(float)
            else:
                ts_df['y'] = 1.0
            ts_df = ts_df.set_index('x').sort_index()
            y_vals = ts_df['y'].values
            n = len(y_vals)
            if n >= 4:
                x_num = np.arange(n)
                slope, intercept, r, p, _ = scipy_stats.linregress(x_num, y_vals)
                direction = 'meningkat' if slope > 0 else 'menurun'
                sig_text = 'signifikan' if p < 0.05 else 'tidak signifikan'
                r2 = r ** 2
                cv = (np.std(y_vals) / abs(np.mean(y_vals)) * 100) if np.mean(y_vals) != 0 else 0
                vol_label = 'tinggi' if cv > 30 else ('sedang' if cv > 10 else 'rendah')
                date_min = str(ts_df.index.min())[:10]
                date_max = str(ts_df.index.max())[:10]
                val_min = float(ts_df['y'].min())
                val_max = float(ts_df['y'].max())
                peak_date = str(ts_df['y'].idxmax())[:10]
                trough_date = str(ts_df['y'].idxmin())[:10]
                change_pct = ((y_vals[-1] - y_vals[0]) / abs(y_vals[0]) * 100) if y_vals[0] != 0 else 0

                obs = (f'Data deret waktu dari {date_min} hingga {date_max} ({n} titik). '
                       f'Variabel menunjukkan tren {direction} dengan slope={slope:.4f} per periode, '
                       f'R²={r2:.3f} ({sig_text}, p={p:.4f}). '
                       f'Perubahan keseluruhan: {change_pct:+.1f}%. '
                       f'Nilai tertinggi {val_max:,.2f} pada {peak_date}, terendah {val_min:,.2f} pada {trough_date}. '
                       f'CV={cv:.1f}% (volatilitas {vol_label}).')
                ana = (f'Tren yang {direction} {"signifikan" if p < 0.05 else "belum signifikan"} ini '
                       f'mengindikasikan pola {"pergerakan konsisten" if abs(slope) > 0.01 else "stabil"} '
                       f'selama periode pengamatan. '
                       f'R² sebesar {r2:.3f} menunjukkan bahwa model linier dapat menjelaskan '
                       f'{r2*100:.1f}% variasi data. '
                       f'Volatilitas {vol_label} (CV={cv:.1f}%) {"perlu diwaspadai karena fluktuasi besar" if cv > 30 else "masih dalam batas toleransi"}.')
                imp_parts = []
                if abs(slope) > 0.001:
                    imp_parts.append('Gunakan model yang menangani tren dan musiman (SARIMA, Prophet, LSTM) untuk peramalan.')
                else:
                    imp_parts.append('Data relatif stasioner — model rata-rata atau simple exponential smoothing mungkin memadai.')
                if cv > 30:
                    imp_parts.append('Volatilitas tinggi mengindikasikan perlunya transformasi stabilisasi varians (Box-Cox) sebelum pemodelan.')
                if abs(change_pct) > 20:
                    imp_parts.append(f'Perubahan keseluruhan {change_pct:+.1f}% memerlukan perhatian khusus dalam konteks bisnis.')
                imp = ' '.join(imp_parts)
            else:
                obs = f'Titik data terlalu sedikit ({n}) untuk analisis tren yang bermakna.'
                ana = 'Data dengan kurang dari 4 titik tidak cukup untuk regresi linier yang andal.'
                imp = 'Kumpulkan lebih banyak data atau gunakan pendekatan kualitatif untuk pengambilan keputusan.'

            insights.append({
                'icon': 'fa-chart-line', 'text': obs,
                'observation': obs, 'analysis': ana, 'implication': imp,
            })

    except Exception:
        insights.append({
            'icon': 'fa-brain', 'text': 'Insight tidak tersedia untuk chart ini.',
            'observation': '', 'analysis': '', 'implication': '',
        })
    if not insights:
        insights.append({
            'icon': 'fa-brain', 'text': 'Data tersedia untuk dieksplorasi lebih lanjut.',
            'observation': '', 'analysis': '', 'implication': '',
        })
    return insights


# ─── MASTER ENTRY POINT ──────────────────────────────────────────────────────

def generate_master_chart(df, num_cols, cat_cols, category, chart_type,
                          col_x=None, col_y=None, col_z=None, theme='dark',
                          save_path=None):
    set_theme(theme)
    if not category_available(category, num_cols, cat_cols):
        return {
            'ok'         : False,
            'placeholder': PLACEHOLDERS.get(category, 'Dataset tidak kompatibel.'),
            'kpis'       : [],
        }

    types = CATEGORY_CHARTS.get(category, [])
    if not chart_type or chart_type not in types:
        chart_type = types[0] if types else None
    if not chart_type:
        return {'ok': False, 'placeholder': 'Tidak ada tipe grafik.', 'kpis': []}

    if category in ('numerical', 'categorical') and not col_x:
        col_x = num_cols[0] if category == 'numerical' else cat_cols[0]

    if category == 'bivariate':
        col_x = col_x or (num_cols[0] if num_cols else None)
        col_y = col_y or (num_cols[1] if len(num_cols) > 1 else num_cols[0])
        col_z = col_z or (num_cols[2] if len(num_cols) > 2 else num_cols[0])

    if category == 'catnum':
        # Default jika belum ada
        if not col_x or col_x not in df.columns:
            col_x = cat_cols[0] if cat_cols else None
        if not col_y or col_y not in df.columns:
            col_y = num_cols[0] if num_cols else None
        # Smart swap: builder butuh (cat_col, num_col)
        # Jika user pilih X=numeric dan Y=categorical → swap dulu
        x_is_num = (col_x in num_cols) if col_x else False
        y_is_cat = (col_y in cat_cols) if col_y else False
        if x_is_num and y_is_cat:
            col_x, col_y = col_y, col_x
        # Fallback: jika keduanya numeric → X = cat[0]
        if col_x in num_cols and col_y in num_cols:
            col_x = cat_cols[0] if cat_cols else col_x
        # Fallback: jika keduanya categorical → Y = num[0]
        if col_x in cat_cols and col_y in cat_cols:
            col_y = num_cols[0] if num_cols else col_y

    if category == 'compare':
        # col_x bisa berisi comma-separated kolom yang dipilih user
        # Contoh: "age,salary,score" → pakai sebagai subset num_cols
        if col_x:
            selected = [c.strip() for c in col_x.split(',')
                        if c.strip() in df.columns and c.strip() in num_cols]
            if selected:
                num_cols = selected

    if col_x == '__all__':
        try:
            if category == 'numerical':
                chart = _chart_all_numerical(df, num_cols, chart_type)
                kpis = [
                    {'label': 'Numerical Cols', 'value': str(len(num_cols)), 'icon': 'fa-columns'},
                    {'label': 'Total Rows', 'value': f'{len(df):,}', 'icon': 'fa-list'},
                    {'label': 'Missing Cells', 'value': f'{int(df[num_cols].isna().sum().sum()):,}', 'icon': 'fa-exclamation'},
                ]
            elif category == 'categorical':
                chart = _chart_all_categorical(df, cat_cols, chart_type)
                kpis = [
                    {'label': 'Categorical Cols', 'value': str(len(cat_cols)), 'icon': 'fa-columns'},
                    {'label': 'Total Rows', 'value': f'{len(df):,}', 'icon': 'fa-list'},
                    {'label': 'Missing Cells', 'value': f'{int(df[cat_cols].isna().sum().sum()):,}', 'icon': 'fa-exclamation'},
                ]
            else:
                chart = None
                kpis = []
            
            if chart is None:
                return {
                    'ok'         : False,
                    'placeholder': f'Gagal membuat grafik untuk semua variabel.',
                    'kpis'       : kpis,
                }
            
            # Save as PNG if requested
            saved_to = None
            if save_path and isinstance(save_path, str):
                save_figure(chart, save_path)
                saved_to = save_path
            elif save_path is True:
                safe = "".join(c for c in f"{category}_{chart_type}_all" if c.isalnum() or c in ('_', '-'))
                saved_to = os.path.join('frontend', 'static', 'temp_plots', f"{safe}.png")
                save_figure(chart, saved_to)

            idx = types.index(chart_type)
            ins = _generate_vizmaster_insights(chart_type, df, col_x=col_x, col_y=col_y, col_z=col_z, num_cols=num_cols, cat_cols=cat_cols)
            return {
                'ok'          : True,
                'chart'       : chart,
                'kpis'        : kpis,
                'chart_type'  : chart_type,
                'chart_label' : CHART_LABELS.get(chart_type, chart_type),
                'chart_index' : idx,
                'chart_total' : len(types),
                'col_x'       : col_x,
                'col_y'       : col_y,
                'col_z'       : col_z,
                'save_path'   : saved_to,
                'insights'    : ins,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'ok'         : False,
                'placeholder': f'Gagal membuat grafik semua variabel: {str(e)}',
                'kpis'       : [],
            }

    def _valid(c):
        return c and c in df.columns

    try:
        builders = {
            'histogram'           : lambda: _chart_histogram(df, col_x) if _valid(col_x) else None,
            'boxplot'             : lambda: _chart_boxplot(df, col_x) if _valid(col_x) else None,
            'density'             : lambda: _chart_density(df, col_x) if _valid(col_x) else None,
            'qq'                  : lambda: _chart_qq(df, col_x) if _valid(col_x) else None,
            'violin'              : lambda: _chart_violin(df, col_x) if _valid(col_x) else None,
            'bar'                 : lambda: _chart_bar(df, col_x) if _valid(col_x) else None,
            'pie'                 : lambda: _chart_pie(df, col_x) if _valid(col_x) else None,
            'count'               : lambda: _chart_count(df, col_x) if _valid(col_x) else None,
            'pareto'              : lambda: _chart_pareto(df, col_x) if _valid(col_x) else None,
            'scatter'             : lambda: _chart_scatter(df, col_x, col_y) if _valid(col_x) and _valid(col_y) else None,
            'heatmap'             : lambda: _chart_heatmap(df, num_cols),
            'scatter_matrix'      : lambda: _chart_scatter_matrix(df, num_cols),
            'regression_plot'     : lambda: _chart_regression_plot(df, col_x, col_y) if _valid(col_x) and _valid(col_y) else None,
            'bubble_chart'        : lambda: _chart_bubble_chart(df, col_x, col_y, col_z) if _valid(col_x) and _valid(col_y) and _valid(col_z) else None,
            'box_cat_num'         : lambda: _chart_box_cat_num(df, col_x, col_y) if _valid(col_x) and _valid(col_y) else None,
            'violin_cat_num'      : lambda: _chart_violin_cat_num(df, col_x, col_y) if _valid(col_x) and _valid(col_y) else None,
            'line'                : lambda: _chart_line(df, col_x, col_y) if _valid(col_x) else None,
            'grouped_bar'         : lambda: _chart_grouped_bar(df, col_x, col_y) if _valid(col_x) and _valid(col_y) else None,
            'strip_plot'          : lambda: _chart_strip_plot(df, col_x, col_y) if _valid(col_x) and _valid(col_y) else None,
            'violin_compare'      : lambda: _chart_violin_compare(df, num_cols),
            'grouped_bar_compare' : lambda: _chart_grouped_bar_compare(df, num_cols),
            'parallel_coords'     : lambda: _chart_parallel_coords(df, num_cols),
            'heatmap_all'         : lambda: _chart_heatmap_all(df),
        }

        chart = builders[chart_type]()
        if chart is None:
            return {
                'ok'         : False,
                'placeholder': f'Data tidak cukup untuk membuat grafik "{CHART_LABELS.get(chart_type, chart_type)}".',
                'kpis'       : build_kpis(category, df, col_x, col_y, num_cols),
            }

        # Save as PNG if requested
        saved_to = None
        if save_path and isinstance(save_path, str):
            save_figure(chart, save_path)
            saved_to = save_path
        elif save_path is True:
            safe = "".join(c for c in f"{category}_{chart_type}" if c.isalnum() or c in ('_', '-'))
            saved_to = os.path.join('frontend', 'static', 'temp_plots', f"{safe}.png")
            save_figure(chart, saved_to)

        ins = _generate_vizmaster_insights(chart_type, df, col_x=col_x, col_y=col_y, col_z=col_z, num_cols=num_cols, cat_cols=cat_cols)
        idx = types.index(chart_type)
        return {
            'ok'          : True,
            'chart'       : chart,
            'kpis'        : build_kpis(category, df, col_x, col_y, num_cols),
            'chart_type'  : chart_type,
            'chart_label' : CHART_LABELS.get(chart_type, chart_type),
            'chart_index' : idx,
            'chart_total' : len(types),
            'col_x'       : col_x,
            'col_y'       : col_y,
            'col_z'       : col_z,
            'save_path'   : saved_to,
            'insights'    : ins,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'ok'         : False,
            'placeholder': f'Gagal membuat grafik: {str(e)}',
            'kpis'       : build_kpis(category, df, col_x, col_y, num_cols),
        }