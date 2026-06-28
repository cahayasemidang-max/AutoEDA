"""
backend/report_generator.py
─────────────────────────────────────────────────────────────────────────────
Comprehensive 11-Bab EDA PDF Report — Auto-EDA Dashboard (Kelompok 2 ITSB)

Structure:
  Halaman Judul  — LAPORAN ANALISIS DATA + metadata
  Bab I:    PENDAHULUAN (Sistem, dataset, status kebersihan — tabel)
  Bab II:   PENDAHULUAN & LATAR BELAKANG (Latar belakang, tujuan, ruang lingkup)
  Bab III:  DESKRIPSI & RINGKASAN DATASET (Metadata, tipe data, cuplikan)
  Bab IV:   KUALITAS DATA & DATA HEALTH (Status kolom: OK / Perlu Perhatian)
  Bab V:    STATISTIK DESKRIPTIF NUMERIK (Tabel + interpretasi)
  Bab VI:   STATISTIK DESKRIPTIF KATEGORIKAL (Tabel + interpretasi)
  Bab VII:  VISUALISASI DATA & INTERPRETASI (Histogram, Boxplot, Heatmap)
  Bab VII-A: ANALISIS TIME SERIES (jika tersedia)
  Bab VIII: PROSES DATA CLEANING (Dokumentasi tahapan)
  Bab IX:   TEMUAN KUNCI & INSIGHT OTOMATIS (Format O-A-I)
  Bab X:    REKOMENDASI STRATEGIS (R1–Rn)
  Bab XI:   PENUTUP (Kesimpulan, saran, pernyataan)

Dependencies: reportlab, matplotlib (optional fallback for images)
─────────────────────────────────────────────────────────────────────────────
"""

import os
import io
import datetime
import traceback

import pandas as pd
import numpy as np

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image as RLImage, KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas


# ─────────────────────────────────────────────────────────────────────────────
# NumberedCanvas — two-pass pattern for 'Page X of Y' + header/footer
# ─────────────────────────────────────────────────────────────────────────────

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that counts total pages and draws header/footer/watermark.
    Watermark: 'CONFIDENTIAL - Kelompok 2 ITSB' — transparent, diagonal.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_decorations(num_pages)
            super().showPage()
        super().save()

    def _draw_decorations(self, page_count):
        self.saveState()

        # ── Watermark (every page, behind content) ──────────────────────────
        self.setFont('Helvetica-Bold', 52)
        self.setFillColor(colors.Color(0.75, 0.75, 0.80, alpha=0.10))
        self.translate(306, 396)
        self.rotate(38)
        self.drawCentredString(0, 0, "CONFIDENTIAL")
        self.setFont('Helvetica', 14)
        self.setFillColor(colors.Color(0.75, 0.75, 0.80, alpha=0.12))
        self.drawCentredString(0, -42, "Kelompok 2 ITSB")
        self.rotate(-38)
        self.translate(-306, -396)

        # ── Header (pages 2+) ────────────────────────────────────────────────
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#a3aed0"))
        if self._pageNumber > 1:
            self.drawString(54, 750, "Auto-EDA Dashboard Report  —  Kelompok 2 ITSB")
            self.setStrokeColor(colors.HexColor("#e0e5f2"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)

        # ── Footer ───────────────────────────────────────────────────────────
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 40, page_text)
        self.drawString(
            54, 40,
            f"Auto-EDA Report | Generated: {datetime.datetime.now().strftime('%d %b %Y %H:%M')}"
        )
        self.setStrokeColor(colors.HexColor("#e0e5f2"))
        self.setLineWidth(0.5)
        self.line(54, 52, 558, 52)

        self.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# Defensive access helpers — never crash on missing/wrong-type keys
# ─────────────────────────────────────────────────────────────────────────────

def _safe_get(obj, key, default=None):
    """Safely get a key from a dict-like object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _safe_summary(quality_full):
    """Return the 'summary' sub-dict from quality_full, or empty dict."""
    return _safe_get(quality_full, 'summary', {})


def _safe_columns(quality_full):
    """Return the 'columns' list from quality_full, or empty list."""
    cols = _safe_get(quality_full, 'columns', [])
    return cols if isinstance(cols, list) else []


def _safe_warnings(quality_full):
    """Return the 'warnings' list from quality_full, or empty list."""
    warns = _safe_get(quality_full, 'warnings', [])
    return warns if isinstance(warns, list) else []


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers — load from path or generate with matplotlib fallback
# ─────────────────────────────────────────────────────────────────────────────

def _try_load_image(image_path, max_width=500, max_height=300):
    """
    Load an image file and return a ReportLab Image flowable,
    scaled proportionally to fit within max_width x max_height.
    Returns None on failure.
    """
    if not image_path or not os.path.isfile(image_path):
        return None
    try:
        from PIL import Image as PILImage
        pil_img = PILImage.open(image_path)
        w, h = pil_img.size
        if w == 0 or h == 0:
            return None
        scale = min(max_width / w, max_height / h, 1.0)
        return RLImage(image_path, width=w * scale, height=h * scale)
    except Exception:
        return None


def _generate_histogram_image(df, num_cols):
    """Generate a histogram PNG in memory using matplotlib; return BytesIO or None."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        col = num_cols[0] if num_cols else None
        if not col or col not in df.columns:
            return None

        series = pd.to_numeric(df[col], errors='coerce').dropna()
        if series.empty:
            return None

        fig, ax = plt.subplots(figsize=(6, 3.5), dpi=100)
        ax.hist(series, bins=25, color='#4ECDC4', edgecolor='white', alpha=0.85)
        ax.set_title(f'Histogram: {col}', fontsize=10, color='#1b254b')
        ax.set_xlabel(col, fontsize=8)
        ax.set_ylabel('Frequency', fontsize=8)
        ax.tick_params(labelsize=7)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        return None


def _generate_heatmap_image(df, num_cols):
    """Generate a correlation heatmap PNG in memory; return BytesIO or None."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        valid = [c for c in num_cols[:10] if c in df.columns]
        if len(valid) < 2:
            return None

        df_num = df[valid].apply(pd.to_numeric, errors='coerce').dropna()
        if df_num.empty or df_num.shape[1] < 2:
            return None

        corr = df_num.corr()
        fig, ax = plt.subplots(figsize=(6, 4.5), dpi=100)
        im = ax.imshow(corr.values, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
        ax.set_xticks(range(len(corr.columns)))
        ax.set_yticks(range(len(corr.columns)))
        ax.set_xticklabels(corr.columns, rotation=45, ha='right', fontsize=7)
        ax.set_yticklabels(corr.columns, fontsize=7)
        ax.set_title('Correlation Heatmap', fontsize=10, color='#1b254b')
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Styles
# ─────────────────────────────────────────────────────────────────────────────

def _build_styles():
    """Build and return all ParagraphStyle objects used in the report."""
    base = getSampleStyleSheet()

    def _make(name, **kw):
        return ParagraphStyle(name, parent=base['Normal'], **kw)

    return {
        'title': _make(
            'CoverTitle',
            fontName='Helvetica-Bold', fontSize=20, leading=24,
            textColor=colors.HexColor('#1b254b'), spaceAfter=6,
        ),
        'subtitle': _make(
            'CoverSubtitle',
            fontName='Helvetica', fontSize=11, leading=15,
            textColor=colors.HexColor('#4318ff'), spaceAfter=15,
        ),
        'h1': _make(
            'H1',
            fontName='Helvetica-Bold', fontSize=12, leading=15,
            textColor=colors.HexColor('#1b254b'), spaceBefore=14,
            spaceAfter=8, keepWithNext=True,
        ),
        'h2': _make(
            'H2',
            fontName='Helvetica-Bold', fontSize=10, leading=13,
            textColor=colors.HexColor('#4318ff'), spaceBefore=10,
            spaceAfter=5, keepWithNext=True,
        ),
        'body': _make(
            'Body',
            fontName='Helvetica', fontSize=8.5, leading=12,
            textColor=colors.HexColor('#4a5568'), spaceAfter=6,
        ),
        'th': _make(
            'TH',
            fontName='Helvetica-Bold', fontSize=8, leading=10,
            textColor=colors.white,
        ),
        'td': _make(
            'TD',
            fontName='Helvetica', fontSize=7.5, leading=9,
            textColor=colors.HexColor('#1b254b'),
        ),
        'warn': _make(
            'Warn',
            fontName='Helvetica', fontSize=8, leading=10,
            textColor=colors.HexColor('#856404'),
        ),
        'na': _make(
            'NA',
            fontName='Helvetica-Oblique', fontSize=8.5, leading=11,
            textColor=colors.HexColor('#a0aec0'), spaceAfter=4,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Table style presets
# ─────────────────────────────────────────────────────────────────────────────

HEADER_BG  = colors.HexColor('#111c44')
ALT_ROW    = [colors.white, colors.HexColor('#f8f9fa')]
GRID_COLOR = colors.HexColor('#e2e8f0')


def _header_table_style():
    return TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), HEADER_BG),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), ALT_ROW),
        ('GRID',          (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_pdf_report(
    dest_path,
    filename,
    df,
    quality_full,
    metrics,
    num_stats,
    cat_stats,
    auto_insights,
    cleaning_history,
    cleaning_summary,
    image_paths=None,
    img_paths=None,
    img_items=None,
    report_types=None,
    lang='id',
    ai_interpretation=None,
):
    """
    Generates a comprehensive 11-bab EDA PDF report:
      Bab I–XI sesuai struktur EDA Report (Pendahuluan s.d. Penutup).

    Parameters
    ----------
    dest_path      : str   — absolute output PDF path
    filename       : str   — dataset filename (for display)
    df             : pd.DataFrame — current (cleaned or raw) DataFrame
    quality_full   : dict  — from get_quality_report(); keys: summary, columns, warnings
    metrics        : dict  — from get_summary_metrics()
    num_stats      : list  — descriptive stats for numeric columns
    cat_stats      : list  — descriptive stats for categorical columns
    auto_insights  : list  — from generate_auto_insights()
    cleaning_history : list — cleaning pipeline labels
    cleaning_summary : dict — before/after cleaning metrics
    image_paths    : dict  — optional {'histogram': path, 'heatmap': path}
    """

    # ── Document setup ───────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        dest_path,
        pagesize=letter,
        leftMargin=54, rightMargin=54,
        topMargin=72,  bottomMargin=72,
    )

    S = _build_styles()
    story = []
    img_items = img_items or []

    # ── Helper: extract summary once ───────────────────────────────────────────
    summary      = _safe_summary(quality_full)
    needs_cleaning = summary.get('needs_cleaning', True)
    status_label = "RAW DATA (Perlu Pembersihan)" if needs_cleaning else "CLEAN DATA (Bersih)"
    status_color = "#e53e3e" if needs_cleaning else "#38a169"
    total_rows    = summary.get('total_rows',    _safe_get(metrics, 'total_rows',    len(df)))
    total_cols    = summary.get('total_cols',
                    summary.get('total_columns', _safe_get(metrics, 'total_columns', len(df.columns))))
    missing_cells = summary.get('missing_cells', 0)
    missing_pct   = summary.get('missing_pct',   0.0)
    duplicate_rows= summary.get('duplicate_rows',0)
    total_outliers= summary.get('total_outliers',0)

    # ── Confidentiality notice ──────────────────────────────────────────────────
    rahasia_note = (
        "<i>Dokumen ini bersifat <b>RAHASIA</b> dan hanya diperuntukkan bagi "
        "pihak-pihak yang berkepentingan. Dilarang memperbanyak, menyebarluaskan, "
        "atau mengutip sebagian atau seluruh isi dokumen ini tanpa izin tertulis "
        "dari Kelompok 2 Data Science ITSB.</i>"
    )

    # ── Filter TS vs non-TS images ─────────────────────────────────────────────
    ts_img_items   = [(p, l, x) for p, l, x in img_items if 'Time Series' in l]
    viz_img_items  = [(p, l, x) for p, l, x in img_items if 'Time Series' not in l]

    # ───────────────────────────────────────────────────────────────────────────
    # HALAMAN JUDUL
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Spacer(1, 80))
        story.append(Paragraph(
            "LAPORAN ANALISIS DATA",
            ParagraphStyle('CoverMain', fontName='Helvetica-Bold',
                           fontSize=22, leading=28, textColor=colors.HexColor('#1b254b'),
                           alignment=1, spaceAfter=8),
        ))
        story.append(Paragraph(
            "Dataset Quality, Descriptive Statistics<br/>&amp; Strategic Recommendations",
            ParagraphStyle('CoverSub', fontName='Helvetica', fontSize=12, leading=16,
                           textColor=colors.HexColor('#4318ff'), alignment=1, spaceAfter=30),
        ))
        # Garis pembatas
        line_data = [[Paragraph("", S['body'])]]
        line_t = Table(line_data, colWidths=[300])
        line_t.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, -1), 1.5, colors.HexColor('#4318ff')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(line_t)
        story.append(Spacer(1, 25))

        # Metadata
        meta_cover = [
            [Paragraph("<b>Nama File Dataset</b>", S['body']),
             Paragraph(f":  {filename}", S['body'])],
            [Paragraph("<b>Tanggal Analisis</b>", S['body']),
             Paragraph(f":  {datetime.datetime.now().strftime('%d %B %Y, %H:%M:%S')}", S['body'])],
            [Paragraph("<b>Penyusun</b>", S['body']),
             Paragraph(":  Kelompok 2 - Data Science, Institut Teknologi dan Sains Bandung", S['body'])],
        ]
        mt_c = Table(meta_cover, colWidths=[140, 364])
        mt_c.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(mt_c)
        story.append(Spacer(1, 40))

        story.append(Paragraph(rahasia_note, S['na']))
        story.append(PageBreak())
    except Exception:
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB I · PENDAHULUAN
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB I: PENDAHULUAN", S['h1']))
        story.append(Paragraph(
            "Bab ini memberikan gambaran umum mengenai sistem yang digunakan untuk menganalisis "
            "dataset, deskripsi singkat dataset yang dianalisis, serta status kebersihan data "
            "sebagai indikator kelayakan analisis lebih lanjut.",
            S['body']))
        story.append(Spacer(1, 10))

        # 1.1 Tentang Sistem
        story.append(Paragraph("1.1 Tentang Sistem", S['h2']))
        desc_web = (
            "<b>Auto-EDA Dashboard (DS Generator)</b> merupakan platform analisis data eksploratif "
            "otomatis berbasis web yang dikembangkan oleh <b>Kelompok 2 Data Science ITSB</b>. "
            "Sistem ini dirancang untuk membantu analis data, manajer, dan pengambil keputusan "
            "bisnis dalam melakukan serangkaian tugas analisis data secara terintegrasi, meliputi: "
            "(1) unggah dan validasi dataset, (2) audit kesehatan data (quality audit), "
            "(3) pembersihan data interaktif (data cleaning), (4) perhitungan statistik deskriptif "
            "dan lanjutan, (5) visualisasi pola data secara interaktif, serta (6) perumusan "
            "insight dan rekomendasi strategis berbasis data secara otomatis dan real-time."
        )
        story.append(Paragraph(desc_web, S['body']))
        story.append(Spacer(1, 8))

        # 1.2 Dataset yang Dianalisis
        story.append(Paragraph("1.2 Dataset yang Dianalisis", S['h2']))
        story.append(Paragraph(
            f"Dataset <b>{filename}</b> dianalisis pada "
            f"{datetime.datetime.now().strftime('%d %B %Y, %H:%M:%S')}. "
            f"Dataset ini memiliki <b>{total_rows:,}</b> baris (observasi) dan "
            f"<b>{total_cols}</b> kolom (variabel), yang terdiri dari "
            f"<b>{_safe_get(metrics, 'num_count', 0)}</b> variabel numerik dan "
            f"<b>{_safe_get(metrics, 'cat_count', 0)}</b> variabel kategorikal. "
            f"Berdasarkan hasil audit awal, status kebersihan data ditetapkan sebagai: "
            f"<font color='{status_color}'><b>{status_label}</b></font>.",
            S['body'])
        )
        story.append(Spacer(1, 8))

        # 1.3 Tim Pengembang
        story.append(Paragraph("1.3 Tim Pengembang", S['h2']))
        members = [
            [Paragraph("<b>Nama Lengkap</b>",            S['th']),
             Paragraph("<b>NIM</b>",                      S['th']),
             Paragraph("<b>Peran / Fokus Analisis</b>",   S['th'])],
            [Paragraph("Carol Dupino Pereira",           S['td']),
             Paragraph("52250051",                        S['td']),
             Paragraph("Descriptive & Advanced Statistics Engine", S['td'])],
            [Paragraph("Refantanur Husnul Haqib",        S['td']),
             Paragraph("52250052",                        S['td']),
             Paragraph("Visualizations & Dynamic Plotly Dashboard", S['td'])],
            [Paragraph("Cahaya Medina Semidang",         S['td']),
             Paragraph("52250053",                        S['td']),
             Paragraph("Data Preprocessing & Sanitizer Module", S['td'])],
            [Paragraph("Raihania Syah Putri",            S['td']),
             Paragraph("52250054",                        S['td']),
             Paragraph("Time Series Forecasting & Trends Panel", S['td'])],
            [Paragraph("Cloise Shafira",                 S['td']),
             Paragraph("52250044",                        S['td']),
             Paragraph("Smart Insights Generation Algorithm", S['td'])],
            [Paragraph("Adinda Adelia Futri",            S['td']),
             Paragraph("52250055",                        S['td']),
             Paragraph("Reporting System PDF/Excel & Security Sanitization", S['td'])],
        ]
        mt = Table(members, colWidths=[180, 100, 224])
        mt.setStyle(_header_table_style())
        story.append(mt)
        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab I tidak dapat dimuat]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB II · PENDAHULUAN & LATAR BELAKANG
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB II: PENDAHULUAN & LATAR BELAKANG", S['h1']))
        latar = (
            "Analisis data eksploratif (Exploratory Data Analysis — EDA) merupakan tahapan "
            "fundamental dalam setiap proyek data science. EDA bertujuan untuk memahami struktur, "
            "pola, anomali, dan karakteristik utama dari suatu dataset sebelum memasuki tahap "
            "pemodelan atau pengambilan keputusan lebih lanjut. Dengan pendekatan yang sistematis "
            "dan terstruktur, EDA memungkinkan para pemangku kepentingan untuk memperoleh wawasan "
            "berbasis data (data-driven insights) yang akurat dan relevan.<br/><br/>"
            "Laporan ini disusun secara otomatis oleh <b>Auto-EDA Dashboard (DS Generator)</b> "
            "sebagai bagian dari sistem analisis data terintegrasi. Seluruh proses — mulai dari "
            "unggah dataset, pembersihan data, komputasi statistik, hingga pembuatan visualisasi "
            "dan rekomendasi — dilakukan secara real-time melalui mesin backend berbasis Python "
            "dengan memanfaatkan library seperti Pandas, NumPy, Matplotlib, dan Plotly.<br/><br/>"
            "Tujuan utama dari laporan ini adalah menyajikan gambaran menyeluruh mengenai kualitas "
            "dan konten dataset yang dianalisis, sehingga pengambil keputusan dapat merumuskan "
            "strategi bisnis yang lebih tepat sasaran, berb pada data yang valid, bersih, dan "
            "terpercaya."
        )
        story.append(Paragraph(latar, S['body']))
        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab II tidak dapat dimuat]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB III · DESKRIPSI & RINGKASAN DATASET
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB III: DESKRIPSI & RINGKASAN DATASET", S['h1']))

        meta_info = [
            [Paragraph("<b>Nama File Dataset:</b>",        S['body']),
             Paragraph(filename,                            S['body'])],
            [Paragraph("<b>Waktu Analisis:</b>",           S['body']),
             Paragraph(datetime.datetime.now().strftime('%d %B %Y, %H:%M:%S'), S['body'])],
            [Paragraph("<b>Status Kebersihan:</b>",        S['body']),
             Paragraph(f"<font color='{status_color}'><b>{status_label}</b></font>", S['body'])],
            [Paragraph("<b>Total Baris (Observasi):</b>",  S['body']),
             Paragraph(str(total_rows),                     S['body'])],
            [Paragraph("<b>Total Kolom (Variabel):</b>",   S['body']),
             Paragraph(str(total_cols),                     S['body'])],
            [Paragraph("<b>Variabel Numerik:</b>",         S['body']),
             Paragraph(str(_safe_get(metrics, 'num_count', 0)), S['body'])],
            [Paragraph("<b>Variabel Kategorikal:</b>",     S['body']),
             Paragraph(str(_safe_get(metrics, 'cat_count', 0)), S['body'])],
        ]
        meta_table = Table(meta_info, colWidths=[150, 354])
        meta_table.setStyle(TableStyle([
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('LINEBELOW',     (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # KPI Box
        kpis = [
            [Paragraph("<b>Missing Cells</b>",   S['th']),
             Paragraph("<b>Duplicate Rows</b>",  S['th']),
             Paragraph("<b>IQR Outliers</b>",    S['th'])],
            [Paragraph(
                f"<font size=11 color='#2d3748'><b>{missing_cells}</b></font>"
                f"<br/><font size=7 color='#718096'>({missing_pct}%)</font>", S['body']),
             Paragraph(f"<font size=11 color='#2d3748'><b>{duplicate_rows}</b></font>", S['body']),
             Paragraph(f"<font size=11 color='#2d3748'><b>{total_outliers}</b></font>", S['body'])],
        ]
        kpi_table = Table(kpis, colWidths=[168, 168, 168])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX',           (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e0')),
            ('INNERGRID',     (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(kpi_table)
        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab III tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB IV · KUALITAS DATA & DATA HEALTH
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB IV: KUALITAS DATA & DATA HEALTH", S['h1']))
        story.append(Paragraph(
            "Bab ini menyajikan evaluasi menyeluruh terhadap kesehatan dan kualitas dataset. "
            "Bagian ini mencakup identifikasi permasalahan data, status setiap kolom, serta "
            "alur proses pembersihan yang diterapkan sistem untuk memastikan data layak analisis.",
            S['body']))
        story.append(Spacer(1, 8))

        # ── 4.1 Identifikasi Masalah ──
        warnings = _safe_warnings(quality_full)
        if warnings:
            story.append(Paragraph("4.1 Identifikasi Masalah Kualitas Data", S['h2']))
            warn_rows = [[Paragraph("•", S['warn']), Paragraph(w, S['warn'])] for w in warnings]
            wt = Table(warn_rows, colWidths=[15, 489])
            wt.setStyle(TableStyle([
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#fff3cd')),
                ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#ffeeba')),
                ('TOPPADDING',    (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(wt)
            story.append(Spacer(1, 8))

        # ── 4.2 Status Per Kolom ──
        columns_info = _safe_columns(quality_full)
        if columns_info:
            story.append(Paragraph("4.2 Status Kesehatan Per Kolom", S['h2']))
            col_rows = [[
                Paragraph("Kolom",       S['th']),
                Paragraph("Tipe Data",   S['th']),
                Paragraph("Missing (%)", S['th']),
                Paragraph("Unique",      S['th']),
                Paragraph("Outliers",    S['th']),
                Paragraph("Status",      S['th']),
            ]]
            for c in columns_info:
                if not isinstance(c, dict):
                    continue
                issues    = c.get('issues', 'OK')
                status_p  = (
                    Paragraph("<font color='#38a169'><b>OK</b></font>", S['td'])
                    if issues == 'OK' else
                    Paragraph(f"<font color='#e53e3e'><b>{issues}</b></font>", S['td'])
                )
                col_rows.append([
                    Paragraph(str(c.get('column', '')),                       S['td']),
                    Paragraph(str(c.get('dtype', '')),                        S['td']),
                    Paragraph(f"{c.get('missing', 0)} ({c.get('missing_pct', 0)}%)", S['td']),
                    Paragraph(str(c.get('unique', 0)),                        S['td']),
                    Paragraph(str(c.get('outliers', 0)),                      S['td']),
                    status_p,
                ])
            ct = Table(col_rows, colWidths=[110, 65, 85, 50, 55, 139])
            ct.setStyle(_header_table_style())
            story.append(ct)
            story.append(Spacer(1, 10))

        # ── 4.3 Alur Proses Data Cleaning ──
        story.append(Paragraph("4.3 Alur Proses Data Cleaning", S['h2']))
        if needs_cleaning:
            flow_desc = (
                "Berdasarkan hasil audit kualitas data, sistem mendeteksi bahwa dataset memerlukan "
                "tindakan pembersihan. Auto-EDA Dashboard menerapkan alur pemrosesan berikut:<br/><br/>"
                "<b>1. Audit Awal (Data Profiling):</b> Mendeteksi sel kosong (missing values), "
                "baris duplikat, inkonsistensi teks, serta pencilan numerik (outlier) menggunakan "
                "metode IQR (Interquartile Range).<br/><br/>"
                "<b>2. Standarisasi Teks:</b> Menghilangkan spasi berlebih, menyeragamkan format "
                "huruf (Title Case / Lower Case / Upper Case), dan mengoreksi ketidakseragaman "
                "kategori pada variabel kategorikal.<br/><br/>"
                "<b>3. Penanganan Data Hilang (Imputasi):</b> Mengisi nilai kosong dengan "
                "mean atau median untuk data numerik, dan modus untuk data kategorikal. Apabila "
                "tingkat kerusakan data melebihi ambang batas, baris yang bermasalah akan dihapus.<br/><br/>"
                "<b>4. Penanganan Outlier (IQR Capping):</b> Menetralkan nilai-nilai ekstrem "
                "dengan menggantinya menggunakan batas atas dan bawah IQR, sehingga distribusi "
                "data menjadi lebih representatif.<br/><br/>"
                "<b>5. Pemurnian Kolom:</b> Menghapus kolom dengan variansi nol atau rasio "
                "keunikan terlalu tinggi (misalnya kolom ID atau teks acak) yang tidak informatif "
                "bagi analisis.<br/><br/>"
                "Log tindakan cleaning secara detail dapat dilihat pada <b>Bab VIII</b> laporan ini."
            )
        else:
            flow_desc = (
                "Dataset telah melalui proses audit awal dan dinyatakan dalam kondisi bersih "
                "(clean). Seluruh kolom memenuhi standar kualitas data yang telah ditetapkan, "
                "sehingga tidak diperlukan tindakan pembersihan lebih lanjut. Data siap untuk "
                "memasuki tahap analisis statistik dan visualisasi. Informasi lebih lanjut "
                "mengenai status kebersihan data dapat dilihat pada <b>Bab VIII</b> laporan ini."
            )
        story.append(Paragraph(flow_desc, S['body']))

        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab IV tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB V · STATISTIK DESKRIPTIF NUMERIK
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB V: STATISTIK DESKRIPTIF — VARIABEL NUMERIK", S['h1']))
        story.append(Paragraph(
            "Bab ini menyajikan ringkasan statistik deskriptif untuk seluruh variabel numerik "
            "dalam dataset. Statistik yang disajikan meliputi ukuran pemusatan (mean, median), "
            "ukuran penyebaran (nilai minimum, maksimum, standar deviasi), serta karakteristik "
            "distribusi (skewness dan hasil uji normalitas). Informasi ini penting untuk memahami "
            "karakteristik dasar setiap variabel sebelum memasuki tahap analisis lebih lanjut.",
            S['body']))
        story.append(Spacer(1, 8))
        if num_stats:
            story.append(Paragraph("5.1 Tabel Statistik Deskriptif Numerik", S['h2']))
            nh = [Paragraph(h, S['th']) for h in
                  ["Kolom", "Mean", "Median", "Min", "Max", "Std Dev", "Skewness", "Normality"]]
            n_rows = [nh]
            for ns in num_stats:
                if not isinstance(ns, dict):
                    continue
                n_rows.append([
                    Paragraph(str(ns.get('Column', '')),    S['td']),
                    Paragraph(str(ns.get('Mean', 'N/A')),   S['td']),
                    Paragraph(str(ns.get('Median', 'N/A')), S['td']),
                    Paragraph(str(ns.get('Min', 'N/A')),    S['td']),
                    Paragraph(str(ns.get('Max', 'N/A')),    S['td']),
                    Paragraph(str(ns.get('Std Dev', 'N/A')),S['td']),
                    Paragraph(str(ns.get('Skewness', 'N/A')), S['td']),
                    Paragraph(str(ns.get('Normality', 'N/A')),S['td']),
                ])
            nt = Table(n_rows, colWidths=[90, 55, 55, 48, 48, 55, 55, 98])
            nt.setStyle(_header_table_style())
            story.append(nt)
        else:
            story.append(Paragraph("<i>Tidak terdapat kolom numerik dalam dataset.</i>", S['na']))
        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab V tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB VI · STATISTIK DESKRIPTIF KATEGORIKAL
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB VI: STATISTIK DESKRIPTIF — VARIABEL KATEGORIKAL", S['h1']))
        story.append(Paragraph(
            "Bab ini menyajikan ringkasan statistik deskriptif untuk seluruh variabel kategorikal "
            "dalam dataset. Statistik yang disajikan mencakup jumlah nilai unik (unique values), "
            "modus (nilai yang paling sering muncul), frekuensi dan persentase modus, serta "
            "jumlah dan persentase data hilang. Informasi ini berguna untuk memahami komposisi "
            "dan distribusi kategori dalam dataset.",
            S['body']))
        story.append(Spacer(1, 8))
        if cat_stats:
            story.append(Paragraph("6.1 Tabel Statistik Deskriptif Kategorikal", S['h2']))
            ch = [Paragraph(h, S['th']) for h in
                  ["Kolom", "Unique", "Mode", "Mode Freq", "Mode %", "Missing", "Missing %"]]
            c_rows = [ch]
            for cs in cat_stats:
                if not isinstance(cs, dict):
                    continue
                c_rows.append([
                    Paragraph(str(cs.get('Column', '')),        S['td']),
                    Paragraph(str(cs.get('Unique', 'N/A')),     S['td']),
                    Paragraph(str(cs.get('Mode', 'N/A')),       S['td']),
                    Paragraph(str(cs.get('Mode Freq', 'N/A')),  S['td']),
                    Paragraph(str(cs.get('Mode %', 'N/A')),     S['td']),
                    Paragraph(str(cs.get('Missing Count', 'N/A')), S['td']),
                    Paragraph(str(cs.get('Missing %', 'N/A')),  S['td']),
                ])
            ct2 = Table(c_rows, colWidths=[100, 50, 124, 60, 55, 55, 60])
            ct2.setStyle(_header_table_style())
            story.append(ct2)
        else:
            story.append(Paragraph("<i>Tidak terdapat kolom kategorikal dalam dataset.</i>", S['na']))
        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab VI tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB VII · VISUALISASI DATA & INTERPRETASI
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB VII: VISUALISASI DATA & INTERPRETASI", S['h1']))
        story.append(Paragraph(
            "Bab ini menyajikan visualisasi data yang meliputi distribusi variabel, boxplot, "
            "heatmap korelasi, serta hubungan antar variabel. Visualisasi ini bertujuan untuk "
            "memberikan pemahaman intuitif mengenai pola dan karakteristik dataset guna "
            "mendukung interpretasi dan pengambilan keputusan berbasis data.",
            S['body']))
        story.append(Spacer(1, 8))

        if viz_img_items:
            for idx, (path, label, _) in enumerate(viz_img_items):
                try:
                    img = _try_load_image(path) if path else None
                    if img is not None:
                        story.append(Paragraph(f"{chr(65+idx)}. {label}", S['h2']))
                        story.append(img)
                        story.append(Spacer(1, 8))
                except Exception:
                    continue
        else:
            # Fallback: old-style image_paths dict
            image_paths = image_paths or {}
            hist_path   = image_paths.get('histogram')
            heat_path   = image_paths.get('heatmap')
            num_cols_list = [
                c for c in df.select_dtypes(include='number').columns
                if c in df.columns
            ]
            story.append(Paragraph("A. Histogram (Distribusi Variabel Numerik)", S['h2']))
            hist_img = _try_load_image(hist_path) if hist_path else None
            if hist_img is None:
                hist_buf = _generate_histogram_image(df, num_cols_list)
                if hist_buf is not None:
                    hist_img = RLImage(hist_buf, width=450, height=262)
            if hist_img is not None:
                story.append(hist_img)
            else:
                story.append(Paragraph("<i>[Histogram tidak dapat dihasilkan]</i>", S['na']))
            story.append(Spacer(1, 10))
            story.append(Paragraph("B. Heatmap Korelasi", S['h2']))
            heat_img = _try_load_image(heat_path) if heat_path else None
            if heat_img is None:
                heat_buf = _generate_heatmap_image(df, num_cols_list)
                if heat_buf is not None:
                    heat_img = RLImage(heat_buf, width=450, height=337)
            if heat_img is not None:
                story.append(heat_img)
            else:
                story.append(Paragraph("<i>[Heatmap tidak dapat dihasilkan]</i>", S['na']))

        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab VII tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB VII-A · ANALISIS TIME SERIES (Jika tersedia)
    # ───────────────────────────────────────────────────────────────────────────
    try:
        if ts_img_items:
            story.append(Paragraph("BAB VII-A: ANALISIS TIME SERIES", S['h1']))
            story.append(Paragraph(
                "Dataset ini mengandung kolom bertipe datetime yang memungkinkan dilakukannya "
                "analisis deret waktu (time series). Analisis ini bertujuan untuk mengidentifikasi "
                "pola tren, efek musiman (seasonality), serta fluktuasi data secara periodik. "
                "Visualisasi berikut menampilkan pergerakan variabel numerik terhadap dimensi "
                "waktu yang tersedia dalam dataset.",
                S['body']))
            story.append(Spacer(1, 8))
            for idx, (path, label, _) in enumerate(ts_img_items):
                try:
                    img = _try_load_image(path) if path else None
                    if img is not None:
                        story.append(Paragraph(f"{chr(65+idx)}. {label}", S['h2']))
                        story.append(img)
                        story.append(Spacer(1, 8))
                except Exception:
                    continue
            story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab VII-A tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB VIII · PROSES DATA CLEANING
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB VIII: PROSES DATA CLEANING", S['h1']))
        if needs_cleaning:
            story.append(Paragraph(
                "Bab ini menyajikan secara rinci hasil pelaksanaan pembersihan data yang "
                "dilakukan oleh sistem terhadap dataset. Alur umum proses cleaning telah "
                "dijelaskan pada <b>Bab IV (Sub-bab 4.3)</b>. Bagian berikut menampilkan "
                "perbandingan kondisi data sebelum dan sesudah pembersihan, serta log "
                "tindakan yang telah dijalankan.",
                S['body']))
            story.append(Spacer(1, 8))

            story.append(Paragraph("8.1 Perbandingan Sebelum dan Sesudah Cleaning", S['h2']))
            if isinstance(cleaning_summary, dict):
                sb     = cleaning_summary
                rows_b = sb.get('rows_before',  len(df))
                rows_a = sb.get('rows_after',   len(df))
                cols_b = sb.get('cols_before',  len(df.columns))
                cols_a = sb.get('cols_after',   len(df.columns))
                miss_b = sb.get('missing_before', 0)
                miss_a = sb.get('missing_after',  0)
                mp_b   = sb.get('missing_pct_before', 0.0)
                mp_a   = sb.get('missing_pct_after',  0.0)

                diff_data = [
                    [Paragraph("<b>Metrik</b>",             S['th']),
                     Paragraph("<b>Sebelum (Raw)</b>",      S['th']),
                     Paragraph("<b>Sesudah (Cleaned)</b>",  S['th']),
                     Paragraph("<b>Perubahan</b>",          S['th'])],
                    [Paragraph("Baris Data",        S['td']),
                     Paragraph(str(rows_b),         S['td']),
                     Paragraph(str(rows_a),         S['td']),
                     Paragraph(f"Dihapus: {rows_b - rows_a} baris", S['td'])],
                    [Paragraph("Kolom Data",        S['td']),
                     Paragraph(str(cols_b),         S['td']),
                     Paragraph(str(cols_a),         S['td']),
                     Paragraph(f"Dihapus: {cols_b - cols_a} kolom", S['td'])],
                    [Paragraph("Sel Kosong",        S['td']),
                     Paragraph(f"{miss_b} ({mp_b}%)", S['td']),
                     Paragraph(f"{miss_a} ({mp_a}%)", S['td']),
                     Paragraph(f"Dibersihkan: {miss_b - miss_a} sel", S['td'])],
                ]
                dt = Table(diff_data, colWidths=[130, 120, 120, 134])
                dt.setStyle(_header_table_style())
                story.append(dt)
                story.append(Spacer(1, 10))

                cleaning_logs = sb.get('log', [])
                if cleaning_logs:
                    story.append(Paragraph("8.2 Log Tindakan Cleaning", S['h2']))
                    story.append(Paragraph(
                        "Berikut adalah daftar tindakan spesifik yang telah dijalankan oleh "
                        "sistem selama proses pembersihan data:", S['body']))
                    story.append(Spacer(1, 4))
                    log_rows = [[Paragraph(f"• {l}", S['td'])] for l in cleaning_logs]
                    lt = Table(log_rows, colWidths=[504])
                    lt.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
                        ('GRID',       (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
                    ]))
                    story.append(lt)
        else:
            story.append(Paragraph(
                f"Dataset ini telah melalui proses audit awal dan dinyatakan dalam kondisi "
                f"bersih (clean data). Seluruh kolom memenuhi standar kualitas data yang "
                f"ditetapkan — tidak ditemukan missing values, duplikasi baris, atau outlier "
                f"signifikan yang memerlukan tindakan korektif.<br/><br/>"
                f"Dengan demikian, dataset <b>{filename}</b> dinyatakan siap untuk memasuki "
                f"tahap analisis statistik deskriptif, visualisasi, dan perumusan insight "
                f"tanpa memerlukan pembersihan tambahan. Keputusan bisnis yang diambil "
                f"berdasarkan data ini dapat diandalkan karena bersumber dari dataset yang "
                f"valid dan terpercaya."
            ))
            story.append(Paragraph(
                "Pada visualisasi dan tabel di bab-bab sebelumnya, seluruh data yang "
                "ditampilkan merupakan data dalam kondisi original (tanpa modifikasi), "
                "sehingga representasi yang disajikan adalah gambaran autentik dari dataset "
                "yang diunggah.",
                S['body']))
        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab VIII tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB IX · TEMUAN KUNCI & INSIGHT OTOMATIS
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB IX: TEMUAN KUNCI & INSIGHT OTOMATIS", S['h1']))
        story.append(Paragraph(
            "Bab ini menyajikan temuan-temuan utama yang berhasil diidentifikasi oleh sistem "
            "berdasarkan hasil analisis statistik dan visualisasi dataset. Insight yang disajikan "
            "dirumuskan secara otomatis oleh mesin analisis dan dapat digunakan sebagai acuan "
            "dalam proses pengambilan keputusan strategis.",
            S['body']))
        story.append(Spacer(1, 8))

        if auto_insights:
            story.append(Paragraph("9.1 Insight Otomatis", S['h2']))
            for ins in auto_insights:
                if not isinstance(ins, dict):
                    continue
                ins_title = ins.get('title', 'Temuan Data')
                ins_desc  = ins.get('desc', '') or ins.get('description', '')
                ins_type  = ins.get('type', 'info')
                t_color = {
                    'success': '#2f855a', 'warning': '#c05621',
                    'danger':  '#c53030',
                }.get(ins_type, '#2b6cb0')
                story.append(Paragraph(
                    f"<b><font color='{t_color}'>{ins_title}</font></b>", S['h2']))
                story.append(Paragraph(ins_desc, S['body']))
                story.append(Spacer(1, 3))
        else:
            story.append(Paragraph(
                "<i>Belum terdapat insight otomatis yang dirumuskan untuk dataset ini.</i>", S['na']))

        # AI Interpretation (if available)
        if ai_interpretation:
            story.append(Spacer(1, 10))
            story.append(Paragraph("9.2 Interpretasi AI", S['h2']))
            ai_summary = ai_interpretation.get('summary', '')
            ai_action  = ai_interpretation.get('action_plan', '')
            if ai_summary:
                story.append(Paragraph(f"<b>Ringkasan:</b> {ai_summary}", S['body']))
            if ai_action:
                story.append(Paragraph(f"<b>Rencana Tindak Lanjut:</b> {ai_action}", S['body']))

        story.append(Spacer(1, 10))
        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab IX tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB X · REKOMENDASI STRATEGIS
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB X: REKOMENDASI STRATEGIS", S['h1']))
        story.append(Paragraph(
            "Berdasarkan hasil analisis statistik, visualisasi, dan temuan insight yang telah "
            "diuraikan pada bab-bab sebelumnya, berikut ini disajikan rekomendasi strategis "
            "yang dapat dipertimbangkan oleh para pemangku kepentingan dalam pengambilan "
            "keputusan berbasis data:",
            S['body']))
        story.append(Spacer(1, 8))

        recoms = []
        if missing_cells > 0:
            recoms.append(
                "<b>R1. Penguatan Validasi Input Data:</b> Mengingat ditemukannya sel kosong "
                "(missing values) pada dataset, manajemen disarankan untuk mengintegrasikan "
                "mekanisme validasi lapangan (field validation) pada sistem pengisian data. "
                "Langkah ini bertujuan memastikan tidak terdapat field kritis yang terlewat "
                "atau dikirim dalam kondisi kosong pada proses pengumpulan data selanjutnya."
            )
        if total_outliers > 0:
            recoms.append(
                "<b>R2. Investigasi Nilai Anomali (Outliers):</b> Teridentifikasi adanya "
                "nilai-nilai pencilan ekstrem dalam dataset. Disarankan agar tim operasional "
                "melakukan validasi silang untuk memastikan apakah nilai tersebut mencerminkan "
                "fluktuasi bisnis yang riil atau merupakan kesalahan pencatatan (human error). "
                "Apabila diperlukan, lakukan capping atau transformasi data sebelum memasuki "
                "tahap pemodelan prediktif guna menghindari bias yang tidak diinginkan."
            )
        if duplicate_rows > 0:
            recoms.append(
                "<b>R3. Pencegahan Duplikasi Data:</b> Ditemukan adanya baris data yang "
                "terduplikasi dalam dataset. Tim IT disarankan untuk meninjau kembali penerapan "
                "primary key atau unique constraint pada basis data transaksional guna "
                "mencegah terulangnya duplikasi di masa mendatang."
            )

        high_skew_cols = []
        for ns in (num_stats or []):
            if not isinstance(ns, dict):
                continue
            try:
                val = ns.get('Skewness', 'N/A')
                if val != 'N/A' and abs(float(val)) > 1.0:
                    high_skew_cols.append(ns.get('Column', ''))
            except Exception:
                continue
        if high_skew_cols:
            cols_str = ", ".join(filter(None, high_skew_cols))
            recoms.append(
                f"<b>R{len(recoms)+1}. Transformasi Skewness Data:</b> Kolom ({cols_str}) "
                "menunjukkan kemiringan distribusi yang tinggi (skewed). Sebelum menerapkan "
                "algoritma yang mengasumsikan distribusi normal, disarankan untuk melakukan "
                "transformasi logaritma atau Box-Cox guna menormalkan distribusi dan "
                "meminimalkan bias dalam pemodelan."
            )

        recoms.append(
            f"<b>R{len(recoms)+1}. Pembersihan Berkala (Data Governance):</b> Disarankan "
            "untuk menjadwalkan proses pembersihan data secara rutin menggunakan Auto-EDA "
            "Dashboard sebelum laporan akhir periode diekspor ke departemen eksekutif. "
            "Praktik tata kelola data (data governance) yang konsisten akan menjamin bahwa "
            "setiap keputusan strategis dibuat berdasarkan data yang bersih, valid, dan "
            "terpercaya."
        )

        recoms_html = "".join(f"{rec}<br/><br/>" for rec in recoms)
        story.append(Paragraph(recoms_html, S['body']))
        story.append(PageBreak())
    except Exception:
        story.append(Paragraph("<i>[Bab X tidak dapat dimuat — N/A]</i>", S['na']))
        story.append(PageBreak())

    # ───────────────────────────────────────────────────────────────────────────
    # BAB XI · PENUTUP
    # ───────────────────────────────────────────────────────────────────────────
    try:
        story.append(Paragraph("BAB XI: PENUTUP", S['h1']))
        penutup = (
            f"Laporan Analisis Data Deskriptif (Exploratory Data Analysis Report) ini telah "
            f"menyajikan gambaran komprehensif mengenai dataset <b>{filename}</b>. Secara "
            f"sistematis, laporan ini mencakup sebelas bab utama yang meliputi aspek kualitas "
            f"data, statistik deskriptif, visualisasi, analisis time series (jika tersedia), "
            f"proses data cleaning, temuan kunci dan insight otomatis, serta rekomendasi "
            f"strategis berbasis data.<br/><br/>"
            f"Dengan memanfaatkan <b>Auto-EDA Dashboard (DS Generator)</b> yang dikembangkan "
            f"oleh Kelompok 2 Data Science ITSB, proses analisis data yang biasanya memerlukan "
            f"waktu dan sumber daya yang besar dapat dilakukan secara otomatis, cepat, dan "
            f"akurat. Seluruh hasil yang disajikan dalam laporan ini bersifat data-driven dan "
            f"dapat dijadikan sebagai landasan pengambilan keputusan yang objektif, terukur, "
            f"serta dapat dipertanggungjawabkan.<br/><br/>"
            f"Demikian laporan ini disusun dan disajikan. Semoga laporan ini memberikan manfaat "
            f"serta wawasan yang berharga bagi seluruh pemangku kepentingan. Kritik dan saran "
            f"yang membangun sangat diharapkan untuk pengembangan sistem yang lebih baik di "
            f"masa mendatang."
        )
        story.append(Paragraph(penutup, S['body']))
        story.append(Spacer(1, 20))
        story.append(Paragraph(
            f"Hormat kami,<br/><br/>"
            f"<b>Kelompok 2 Data Science ITSB</b><br/>"
            f"{datetime.datetime.now().strftime('%d %B %Y')}",
            S['body']))
    except Exception:
        story.append(Paragraph("<i>[Bab XI tidak dapat dimuat]</i>", S['na']))

    # ── Build PDF ─────────────────────────────────────────────────────────────
    doc.build(
        story,
        canvasmaker=NumberedCanvas,
    )
    return True
