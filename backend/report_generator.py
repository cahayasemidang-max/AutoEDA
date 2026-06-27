import os
import datetime
import pandas as pd
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT


_PDF_LANG = 'id'

def _(*, id, en):
    return id if _PDF_LANG == 'id' else en

class NumberedCanvas(canvas.Canvas):
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
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#a3aed0"))
        if self._pageNumber > 1:
            self.drawString(54, 750, _(id="DS Generator — Laporan Analisis Data | Kelompok 2", en="DS Generator — Data Analysis Report | Group 2"))
            self.setStrokeColor(colors.HexColor("#e0e5f2"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)
        page_text = _(id=f"Halaman {self._pageNumber} dari {page_count}", en=f"Page {self._pageNumber} of {page_count}")
        self.drawRightString(558, 40, page_text)
        self.drawString(54, 40, _(id=f"Statistik Deskriptif & Laporan Kualitas Data | Dihasilkan: {datetime.datetime.now().strftime('%d %b %Y')}", en=f"Descriptive Statistics & Data Quality Report | Generated: {datetime.datetime.now().strftime('%d %b %Y')}"))
        self.setStrokeColor(colors.HexColor("#e0e5f2"))
        self.setLineWidth(0.5)
        self.line(54, 52, 558, 52)
        self.restoreState()


def draw_watermark(canvas_obj, doc):
    canvas_obj.saveState()
    canvas_obj.setFont('Helvetica-Bold', 55)
    canvas_obj.setFillColor(colors.HexColor('#e0e5f2'), alpha=0.12)
    canvas_obj.translate(300, 400)
    canvas_obj.rotate(42)
    canvas_obj.drawCentredString(0, 0, _(id="CONFIDENTIAL", en="CONFIDENTIAL"))
    canvas_obj.setFont('Helvetica', 16)
    canvas_obj.drawCentredString(0, -45, _(id="DS GENERATOR - ITSB KELOMPOK 2", en="DS GENERATOR - ITSB GROUP 2"))
    canvas_obj.restoreState()


def _try_img(path, max_width=440, max_height=300):
    if not path or not os.path.isfile(path):
        return None
    try:
        img = Image(path)
        aspect = img.drawWidth / max(img.drawHeight, 1)
        w = min(max_width, img.drawWidth)
        h = w / aspect
        if h > max_height:
            h = max_height
            w = h * aspect
        img.drawWidth = w
        img.drawHeight = h
        return img
    except Exception:
        return None





def _num(n, dec=2):
    if n is None or n == 'N/A':
        return 'N/A'
    try:
        return f"{float(n):,.{dec}f}"
    except (ValueError, TypeError):
        return str(n)


def generate_pdf_report(dest_path, filename, df, quality_report, metrics, num_stats, cat_stats, auto_insights, cleaning_history, cleaning_summary,
                        img_paths=None, img_items=None, report_types=None, lang='id',
                        ai_interpretation=None):
    """
    Generates a comprehensive 11-chapter academic PDF report in Indonesian or English.
    """
    global _PDF_LANG
    _PDF_LANG = lang if lang in ('id', 'en') else 'id'

    _cat_label_map = {
        'Distribusi Data': _(id='Distribusi Data', en='Data Distribution'),
        'Analisis Boxplot': _(id='Analisis Boxplot', en='Boxplot Analysis'),
        'Analisis Korelasi': _(id='Analisis Korelasi', en='Correlation Analysis'),
        'Distribusi Kategorikal': _(id='Distribusi Kategorikal', en='Categorical Distribution'),
        'Proporsi Kategorikal': _(id='Proporsi Kategorikal', en='Categorical Proportion'),
        'Analisis Time Series': _(id='Analisis Time Series', en='Time Series Analysis'),
        'Visualisasi Lainnya': _(id='Visualisasi Lainnya', en='Other Visualizations'),
    }

    # ── Styles ──────────────────────────────────────────────────────────────
    _styles = getSampleStyleSheet()

    s = {}

    s['cover_title'] = ParagraphStyle('CoverTitle', fontName='Helvetica-Bold', fontSize=20, leading=24,
                                      textColor=colors.HexColor('#1b254b'), spaceAfter=6)

    s['cover_sub'] = ParagraphStyle('CoverSubtitle', fontName='Helvetica', fontSize=11, leading=15,
                                    textColor=colors.HexColor('#4318ff'), spaceAfter=15)

    s['bab'] = ParagraphStyle('Bab', fontName='Helvetica-Bold', fontSize=14, leading=18,
                              textColor=colors.HexColor('#1b254b'), spaceBefore=20, spaceAfter=12, alignment=TA_CENTER)

    s['sub_bab'] = ParagraphStyle('SubBab', fontName='Helvetica-Bold', fontSize=11, leading=14,
                                  textColor=colors.HexColor('#1b254b'), spaceBefore=14, spaceAfter=8, keepWithNext=True)

    s['h2'] = ParagraphStyle('H2', fontName='Helvetica-Bold', fontSize=10, leading=13,
                             textColor=colors.HexColor('#4318ff'), spaceBefore=10, spaceAfter=5, keepWithNext=True)

    s['body'] = ParagraphStyle('Body', fontName='Helvetica', fontSize=8.5, leading=12,
                               textColor=colors.HexColor('#4a5568'), spaceAfter=6, alignment=TA_JUSTIFY)

    s['body_sm'] = ParagraphStyle('BodySmall', fontName='Helvetica', fontSize=7, leading=10, spaceAfter=4)

    s['th'] = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white)

    s['td'] = ParagraphStyle('TD', fontName='Helvetica', fontSize=7.5, leading=9, textColor=colors.HexColor('#1b254b'))

    s['cap'] = ParagraphStyle('Caption', fontName='Helvetica', fontSize=7, leading=10,
                              textColor=colors.HexColor('#94A3B8'), spaceBefore=4, spaceAfter=10, alignment=TA_CENTER)

    s['warn'] = ParagraphStyle('Warn', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#856404'))

    def P(text, style='body'):
        return Paragraph(text, s[style])

    def TH(text):
        return Paragraph(text, s['th'])

    def TD(text):
        return Paragraph(text, s['td'])

    def CAP(text):
        return Paragraph(text, s['cap'])

    def TB(rows, col_widths, extra_styles=None):
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        base = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111c44')),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 0), (-1, 0), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
            ('TOPPADDING', (0, 1), (-1, -1), 3),
        ]
        if extra_styles:
            base.extend(extra_styles)
        t.setStyle(TableStyle(base))
        return t

    now_str = datetime.datetime.now().strftime('%d %B %Y, %H:%M:%S')
    rows_total = len(df) if df is not None else 0
    cols_total = len(df.columns) if df is not None else 0
    qs = quality_report.get('summary', {}) if isinstance(quality_report, dict) else {}
    cols_q = quality_report.get('columns', []) if isinstance(quality_report, dict) else []
    sb = cleaning_summary or {}

    needs_clean = qs.get('needs_cleaning', True)
    status_label = _(id="RAW DATA (Perlu Pembersihan)", en="RAW DATA (Needs Cleaning)") if needs_clean else _(id="CLEAN DATA (Bersih)", en="CLEAN DATA (Clean)")
    status_color = "#e53e3e" if needs_clean else "#38a169"

    # ── Cross-chapter computed variables ──────────────────────────────────
    total_missing = qs.get('missing_cells', 0)
    total_outliers = qs.get('total_outliers', 0)
    total_dups = qs.get('duplicate_rows', 0)
    is_cleaned = sb.get('is_cleaned', False)
    steps_taken = sb.get('steps_taken', 0)

    high_skew = []
    if num_stats:
        for ns in num_stats:
            try:
                if abs(float(ns.get('Skewness', 0))) > 1.0:
                    high_skew.append(ns.get('Column', ''))
            except Exception:
                continue

    # ── Report type selection ──────────────────────────────────────────────
    _rt_set = set(report_types or [])
    _empty_rt = not _rt_set
    _inc_summary     = _empty_rt or 'summary' in _rt_set
    _inc_detailed    = _empty_rt or 'detailed' in _rt_set
    _inc_correlation = _empty_rt or 'correlation' in _rt_set
    _inc_action      = _empty_rt or 'action' in _rt_set

    story = []
    _sink = story

    # ========================================================================
    # COVER PAGE
    # ========================================================================
    banner_data = [
        [P(_(id="DATA SCIENCE GENERATOR SYSTEM", en="DATA SCIENCE GENERATOR SYSTEM"), 'cover_sub')]
    ]
    banner_table = Table(banner_data, colWidths=[504])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#4318ff')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    _sink.append(banner_table)
    _sink.append(Spacer(1, 30))
    _sink.append(Paragraph(_(id="LAPORAN ANALISIS DATA", en="DATA ANALYSIS REPORT"), s['cover_title']))
    _sink.append(Paragraph(_(id="Dataset Quality, Descriptive Statistics & Strategic Recommendations", en="Dataset Quality, Descriptive Statistics & Strategic Recommendations"), s['cover_sub']))
    _sink.append(Spacer(1, 6))
    _sink.append(P(_(id=f"<b>File Dataset:</b> {filename}", en=f"<b>Dataset File:</b> {filename}")))
    _sink.append(P(_(id=f"<b>Tanggal Analisis:</b> {now_str}", en=f"<b>Analysis Date:</b> {now_str}")))
    _sink.append(P(_(id=f"<b>Disusun Oleh:</b> Kelompok 2 — Data Science, Institut Teknologi dan Sains Bandung", en=f"<b>Prepared By:</b> Group 2 — Data Science, Institut Teknologi dan Sains Bandung")))
    _sink.append(Spacer(1, 10))
    _sink.append(P(_(id="Dokumen ini bersifat rahasia dan ditujukan untuk kepentingan analisis internal.", en="This document is confidential and intended for internal analysis purposes.")))
    _sink.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # BAB I — PENDAHULUAN (_inc_summary)
    _sink = story if _inc_summary else []
    # ════════════════════════════════════════════════════════════════════════
    # ========================================================================
    _sink.append(Paragraph(_(id="BAB I<br/>PENDAHULUAN", en="CHAPTER I<br/>INTRODUCTION"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="1.1. Tentang DS Generator", en="1.1. About DS Generator"), 'sub_bab'))
    _sink.append(P(_(id=
        "<b>DS Generator (Descriptive Statistics Generator)</b> merupakan sebuah platform analisis data "
        "berbasis web yang dikembangkan oleh <b>Kelompok 2 Program Studi Data Science</b>, "
        "Institut Teknologi dan Sains Bandung (ITSB). Sistem ini dirancang untuk memfasilitasi para analis data, "
        "manajer, dan pengambil keputusan dalam melakukan serangkaian tugas analitis secara otomatis dan terintegrasi, "
        "meliputi: (a) unggah dataset dalam berbagai format tabular; (b) audit kualitas data secara komprehensif; "
        "(c) pembersihan data melalui pipeline terstruktur; (d) komputasi statistik deskriptif tingkat lanjut; "
        "(e) visualisasi data interaktif berbasis Plotly; (f) analisis time series; serta (g) perumusan insight "
        "dan rekomendasi strategis berbasis bukti numerik. Seluruh fitur tersebut tersaji dalam tatap muka "
        "dashboard yang responsif dan mendukung ekspor laporan dalam format PDF.",
        en=
        "<b>DS Generator (Descriptive Statistics Generator)</b> is a web-based data analysis platform "
        "developed by <b>Group 2 of the Data Science Study Program</b>, "
        "Institut Teknologi dan Sains Bandung (ITSB). This system is designed to facilitate data analysts, "
        "managers, and decision-makers in performing a series of analytical tasks automatically and in an integrated manner, "
        "covering: (a) uploading datasets in various tabular formats; (b) comprehensive data quality audits; "
        "(c) data cleaning through structured pipelines; (d) advanced descriptive statistical computations; "
        "(e) interactive Plotly-based data visualizations; (f) time series analysis; and (g) formulation of insights "
        "and strategic recommendations based on numerical evidence. All these features are presented in a responsive "
        "dashboard interface that supports report export in PDF format.")))

    _sink.append(P(_(id="1.2. Deskripsi Dataset", en="1.2. Dataset Description"), 'sub_bab'))
    num_cols = metrics.get('num_count', 0)
    cat_cols = metrics.get('cat_count', 0)
    _sink.append(P(_(id=
        f"Dataset yang dianalisis dalam laporan ini adalah <b>{filename}</b>, yang terdiri dari "
        f"<b>{rows_total}</b> baris observasi dan <b>{cols_total}</b> kolom variabel. "
        f"Berdasarkan klasifikasi tipe data, dataset mengandung <b>{num_cols}</b> variabel numerik dan "
        f"<b>{cat_cols}</b> variabel kategorikal. Seluruh analisis dalam laporan ini dilakukan terhadap "
        f"data dalam kondisi terkini sesuai dengan sesi analisis yang berjalan.",
        en=
        f"The dataset analyzed in this report is <b>{filename}</b>, consisting of "
        f"<b>{rows_total}</b> observation rows and <b>{cols_total}</b> variable columns. "
        f"Based on data type classification, the dataset contains <b>{num_cols}</b> numeric variables and "
        f"<b>{cat_cols}</b> categorical variables. All analyses in this report were conducted on "
        f"the current data state according to the active analysis session.")))

    _sink.append(P(_(id="1.3. Status Kebersihan Data", en="1.3. Data Cleanliness Status"), 'sub_bab'))
    _sink.append(P(_(id=
        f"Berdasarkan hasil audit kualitas data yang dilakukan oleh sistem, status kebersihan dataset saat ini "
        f"dinyatakan sebagai <font color='{status_color}'><b>{status_label}</b></font>. "
        f"Indikator utama yang digunakan dalam penentuan status ini meliputi jumlah sel kosong, "
        f"baris duplikat, nilai outlier, serta konsistensi tipe data antar kolom.",
        en=
        f"Based on the data quality audit conducted by the system, the current dataset cleanliness status "
        f"is declared as <font color='{status_color}'><b>{status_label}</b></font>. "
        f"The main indicators used in determining this status include the number of empty cells, "
        f"duplicate rows, outlier values, and data type consistency across columns.")))

    # Quality KPIs
    kpi_rows = [[
        P(_(id="<b>Sel Kosong (Missing)</b>", en="<b>Empty Cells (Missing)</b>"), 'h2'),
        P(_(id="<b>Baris Duplikat</b>", en="<b>Duplicate Rows</b>"), 'h2'),
        P(_(id="<b>Nilai Outlier (IQR)</b>", en="<b>Outlier Values (IQR)</b>"), 'h2'),
    ], [
        P(f"<font size=11 color='#2d3748'><b>{qs.get('missing_cells', 0)}</b></font><br/><font size=7 color='#718096'>({qs.get('missing_pct', '0%')})</font>", 'body'),
        P(f"<font size=11 color='#2d3748'><b>{qs.get('duplicate_rows', 0)}</b></font><br/><font size=7 color='#718096'>" + _(id="baris", en="rows") + "</font>", 'body'),
        P(f"<font size=11 color='#2d3748'><b>{qs.get('total_outliers', 0)}</b></font><br/><font size=7 color='#718096'>" + _(id="nilai ekstrem", en="extreme values") + "</font>", 'body'),
    ]]
    kpi_t = Table(kpi_rows, colWidths=[168, 168, 168])
    kpi_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    _sink.append(kpi_t)
    _sink.append(Spacer(1, 8))

    # Warnings
    if quality_report and quality_report.get('warnings'):
        _sink.append(P(_(id="<b>Peringatan Kualitas Data:</b>", en="<b>Data Quality Warnings:</b>")))
        for w in quality_report['warnings']:
            _sink.append(P(f"• {w}", 'warn'))
    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB II — PENDAHULUAN & LATAR BELAKANG
    # ========================================================================
    _sink = story if _inc_summary else []
    _sink.append(Paragraph(_(id="BAB II<br/>PENDAHULUAN &amp; LATAR BELAKANG", en="CHAPTER II<br/>INTRODUCTION &amp; BACKGROUND"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="2.1. Latar Belakang", en="2.1. Background"), 'sub_bab'))
    _sink.append(P(_(id=
        "Dalam era transformasi digital, data merupakan aset strategis yang mendasari setiap keputusan bisnis "
        "dan organisasi. Kualitas keputusan yang dihasilkan sangat bergantung pada kualitas data yang dianalisis. "
        "Sayangnya, data mentah yang dikumpulkan dari berbagai sumber seringkali mengandung ketidaksempurnaan, "
        "seperti nilai yang hilang (missing values), inkonsistensi format, duplikasi entri, serta pencilan "
        "numerik (outliers) yang dapat mengganggu validitas hasil analisis statistik.",
        en=
        "In the era of digital transformation, data is a strategic asset underlying every business "
        "and organizational decision. The quality of resulting decisions greatly depends on the quality of the data analyzed. "
        "Unfortunately, raw data collected from various sources often contains imperfections, "
        "such as missing values, format inconsistencies, duplicate entries, and numerical "
        "outliers that can compromise the validity of statistical analysis results.")))

    _sink.append(P(_(id=
        "<b>DS Generator</b> hadir sebagai solusi terintegrasi yang menjembatani kesenjangan antara data mentah "
        "dan informasi yang siap pakai. Sistem ini mengotomatiskan seluruh tahapan analisis data — mulai dari "
        "profil kualitas, pembersihan, komputasi statistik, visualisasi, hingga perumusan rekomendasi. "
        "Dengan pendekatan berbasis pipeline terstruktur, DS Generator memastikan bahwa setiap analisis "
        "dilakukan secara reprodusibel dan transparan.",
        en=
        "<b>DS Generator</b> serves as an integrated solution that bridges the gap between raw data "
        "and actionable information. This system automates the entire data analysis pipeline — from "
        "quality profiling, cleaning, statistical computation, visualization, to recommendation formulation. "
        "With a structured pipeline-based approach, DS Generator ensures that every analysis "
        "is conducted reproducibly and transparently.")))

    _sink.append(P(_(id="2.2. Tujuan Laporan", en="2.2. Report Objectives"), 'sub_bab'))
    _sink.append(P(_(id=
        "Laporan ini disusun dengan tujuan sebagai berikut: "
        "(1) menyajikan gambaran umum dataset yang dianalisis; "
        "(2) mengevaluasi tingkat kesehatan data melalui metrik kualitas yang terstandarisasi; "
        "(3) menyajikan statistik deskriptif untuk seluruh variabel numerik dan kategorikal; "
        "(4) menampilkan visualisasi data beserta interpretasi analitisnya; "
        "(5) mendokumentasikan proses pembersihan data yang telah dilakukan; "
        "(6) merumuskan insight otomatis berdasarkan pola yang terdeteksi dalam data; serta "
        "(7) memberikan rekomendasi strategis bagi pengambil keputusan berbasis bukti.",
        en=
        "This report is prepared with the following objectives: "
        "(1) presenting an overview of the analyzed dataset; "
        "(2) evaluating data health levels through standardized quality metrics; "
        "(3) presenting descriptive statistics for all numeric and categorical variables; "
        "(4) displaying data visualizations along with their analytical interpretation; "
        "(5) documenting the data cleaning process that has been performed; "
        "(6) formulating automatic insights based on patterns detected in the data; and "
        "(7) providing strategic recommendations for evidence-based decision makers.")))

    _sink.append(P(_(id="2.3. Ruang Lingkup", en="2.3. Scope"), 'sub_bab'))
    _sink.append(P(_(id=
        "Ruang lingkup laporan ini mencakup seluruh variabel yang terdapat dalam dataset "
        "tanpa dilakukan penyamplingan. Analisis mencakup seluruh observasi dan seluruh kolom "
        "yang tersedia. Metode statistik yang digunakan meliputi statistika deskriptif (ukuran "
        "tendensi sentral, dispersi, dan distribusi), analisis korelasi Pearson, serta deteksi "
        "outlier menggunakan metode Interquartile Range (IQR). Visualisasi data disajikan dalam "
        "bentuk diagram distribusi, boxplot, heatmap korelasi, serta diagram interaktif lainnya.",
        en=
        "The scope of this report covers all variables contained in the dataset "
        "without sampling. The analysis includes all observations and all available "
        "columns. The statistical methods used include descriptive statistics (measures of "
        "central tendency, dispersion, and distribution), Pearson correlation analysis, and "
        "outlier detection using the Interquartile Range (IQR) method. Data visualizations are presented in "
        "the form of distribution diagrams, boxplots, correlation heatmaps, and other interactive charts.")))
    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB III — DESKRIPSI & RINGKASAN DATASET
    # ========================================================================
    _sink = story if _inc_summary else []
    _sink.append(Paragraph(_(id="BAB III<br/>DESKRIPSI &amp; RINGKASAN DATASET", en="CHAPTER III<br/>DATASET DESCRIPTION &amp; SUMMARY"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="3.1. Metadata Dataset", en="3.1. Dataset Metadata"), 'sub_bab'))
    meta_rows = [
        [P(_(id="<b>Atribut Metadata</b>", en="<b>Metadata Attribute</b>"), 'h2'), P(_(id="<b>Nilai</b>", en="<b>Value</b>"), 'h2')],
        [TD(_(id="Nama File", en="File Name")), TD(filename)],
        [TD(_(id="Waktu Analisis", en="Analysis Time")), TD(now_str)],
        [TD(_(id="Status Kebersihan", en="Cleanliness Status")), TD(f"<font color='{status_color}'><b>{status_label}</b></font>")],
        [TD(_(id="Jumlah Baris (Observasi)", en="Row Count (Observations)")), TD(str(metrics.get('total_rows', rows_total)))],
        [TD(_(id="Jumlah Kolom (Variabel)", en="Column Count (Variables)")), TD(str(metrics.get('total_columns', cols_total)))],
        [TD(_(id="Variabel Numerik", en="Numeric Variables")), TD(str(num_cols))],
        [TD(_(id="Variabel Kategorikal", en="Categorical Variables")), TD(str(cat_cols))],
        [TD(_(id="Jumlah Sel Kosong", en="Empty Cell Count")), TD(f"{qs.get('missing_cells', 0)} ({qs.get('missing_pct', '0%')})")],
        [TD(_(id="Baris Duplikat", en="Duplicate Rows")), TD(str(qs.get('duplicate_rows', 0)))],
        [TD(_(id="Nilai Outlier Terdeteksi", en="Detected Outliers")), TD(str(qs.get('total_outliers', 0)))],
    ]
    _sink.append(TB(meta_rows, [160, 344]))
    _sink.append(Spacer(1, 10))

    _sink.append(P(_(id="3.2. Komposisi Tipe Data", en="3.2. Data Type Composition"), 'sub_bab'))
    if df is not None:
        type_counts = df.dtypes.value_counts().to_dict()
        type_rows = [[TH(_(id="Tipe Data", en="Data Type")), TH(_(id="Jumlah Kolom", en="Number of Columns"))]]
        for dt, cnt in sorted(type_counts.items(), key=lambda x: str(x[0])):
            type_rows.append([TD(str(dt)), TD(str(cnt))])
        _sink.append(TB(type_rows, [200, 200]))
        _sink.append(Spacer(1, 6))

    _sink.append(P(_(id="3.3. Cuplikan Data (Sampel Awal)", en="3.3. Data Sample (Preview)"), 'sub_bab'))
    if df is not None:
        sample = df.head(5)
        sample_cols = list(sample.columns)
        total_cols = len(sample_cols)
        max_display_cols = 8
        cw = min(460 // min(total_cols, max_display_cols), 80)
        cw = max(cw, 55)

        display_cols = sample_cols[:max_display_cols]
        hidden = total_cols - max_display_cols
        col_trunc = max(int(cw / 4.5) - 2, 6)

        sample_headers = [TH(c[:col_trunc] + ('...' if len(c) > col_trunc else '')) for c in display_cols]
        if hidden > 0:
            sample_headers.append(TH(_(id=f"+{hidden} kolom", en=f"+{hidden} columns")))
            widths = [cw] * len(display_cols) + [45]
        else:
            widths = [cw] * len(display_cols)

        sample_rows = [sample_headers]
        for __, row in sample.iterrows():
            vals = [TD(str(v)[:col_trunc] if v is not None else 'NaN') for v in row[:max_display_cols]]
            if hidden > 0:
                vals.append(TD("..."))
            sample_rows.append(vals)
        _sink.append(TB(sample_rows, widths))
        _sink.append(P(_(id=f"<i>Menampilkan {min(total_cols, max_display_cols)} dari {total_cols} kolom. "
                       f"Dataset memiliki total {rows_total} baris.</i>",
                       en=f"<i>Showing {min(total_cols, max_display_cols)} of {total_cols} columns. "
                       f"Dataset has a total of {rows_total} rows.</i>"), 'body_sm'))
    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB IV — KUALITAS DATA & DATA HEALTH
    # ========================================================================
    _sink = story if _inc_detailed else []
    _sink.append(Paragraph(_(id="BAB IV<br/>KUALITAS DATA &amp; DATA HEALTH", en="CHAPTER IV<br/>DATA QUALITY &amp; HEALTH"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="4.1. Ringkasan Kualitas Data", en="4.1. Data Quality Summary"), 'sub_bab'))
    _sink.append(P(_(id=
        "Penilaian kualitas data dilakukan dengan memindai setiap kolom dataset untuk mendeteksi "
        "berbagai anomali, meliputi: nilai hilang (missing values), tingkat keunikan data, keberadaan "
        "nilai pencilan (outliers) berdasarkan metode IQR, serta inkonsistensi tipe data. "
        "Setiap kolom kemudian diklasifikasikan ke dalam status 'OK' (tidak bermasalah) atau "
        "'Perlu Perhatian' berdasarkan ambang batas yang telah ditentukan oleh sistem.",
        en=
        "Data quality assessment is performed by scanning each column of the dataset to detect "
        "various anomalies, including: missing values, data uniqueness levels, the presence of "
        "outliers based on the IQR method, and data type inconsistencies. "
        "Each column is then classified into an 'OK' (no issues) or "
        "'Needs Attention' status based on thresholds determined by the system.")))

    if quality_report and quality_report.get('warnings'):
        _sink.append(P(_(id="<b>Temuan Umum dari Proses Audit:</b>", en="<b>General Findings from the Audit Process:</b>")))
        for w in quality_report['warnings']:
            _sink.append(P(f"• {w}", 'warn'))
        _sink.append(Spacer(1, 6))

    _sink.append(P(_(id="4.2. Tabel Status Kesehatan per Kolom", en="4.2. Column Health Status Table"), 'sub_bab'))
    col_headers = [
        TH(_(id="Nama Kolom", en="Column Name")), TH(_(id="Tipe", en="Type")), TH(_(id="Missing (%)", en="Missing (%)")), TH(_(id="Unique", en="Unique")),
        TH(_(id="Outlier", en="Outlier")), TH(_(id="Status / Isu", en="Status / Issues")),
    ]
    col_rows = [col_headers]
    if cols_q:
        for c in cols_q:
            issues = c.get('issues', 'OK')
            if issues == 'OK':
                sp = TD("<font color='#38a169'><b>OK</b></font>")
            else:
                sp = TD(f"<font color='#e53e3e'><b>{issues}</b></font>")
            col_rows.append([
                TD(c.get('column', '—')),
                TD(c.get('dtype', '—')),
                TD(f"{c.get('missing', 0)} ({c.get('missing_pct', '0%')}%)"),
                TD(str(c.get('unique', 0))),
                TD(str(c.get('outliers', 0))),
                sp,
            ])
    _sink.append(TB(col_rows, [100, 55, 80, 50, 50, 169]))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="4.3. Interpretasi Kualitas Data", en="4.3. Data Quality Interpretation"), 'sub_bab'))
    ok_cols = sum(1 for c in cols_q if c.get('issues', '') == 'OK')
    problematic_cols = sum(1 for c in cols_q if c.get('issues', '') != 'OK')
    _sink.append(P(_(id=
        f"Dari total <b>{len(cols_q)}</b> kolom yang diperiksa, sebanyak <b>{ok_cols}</b> kolom "
        f"dinyatakan dalam kondisi baik (OK), sementara <b>{problematic_cols}</b> kolom lainnya "
        f"memerlukan perhatian lebih lanjut. Secara global, ditemukan <b>{total_missing}</b> sel kosong, "
        f"<b>{total_dups}</b> baris duplikat, dan <b>{total_outliers}</b> nilai outlier yang terdeteksi. "
        f"Temuan ini mengindikasikan bahwa dataset memerlukan proses pembersihan sebelum "
        f"digunakan untuk analisis lanjutan atau pemodelan prediktif.",
        en=
        f"Of the total <b>{len(cols_q)}</b> columns examined, <b>{ok_cols}</b> columns "
        f"are declared in good condition (OK), while <b>{problematic_cols}</b> other columns "
        f"require further attention. Globally, <b>{total_missing}</b> empty cells, "
        f"<b>{total_dups}</b> duplicate rows, and <b>{total_outliers}</b> outlier values were detected. "
        f"These findings indicate that the dataset requires a cleaning process before "
        f"being used for further analysis or predictive modeling.")))
    _sink.append(PageBreak())

    # ========================================================================
    # BAB V — STATISTIK DESKRIPTIF NUMERIK
    # ========================================================================
    _sink.append(Paragraph(_(id="BAB V<br/>STATISTIK DESKRIPTIF NUMERIK", en="CHAPTER V<br/>NUMERICAL DESCRIPTIVE STATISTICS"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="5.1. Tabel Statistik Deskriptif Variabel Numerik", en="5.1. Numerical Variable Descriptive Statistics Table"), 'sub_bab'))
    if num_stats:
        num_headers = [
            TH(_(id="Variabel", en="Variable")), TH(_(id="Mean", en="Mean")), TH(_(id="Median", en="Median")), TH(_(id="Min", en="Min")), TH(_(id="Max", en="Max")),
            TH(_(id="Std Dev", en="Std Dev")), TH(_(id="Skewness", en="Skewness")), TH(_(id="Kurtosis", en="Kurtosis")), TH(_(id="Distribusi", en="Distribution")),
        ]
        num_rows = [num_headers]
        for ns in num_stats:
            skew_val = ns.get('Skewness', 'N/A')
            try:
                sv = float(skew_val) if skew_val != 'N/A' else 0
                if abs(sv) < 0.5:
                    dist_label = _(id="Simetris", en="Symmetric")
                elif sv > 0.5:
                    dist_label = _(id="Miring Kanan", en="Right Skewed")
                elif sv < -0.5:
                    dist_label = _(id="Miring Kiri", en="Left Skewed")
                else:
                    dist_label = _(id="Simetris", en="Symmetric")
            except:
                dist_label = "N/A"
            num_rows.append([
                TD(ns.get('Column', '—')),
                TD(_num(ns.get('Mean'))),
                TD(_num(ns.get('Median'))),
                TD(_num(ns.get('Min'))),
                TD(_num(ns.get('Max'))),
                TD(_num(ns.get('Std Dev'))),
                TD(str(skew_val)),
                TD(_num(ns.get('Kurtosis', 'N/A'))),
                TD(dist_label),
            ])
        _sink.append(TB(num_rows, [80, 52, 52, 42, 42, 52, 52, 52, 62]))
        _sink.append(Spacer(1, 8))
    else:
        _sink.append(P(_(id="Tidak terdapat variabel numerik dalam dataset yang dianalisis.", en="No numeric variables found in the analyzed dataset.")))
        _sink.append(PageBreak())


    if num_stats:
        _sink.append(P(_(id="5.2. Analisis dan Interpretasi", en="5.2. Analysis and Interpretation"), 'sub_bab'))
    # Generate interpretive narrative per numeric column
    for ns in num_stats:
        col = ns.get('Column', '—')
        mean = ns.get('Mean', 'N/A')
        median = ns.get('Median', 'N/A')
        std = ns.get('Std Dev', 'N/A')
        minv = ns.get('Min', 'N/A')
        maxv = ns.get('Max', 'N/A')
        skew = ns.get('Skewness', 'N/A')
        try:
            sk_f = float(skew) if skew != 'N/A' else 0
        except:
            sk_f = 0

        # Interpretasi skewness
        if abs(sk_f) < 0.5:
            skew_int = _(id="distribusi data cenderung simetris, di mana nilai mean dan median relatif berdekatan", en="the data distribution tends to be symmetric, where the mean and median values are relatively close")
            skew_rec = _(id="data telah memenuhi asumsi distribusi normal yang diperlukan oleh berbagai algoritma parametrik", en="the data meets the normality assumption required by various parametric algorithms")
        elif sk_f > 0.5:
            skew_int = _(id="distribusi data miring ke kanan (positif skewness), mengindikasikan adanya sejumlah observasi dengan nilai yang jauh lebih besar dari mayoritas data", en="the data distribution is right-skewed (positive skewness), indicating a number of observations with values much larger than the majority of the data")
            skew_rec = _(id="transformasi logaritma atau Box-Cox disarankan sebelum menerapkan model yang mengasumsikan normalitas", en="logarithmic or Box-Cox transformation is recommended before applying models that assume normality")
        else:
            skew_int = _(id="distribusi data miring ke kiri (negatif skewness), yang berarti sebagian besar nilai terkonsentrasi pada kisaran tinggi dengan ekor panjang di sisi kiri", en="the data distribution is left-skewed (negative skewness), meaning most values are concentrated in the high range with a long tail on the left side")
            skew_rec = _(id="transformasi refleksi atau pangkat (power transform) dapat dipertimbangkan untuk menormalkan distribusi", en="reflection or power transform can be considered to normalize the distribution")

        _sink.append(P(_(id=
            f"<b>{col}:</b> Variabel ini memiliki rata-rata (mean) sebesar <b>{mean}</b> dengan simpangan baku "
            f"(std. deviasi) <b>{std}</b>. Rentang nilai berkisar dari <b>{minv}</b> hingga <b>{maxv}</b>, "
            f"memberikan gambaran tentang sebaran data secara keseluruhan. Nilai tengah (median) tercatat "
            f"sebesar <b>{median}</b>. Ditinjau dari kemiringan distribusi (skewness = {sk_f}), "
            f"{skew_int}. Dari sisi pemodelan, {skew_rec}. "
            f"Simpangan baku yang relatif besar terhadap mean mengindikasikan variabilitas yang tinggi dalam data, "
            f"sehingga perlu diperhatikan dalam proses analisis lebih lanjut.",
            en=
            f"<b>{col}:</b> This variable has a mean of <b>{mean}</b> with a standard "
            f"deviation of <b>{std}</b>. The value range spans from <b>{minv}</b> to <b>{maxv}</b>, "
            f"providing an overview of the overall data spread. The median value is recorded "
            f"at <b>{median}</b>. In terms of distribution skewness (skewness = {sk_f}), "
            f"{skew_int}. From a modeling perspective, {skew_rec}. "
            f"A relatively large standard deviation relative to the mean indicates high variability in the data, "
            f"which needs to be considered in further analysis.")))

    if high_skew:
        _sink.append(P(_(id=
            f"Perhatian khusus perlu diberikan pada variabel {', '.join(high_skew)} yang menunjukkan "
            f"tingkat kemiringan distribusi tinggi (|skewness| > 1.0). Variabel-variabel ini berpotensi "
            f"menurunkan akurasi model prediktif apabila tidak ditransformasi terlebih dahulu.",
            en=
            f"Special attention should be given to the variables {', '.join(high_skew)} which show "
            f"a high degree of distribution skewness (|skewness| > 1.0). These variables have the potential to "
            f"reduce the accuracy of predictive models if not transformed first.")))
    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB VI — STATISTIK DESKRIPTIF KATEGORIKAL
    # ========================================================================
    _sink = story if _inc_detailed else []
    _sink.append(Paragraph(_(id="BAB VI<br/>STATISTIK DESKRIPTIF KATEGORIKAL", en="CHAPTER VI<br/>CATEGORICAL DESCRIPTIVE STATISTICS"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="6.1. Tabel Statistik Deskriptif Variabel Kategorikal", en="6.1. Categorical Variable Descriptive Statistics Table"), 'sub_bab'))
    if cat_stats:
        cat_headers = [
            TH(_(id="Variabel", en="Variable")), TH(_(id="Unique", en="Unique")), TH(_(id="Modus (Terbanyak)", en="Mode (Most Frequent)")),
            TH(_(id="Frekuensi", en="Frequency")), TH(_(id="Proporsi (%)", en="Proportion (%)")),
            TH(_(id="Missing", en="Missing")), TH(_(id="Missing %", en="Missing %")),
        ]
        cat_rows = [cat_headers]
        for cs in cat_stats:
            cat_rows.append([
                TD(cs.get('Column', '—')),
                TD(str(cs.get('Unique', 0))),
                TD(str(cs.get('Mode', '—'))[:20]),
                TD(str(cs.get('Mode Freq', 0))),
                TD(str(cs.get('Mode %', '0%'))),
                TD(str(cs.get('Missing Count', 0))),
                TD(str(cs.get('Missing %', '0%'))),
            ])
        _sink.append(TB(cat_rows, [100, 45, 120, 55, 60, 45, 45]))
        _sink.append(Spacer(1, 8))
    else:
        _sink.append(P(_(id="Tidak terdapat variabel kategorikal dalam dataset yang dianalisis.", en="No categorical variables found in the analyzed dataset.")))
        _sink.append(PageBreak())


    if cat_stats:
        _sink.append(P(_(id="6.2. Analisis dan Interpretasi", en="6.2. Analysis and Interpretation"), 'sub_bab'))
    for cs in cat_stats:
        col = cs.get('Column', '—')
        uniq = cs.get('Unique', 0)
        mode = cs.get('Mode', '—')
        freq = cs.get('Mode Freq', 0)
        pct = cs.get('Mode %', '0%')
        miss = cs.get('Missing Count', 0)
        _cat_tail_id = (f"Terdapat <b>{miss}</b> nilai kosong pada variabel ini yang perlu ditangani "
                       f"melalui imputasi modus atau pendekatan lainnya." if miss > 0 else
                       f"Seluruh observasi pada variabel ini terisi lengkap tanpa nilai kosong.")
        _cat_tail_en = (f"There are <b>{miss}</b> empty values in this variable that need to be handled "
                       f"through mode imputation or other approaches." if miss > 0 else
                       f"All observations for this variable are completely filled with no missing values.")
        _sink.append(P(_(id=
            f"<b>{col}:</b> Variabel kategorikal ini memiliki <b>{uniq}</b> kategori unik. "
            f"Kategori yang paling dominan (modus) adalah <b>{mode}</b> yang muncul sebanyak "
            f"<b>{freq}</b> kali atau setara dengan <b>{pct}</b> dari total observasi. "
            f"Keberadaan kategori yang mendominasi secara signifikan perlu diwaspadai dalam "
            f"proses pemodelan karena dapat menyebabkan bias prediksi terhadap kelas mayoritas "
            f"(class imbalance). {_cat_tail_id}",
            en=
            f"<b>{col}:</b> This categorical variable has <b>{uniq}</b> unique categories. "
            f"The most dominant category (mode) is <b>{mode}</b> which appears "
            f"<b>{freq}</b> times or equivalent to <b>{pct}</b> of total observations. "
            f"The presence of a significantly dominant category needs to be monitored in "
            f"the modeling process as it can cause prediction bias toward the majority class "
            f"(class imbalance). {_cat_tail_en}")))
    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB VII — VISUALISASI DATA & INTERPRETASI
    # ========================================================================
    _sink = story if _inc_detailed else []
    _sink.append(Paragraph(_(id="BAB VII<br/>VISUALISASI DATA &amp; INTERPRETASI", en="CHAPTER VII<br/>DATA VISUALIZATION &amp; INTERPRETATION"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="7.1. Analisis Visual dan Interpretasi", en="7.1. Visual Analysis and Interpretation"), 'sub_bab'))
    _sink.append(P(_(id=
        "Visualisasi data merupakan komponen esensial dalam analisis eksploratori data (EDA) "
        "karena memungkinkan pengamat untuk mengidentifikasi pola, tren, anomali, dan hubungan "
        "antar variabel secara intuitif. Pada bagian ini disajikan serangkaian grafik yang dihasilkan "
        "secara otomatis oleh DS Generator, mencakup distribusi frekuensi, boxplot, scatter plot, "
        "serta heatmap korelasi. Setiap visualisasi dilengkapi dengan interpretasi analitis untuk "
        "memudahkan pemahaman.",
        en=
        "Data visualization is an essential component of exploratory data analysis (EDA) "
        "as it enables observers to identify patterns, trends, anomalies, and relationships "
        "between variables intuitively. This section presents a series of charts automatically generated "
        "by DS Generator, including frequency distributions, boxplots, scatter plots, "
        "and correlation heatmaps. Each visualization is accompanied by analytical interpretation to "
        "facilitate understanding.")))

    images_rendered = 0
    chart_sources = img_items if img_items else (img_paths or [])

    # Group images by category for sub-sectioning
    cat_map = {}
    if chart_sources:
        for item in chart_sources:
            if isinstance(item, (list, tuple)):
                path = item[0]
                label = item[1] if len(item) > 1 else ''
            else:
                path = item
                label = ''
            # Determine category from label or filename
            lower_label = label.lower() if label else ''
            lower_path = path.lower() if isinstance(path, str) else ''
            if any(k in lower_label or k in lower_path for k in ['histogram', 'distribusi', 'distribution']):
                cat = 'Distribusi Data'
            elif any(k in lower_label or k in lower_path for k in ['boxplot']):
                cat = 'Analisis Boxplot'
            elif any(k in lower_label or k in lower_path for k in ['scatter', 'korelasi', 'correlation', 'heatmap']):
                cat = 'Analisis Korelasi'
            elif any(k in lower_label or k in lower_path for k in ['bar', 'kategorikal', 'category']):
                cat = 'Distribusi Kategorikal'
            elif any(k in lower_label or k in lower_path for k in ['pie']):
                cat = 'Proporsi Kategorikal'
            elif any(k in lower_label or k in lower_path for k in ['line', 'time', 'series', 'tren', 'trend']):
                cat = 'Analisis Time Series'
            else:
                cat = 'Visualisasi Lainnya'
            cat_map.setdefault(cat, []).append((path, label))

    # Find and embed correlation heatmap first
    heatmap_path = None
    heatmap_label = ""
    for cat, items in cat_map.items():
        for path, label in items:
            if 'heatmap' in os.path.basename(path).lower() or 'korelasi' in label.lower():
                heatmap_path = path
                heatmap_label = label
                break
        if heatmap_path:
            break

    # Render images by group
    for cat_name in ['Distribusi Data', 'Analisis Boxplot', 'Analisis Korelasi',
                     'Distribusi Kategorikal', 'Proporsi Kategorikal', 'Analisis Time Series',
                     'Visualisasi Lainnya']:
        if cat_name not in cat_map:
            continue
        items = cat_map[cat_name]

        # Sub-heading
        sub_num = {
            'Distribusi Data': '7.2',
            'Analisis Boxplot': '7.3',
            'Analisis Korelasi': '7.4',
            'Distribusi Kategorikal': '7.5',
            'Proporsi Kategorikal': '7.6',
            'Analisis Time Series': '7.7',
            'Visualisasi Lainnya': '7.8',
        }.get(cat_name, '7.8')
        _sink.append(P(f"{sub_num}. {_cat_label_map.get(cat_name, cat_name)}", 'sub_bab'))

        if cat_name == 'Analisis Korelasi' and heatmap_path:
            img = _try_img(heatmap_path, max_width=440, max_height=300)
            if img:
                _sink.append(Spacer(1, 4))
                _sink.append(img)
                cap = heatmap_label or _(id=
                    "<i>Gambar 7.4: Matriks Korelasi Pearson antar Variabel Numerik. "
                    "Nilai dalam sel menunjukkan koefisien korelasi (r). Semakin mendekati |1|, "
                    "semakin kuat hubungan linier antar kedua variabel. Warna biru tua menandakan "
                    "korelasi positif, sementara warna merah menandakan korelasi negatif.</i>",
                    en=
                    "<i>Figure 7.4: Pearson Correlation Matrix between Numeric Variables. "
                    "Values in cells show the correlation coefficient (r). The closer to |1|, "
                    "the stronger the linear relationship between the two variables. Dark blue indicates "
                    "a positive correlation, while red indicates a negative correlation.</i>")
                _sink.append(CAP(cap))
                images_rendered += 1

        for path, label in items:
            if heatmap_path and path == heatmap_path:
                continue
            img = _try_img(path, max_width=440, max_height=260)
            if img:
                if images_rendered > 0:
                    _sink.append(Spacer(1, 6))
                _sink.append(img)
                if label:
                    _sink.append(CAP(f"<i>{label}</i>"))
                images_rendered += 1

    if images_rendered == 0:
        _sink.append(P(_(id=
            "Visualisasi grafis yang disajikan pada dashboard interaktif DS Generator tidak dapat "
            "dirender ke dalam dokumen PDF ini. Silakan merujuk pada dashboard untuk melihat grafik "
            "dan diagram interaktif secara lengkap.",
            en=
            "Graphical visualizations presented on the DS Generator interactive dashboard cannot be "
            "rendered into this PDF document. Please refer to the dashboard to view the charts "
            "and interactive diagrams in full.")))
    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB VII-A — ANALISIS TIME SERIES (kondisional)
    # ========================================================================
    # Auto-detect if time series insights exist
    has_ts = any(
        ins.get('type', '') == 'timeseries'
        for ins in (auto_insights or [])
    )
    if has_ts and _inc_detailed:
        _sink.append(Paragraph(_(id="BAB VII-A<br/>ANALISIS TIME SERIES", en="CHAPTER VII-A<br/>TIME SERIES ANALYSIS"), s['bab']))
        _sink.append(Spacer(1, 8))

        _sink.append(P(_(id="7A.1. Analisis Deret Waktu", en="7A.1. Time Series Analysis"), 'sub_bab'))
        _sink.append(P(_(id=
            "Apabila dataset mengandung kolom bertipe datetime atau timestamp, DS Generator secara "
            "otomatis melakukan analisis deret waktu (time series) untuk mengidentifikasi pola "
            "temporal, musiman, serta tren jangka panjang dalam data. Analisis ini penting untuk "
            "mendukung perencanaan strategis dan pengambilan keputusan berbasis proyeksi.",
            en=
            "If the dataset contains datetime or timestamp columns, DS Generator automatically "
            "performs time series analysis to identify temporal patterns, "
            "seasonality, and long-term trends in the data. This analysis is important for "
            "supporting strategic planning and projection-based decision making.")))

        # Time series images
        ts_count = 0
        if chart_sources:
            for item in chart_sources:
                if isinstance(item, (list, tuple)):
                    path = item[0]
                    label = item[1] if len(item) > 1 else ''
                else:
                    path = item
                    label = ''
                if any(k in os.path.basename(path).lower() or k in label.lower()
                       for k in ['line', 'time', 'series', 'tren', 'trend']):
                    img = _try_img(path, max_width=440, max_height=260)
                    if img:
                        if ts_count > 0:
                            _sink.append(Spacer(1, 6))
                        _sink.append(img)
                        if label:
                            _sink.append(CAP(f"<i>{label}</i>"))
                        ts_count += 1

        if ts_count == 0:
            _sink.append(P(_(id=
                "Grafik time series tidak tersedia untuk dirender dalam format PDF. "
                "Silakan lihat panel Time Series pada dashboard untuk analisis temporal interaktif.",
                en=
                "Time series charts are not available for rendering in PDF format. "
                "Please see the Time Series panel on the dashboard for interactive temporal analysis.")))

        # Time series insights in O-A-I
        ts_insights = [ins for ins in (auto_insights or []) if ins.get('type') == 'timeseries']
        for ins in ts_insights:
            _sink.append(P(f"<b>{ins.get('title', _(id='Temuan Time Series', en='Time Series Finding'))}</b>", 'h2'))
            obs = ins.get('observation', '')
            ana = ins.get('analysis', '')
            imp = ins.get('implication', '')
            if obs:
                _sink.append(P(_(id=f"<b>Observasi:</b> {obs}", en=f"<b>Observation:</b> {obs}")))
            if ana:
                _sink.append(P(_(id=f"<b>Analisis:</b> {ana}", en=f"<b>Analysis:</b> {ana}")))
            if imp:
                _sink.append(P(_(id=f"<b>Implikasi:</b> {imp}", en=f"<b>Implication:</b> {imp}")))

        _sink.append(PageBreak())
    _sink = story

    # ════════════════════════════════════════════════════════════════════════
    # CORRELATION — standalone (hanya jika correlation dicentang, detailed tidak)
    # ════════════════════════════════════════════════════════════════════════
    if _inc_correlation and not _inc_detailed:
        _sink.append(Paragraph(_(id="ANALISIS KORELASI", en="CORRELATION ANALYSIS"), s['bab']))
        _sink.append(Spacer(1, 8))
        _sink.append(P(_(id="Analisis korelasi bertujuan untuk mengidentifikasi hubungan linier "
                        "antar variabel numerik dalam dataset. Koefisien korelasi Pearson (r) "
                        "digunakan sebagai indikator kekuatan dan arah hubungan, dengan rentang "
                        "nilai -1 hingga +1.",
                        en="Correlation analysis aims to identify linear relationships "
                        "between numeric variables in the dataset. The Pearson correlation coefficient (r) "
                        "is used as an indicator of relationship strength and direction, with a range "
                        "of values from -1 to +1.")))
        _corr_heatmap = None
        _corr_label = ''
        if chart_sources:
            for _item in chart_sources:
                _p = _item[0] if isinstance(_item, (list, tuple)) else _item
                _l = _item[1] if isinstance(_item, (list, tuple)) and len(_item) > 1 else ''
                if 'heatmap' in os.path.basename(str(_p)).lower() or 'korelasi' in _l.lower():
                    _img = _try_img(_p, max_width=440, max_height=300)
                    if _img:
                        _corr_heatmap = _img
                        _corr_label = _l
                        break
        if _corr_heatmap:
            _sink.append(Spacer(1, 6))
            _sink.append(_corr_heatmap)
            _sink.append(CAP(_corr_label or _(id="<i>Matriks Korelasi Pearson antar Variabel Numerik.</i>", en="<i>Pearson Correlation Matrix between Numeric Variables.</i>")))
        # Cari insight korelasi dari auto_insights
        for _ins in (auto_insights or []):
            if 'korelasi' in (_ins.get('title', '') or '').lower() or 'correlation' in (_ins.get('title', '') or '').lower():
                _sink.append(P(f"<b>{_ins.get('title', _(id='Insight Korelasi', en='Correlation Insight'))}</b>", 'h2'))
                _o = _ins.get('observation', '')
                _a = _ins.get('analysis', '')
                _i = _ins.get('implication', '')
                if _o: _sink.append(P(_(id=f"<b>Observasi:</b> {_o}", en=f"<b>Observation:</b> {_o}")))
                if _a: _sink.append(P(_(id=f"<b>Analisis:</b> {_a}", en=f"<b>Analysis:</b> {_a}")))
                if _i: _sink.append(P(_(id=f"<b>Implikasi:</b> {_i}", en=f"<b>Implication:</b> {_i}")))
                break
        _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB VIII — PROSES DATA CLEANING
    # ========================================================================
    _sink = story if _inc_summary else []
    _sink.append(Paragraph(_(id="BAB VIII<br/>PROSES DATA CLEANING", en="CHAPTER VIII<br/>DATA CLEANING PROCESS"), s['bab']))
    _sink.append(Spacer(1, 8))

    stages = cleaning_history or []

    if not needs_clean and is_cleaned:
        _sink.append(P(_(id=
            "Dataset telah melalui proses pembersihan secara menyeluruh. Berikut adalah "
            "dokumentasi tahapan pembersihan yang telah diterapkan pada dataset.",
            en=
            "The dataset has undergone a thorough cleaning process. The following is the "
            "documentation of cleaning stages that have been applied to the dataset.")))
    elif needs_clean:
        _sink.append(P(_(id=
            "Dataset saat ini masih dalam kondisi mentah (raw) dan belum menjalani proses "
            "pembersihan. Meskipun demikian, sistem telah menyiapkan pipeline pembersihan "
            "yang siap dijalankan. Ringkasan perbandingan sebelum dan sesudah cleaning "
            "disajikan apabila proses pembersihan telah dilakukan.",
            en=
            "The dataset is currently still in raw condition and has not undergone any "
            "cleaning process. However, the system has prepared a cleaning pipeline "
            "ready to be executed. A comparison summary before and after cleaning "
            "will be presented once the cleaning process has been performed.")))
    else:
        _sink.append(P(_(id=
            "Berdasarkan hasil audit, dataset tidak memerlukan tindakan pembersihan lebih lanjut "
            "karena seluruh indikator kualitas telah berada dalam ambang batas yang dapat diterima.",
            en=
            "Based on the audit results, the dataset does not require further cleaning actions "
            "as all quality indicators are within acceptable thresholds.")))

    _sink.append(P(_(id="8.1. Dokumentasi Tahapan Pembersihan", en="8.1. Cleaning Stages Documentation"), 'sub_bab'))
    if stages:
        stage_data = [[TH(_(id="No.", en="No.")), TH(_(id="Waktu", en="Time")), TH(_(id="Tahapan", en="Stage")), TH(_(id="Deskripsi", en="Description"))]]
        for idx, st in enumerate(stages, 1):
            ts = st.get('timestamp', '')[:19] if st.get('timestamp') else ''
            label = st.get('label', '—')[:30]
            desc = st.get('description', '—')[:60]
            stage_data.append([
                TD(str(idx)),
                TD(ts),
                TD(label),
                TD(desc),
            ])
        _sink.append(TB(stage_data, [30, 120, 130, 224]))
    else:
        _sink.append(P(_(id="Belum terdapat riwayat pembersihan yang tercatat untuk sesi ini.", en="No cleaning history recorded for this session.")))
    _sink.append(Spacer(1, 10))

    _sink.append(P(_(id="8.2. Perbandingan Metrik Sebelum dan Sesudah Pembersihan", en="8.2. Metric Comparison Before and After Cleaning"), 'sub_bab'))
    rows_b = sb.get('rows_before', rows_total)
    rows_a = sb.get('rows_after', rows_total)
    cols_b = sb.get('cols_before', cols_total)
    cols_a = sb.get('cols_after', cols_total)
    miss_b = sb.get('missing_before', 0)
    miss_a = sb.get('missing_after', 0)
    dups_rem = sb.get('duplicates_removed', 0)

    _Dihapus = _(id="Dihapus", en="Removed")
    _Tetap = _(id="Tetap", en="Unchanged")
    _Berkurang = _(id="Berkurang", en="Reduced")
    diff_data = [
        [TH(_(id="Metrik", en="Metric")), TH(_(id="Sebelum (Raw)", en="Before (Raw)")), TH(_(id="Sesudah (Cleaned)", en="After (Cleaned)")), TH(_(id="Perubahan", en="Change"))],
        [TD(_(id="Jumlah Baris", en="Row Count")), TD(str(rows_b)), TD(str(rows_a)),
         TD(f"{_Dihapus if rows_b > rows_a else _Tetap}: {rows_b - rows_a} " + _(id="baris", en="rows"))],
        [TD(_(id="Jumlah Kolom", en="Column Count")), TD(str(cols_b)), TD(str(cols_a)),
         TD(f"{_Dihapus if cols_b > cols_a else _Tetap}: {cols_b - cols_a} " + _(id="kolom", en="columns"))],
        [TD(_(id="Sel Kosong (Missing)", en="Empty Cells (Missing)")), TD(str(miss_b)), TD(str(miss_a)),
         TD(f"{_Berkurang if miss_b > miss_a else _Tetap}: {miss_b - miss_a} " + _(id="sel", en="cells"))],
        [TD(_(id="Baris Duplikat", en="Duplicate Rows")), TD(str(dups_rem)), TD("0"),
         TD(_(id="100% duplikasi dihilangkan", en="100% duplication removed") if dups_rem > 0 else _(id="Tidak ada duplikasi", en="No duplication"))],
    ]
    _sink.append(TB(diff_data, [140, 110, 130, 124]))
    _sink.append(Spacer(1, 8))

    # Cleaning summary narrative
    if steps_taken > 0:
        _sink.append(P(_(id=
            f"Telah dilakukan <b>{steps_taken}</b> tahapan pembersihan pada dataset ini. "
            f"Dari <b>{rows_b}</b> baris awal, data berkurang menjadi <b>{rows_a}</b> baris setelah "
            f"penghapusan duplikat dan baris kosong. Jumlah sel kosong berhasil ditekan dari "
            f"<b>{miss_b}</b> menjadi <b>{miss_a}</b> melalui proses imputasi. "
            f"Seluruh proses ini terdokumentasi dalam riwayat pembersihan sistem.",
            en=
            f"A total of <b>{steps_taken}</b> cleaning stages have been performed on this dataset. "
            f"From <b>{rows_b}</b> initial rows, the data was reduced to <b>{rows_a}</b> rows after "
            f"removal of duplicates and empty rows. The number of empty cells was reduced from "
            f"<b>{miss_b}</b> to <b>{miss_a}</b> through the imputation process. "
            f"All of these processes are documented in the system cleaning history.")))
    else:
        _sink.append(P(_(id=
            "Belum ada langkah pembersihan yang diterapkan pada dataset ini. Sistem merekomendasikan "
            "untuk menjalankan pipeline pembersihan guna memastikan data siap dianalisis lebih lanjut.",
            en=
            "No cleaning steps have been applied to this dataset yet. The system recommends "
            "running the cleaning pipeline to ensure the data is ready for further analysis.")))
    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB IX — TEMUAN KUNCI & INSIGHT OTOMATIS
    # ========================================================================
    _sink = story if _inc_action else []
    _sink.append(Paragraph(_(id="BAB IX<br/>TEMUAN KUNCI &amp; INSIGHT OTOMATIS", en="CHAPTER IX<br/>KEY FINDINGS &amp; AUTOMATIC INSIGHTS"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="9.1. Pendahuluan", en="9.1. Introduction"), 'sub_bab'))
    _sink.append(P(_(id=
        "DS Generator dilengkapi dengan mesin pembangkit insight otomatis (Smart Insights Algorithm) "
        "yang mampu mengekstraksi pola-pola penting dari data secara real-time. Setiap insight "
        "disajikan dalam kerangka <b>Observasi-Analisis-Implikasi (O-A-I)</b> untuk memudahkan "
        "pemahaman dan pengambilan tindakan. Kerangka ini memastikan bahwa setiap temuan tidak "
        "hanya dilaporkan secara deskriptif, tetapi juga dianalisis secara kritis dan dikaitkan "
        "dengan implikasi bisnis atau teknisnya.",
        en=
        "DS Generator is equipped with an automatic insight generation engine (Smart Insights Algorithm) "
        "capable of extracting important patterns from data in real-time. Each insight "
        "is presented within the <b>Observation-Analysis-Implication (O-A-I)</b> framework to facilitate "
        "understanding and action-taking. This framework ensures that each finding is "
        "not only reported descriptively, but also critically analyzed and linked "
        "to its business or technical implications.")))

    non_ts_insights = [ins for ins in (auto_insights or []) if ins.get('type') != 'timeseries']

    _sink.append(P(_(id="9.2. Daftar Insight", en="9.2. Insights List"), 'sub_bab'))
    if non_ts_insights:
        for i, ins in enumerate(non_ts_insights, 1):
            _sink.append(P(f"<b>9.{i+2}. {ins.get('title', _(id=f'Temuan {i}', en=f'Finding {i}'))}</b>"))
            obs = ins.get('observation', '')
            ana = ins.get('analysis', '')
            imp = ins.get('implication', '')
            if obs and ana and imp:
                _sink.append(P(_(id=f"<b>Observasi:</b> {obs}", en=f"<b>Observation:</b> {obs}")))
                _sink.append(P(_(id=f"<b>Analisis:</b> {ana}", en=f"<b>Analysis:</b> {ana}")))
                _sink.append(P(_(id=f"<b>Implikasi:</b> {imp}", en=f"<b>Implication:</b> {imp}")))
            else:
                _sink.append(P(ins.get('desc', '')))
            _sink.append(Spacer(1, 3))
    else:
        _sink.append(P(_(id=
            "Belum terdapat insight otomatis yang dapat dirumuskan untuk dataset ini. "
            "Hal ini dapat disebabkan oleh ukuran dataset yang terlalu kecil atau variasi "
            "data yang tidak mencukupi untuk mendeteksi pola yang bermakna.",
            en=
            "No automatic insights could be formulated for this dataset yet. "
            "This may be due to the dataset being too small or having insufficient "
            "data variation to detect meaningful patterns.")))
    # ── 9.3 AI-Powered Interpretation ─────────────────────────────────
    if ai_interpretation:
        _sink.append(P(_(id="9.3. Interpretasi Berbasis AI", en="9.3. AI-Powered Interpretation"), 'sub_bab'))
        _sink.append(P(_(id=
            "Bagian ini menyajikan interpretasi mendalam yang dihasilkan oleh kecerdasan buatan (AI) "
            "berdasarkan analisis menyeluruh terhadap statistik, korelasi, distribusi, dan kualitas data. "
            "Interpretasi menggunakan kerangka <b>Observasi-Analisis-Implikasi (O-A-I)</b> untuk setiap temuan.",
            en=
            "This section presents an in-depth interpretation generated by artificial intelligence (AI) "
            "based on a comprehensive analysis of statistics, correlations, distributions, and data quality. "
            "The interpretation uses the <b>Observation-Analysis-Implication (O-A-I)</b> framework for each finding.")))
        _sink.append(Spacer(1, 6))

        _sink.append(P(_(id="9.3.1. Ringkasan Eksekutif", en="9.3.1. Executive Summary"), 'sub_bab'))
        _sink.append(P(ai_interpretation.get('summary', '')))

        kf = ai_interpretation.get('key_findings', [])
        if kf:
            _sink.append(P(_(id="9.3.2. Temuan Utama", en="9.3.2. Key Findings"), 'sub_bab'))
            for f in kf:
                _sink.append(P(f"• {f}"))

        recs = ai_interpretation.get('recommendations', [])
        if recs:
            _sink.append(P(_(id="9.3.3. Rekomendasi", en="9.3.3. Recommendations"), 'sub_bab'))
            for r in recs:
                _sink.append(P(f"• {r}"))

        conc = ai_interpretation.get('conclusion', '')
        if conc:
            _sink.append(P(_(id="9.3.4. Kesimpulan", en="9.3.4. Conclusion"), 'sub_bab'))
            _sink.append(P(conc))
    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB X — REKOMENDASI STRATEGIS
    # ========================================================================
    _sink = story if _inc_action else []
    _sink.append(Paragraph(_(id="BAB X<br/>REKOMENDASI STRATEGIS", en="CHAPTER X<br/>STRATEGIC RECOMMENDATIONS"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="10.1. Latar Belakang Rekomendasi", en="10.1. Recommendation Background"), 'sub_bab'))
    _sink.append(P(_(id=
        "Berdasarkan seluruh rangkaian analisis yang telah dilakukan — mulai dari audit kualitas data, "
        "statistik deskriptif, visualisasi, hingga insight otomatis — bagian ini menyajikan "
        "sejumlah rekomendasi strategis yang dapat dijadikan acuan oleh para pemangku kepentingan "
        "dalam pengambilan keputusan berbasis data. Rekomendasi disusun berdasarkan temuan "
        "kuantitatif dan disesuaikan dengan konteks praktis organisasi.",
        en=
        "Based on the entire series of analyses that have been conducted — from data quality audits, "
        "descriptive statistics, visualizations, to automatic insights — this section presents "
        "a number of strategic recommendations that can serve as references for stakeholders "
        "in data-driven decision making. Recommendations are compiled based on quantitative "
        "findings and tailored to the practical context of the organization.")))

    _sink.append(P(_(id="10.2. Rekomendasi Berdasarkan Temuan", en="10.2. Recommendations Based on Findings"), 'sub_bab'))
    recoms = []

    if total_missing > 0:
        recoms.append((
            _(id="R1 — Penguatan Validasi Input Data", en="R1 — Strengthening Data Input Validation"),
            _(id=f"Ditemukan <b>{total_missing}</b> sel kosong dalam dataset. Manajemen disarankan untuk "
            f"mengintegrasikan mekanisme validasi lapangan (field-level validation) pada sistem "
            f"pengumpulan data guna memastikan bahwa seluruh variabel kritis terisi secara lengkap "
            f"sebelum data masuk ke basis data utama. Langkah ini akan mengurangi kebutuhan imputasi "
            f"retrospektif dan meningkatkan integritas data sejak titik entri.",
            en=f"Found <b>{total_missing}</b> empty cells in the dataset. Management is advised to "
            f"integrate field-level validation mechanisms into the data collection system to ensure "
            f"that all critical variables are completely filled before data enters the main database. "
            f"This step will reduce the need for retrospective imputation and improve data integrity "
            f"from the point of entry.")))

    if total_outliers > 0:
        recoms.append((
            _(id="R2 — Investigasi dan Penanganan Nilai Ekstrem", en="R2 — Investigation and Handling of Extreme Values"),
            _(id=f"Sistem mendeteksi <b>{total_outliers}</b> nilai outlier yang tersebar di berbagai kolom "
            f"numerik. Disarankan agar tim operasional melakukan validasi silang terhadap nilai-nilai "
            f"tersebut untuk membedakan apakah outlier merupakan anomali yang sah secara bisnis "
            f"(misalnya, lonjakan transaksi musiman) atau kesalahan entri data. Outlier yang terbukti "
            f"sebagai kesalahan sebaiknya ditangani melalui teknik capping atau imputasi sebelum "
            f"data digunakan untuk pemodelan prediktif.",
            en=f"The system detects <b>{total_outliers}</b> outlier values spread across various numeric "
            f"columns. It is recommended that the operational team perform cross-validation of these "
            f"values to distinguish whether outliers are legitimate business anomalies "
            f"(e.g., seasonal transaction spikes) or data entry errors. Outliers proven to be "
            f"errors should be handled through capping or imputation techniques before "
            f"the data is used for predictive modeling.")))

    if total_dups > 0:
        recoms.append((
            _(id="R3 — Pencegahan Duplikasi Data", en="R3 — Data Duplication Prevention"),
            _(id=f"Terdeteksi <b>{total_dups}</b> baris duplikat dalam dataset. Tim pengelola data disarankan "
            f"untuk menerapkan constraint keunikan (primary key atau unique constraint) pada basis data "
            f"transaksional guna mencegah terjadinya duplikasi entri di masa mendatang. "
            f"Pembersihan duplikat secara berkala juga perlu dijadwalkan sebagai bagian dari "
            f"tata kelola data (data governance).",
            en=f"Detected <b>{total_dups}</b> duplicate rows in the dataset. The data management team is advised "
            f"to apply uniqueness constraints (primary key or unique constraint) on the transactional "
            f"database to prevent duplicate entries in the future. "
            f"Regular duplicate cleaning should also be scheduled as part of "
            f"data governance.")))

    if high_skew:
        cols_str = ", ".join(high_skew)
        recoms.append((
            _(id="R4 — Transformasi Distribusi Data", en="R4 — Data Distribution Transformation"),
            _(id=f"Variabel {cols_str} menunjukkan kemiringan distribusi yang tinggi (|skewness| > 1.0). "
            f"Sebelum menerapkan algoritma pemodelan yang mengasumsikan normalitas (seperti regresi "
            f"linier, ANOVA, atau LDA), disarankan untuk melakukan transformasi logaritma (log-transform) "
            f"atau Box-Cox power transform guna mengurangi bias estimasi dan meningkatkan performa model.",
            en=f"Variables {cols_str} show high distribution skewness (|skewness| > 1.0). "
            f"Before applying modeling algorithms that assume normality (such as linear "
            f"regression, ANOVA, or LDA), it is recommended to perform log-transformation "
            f"or Box-Cox power transform to reduce estimation bias and improve model performance.")))

    # Rekomendasi berdasarkan insight
    if non_ts_insights:
        for ins in non_ts_insights:
            imp = ins.get('implication', '')
            if imp and len(imp) > 40:
                title = ins.get('title', _(id='Rekomendasi', en='Recommendation'))
                _rN_label = _(id=f"R{len(recoms)+1} — Tindak Lanjut: {title}", en=f"R{len(recoms)+1} — Follow-up: {title}")
                recoms.append((
                    _rN_label,
                    imp))

    _r5_label = _(id="R{} — Pembersihan Data Berkala (Data Governance)", en="R{} — Periodic Data Cleaning (Data Governance)")
    recoms.append((
        _r5_label.format(len(recoms) + 1),
        _(id="Disarankan untuk menjadwalkan proses pembersihan data secara rutin menggunakan DS Generator "
        "sebelum laporan akhir periode (bulanan/kuartalan) diekspor ke departemen eksekutif. "
        "Langkah ini akan menjamin bahwa setiap keputusan strategis didasarkan pada data yang "
        "telah terverifikasi kualitasnya.",
        en="It is recommended to schedule regular data cleaning processes using DS Generator "
        "before end-of-period reports (monthly/quarterly) are exported to executive departments. "
        "This step will ensure that every strategic decision is based on data "
        "whose quality has been verified.")))

    for label, detail in recoms:
        _sink.append(P(f"<b>{label}:</b> {detail}"))
        _sink.append(Spacer(1, 4))

    if not recoms:
        _sink.append(P(_(id=
            "Berdasarkan hasil analisis, tidak ditemukan isu signifikan yang memerlukan "
            "rekomendasi strategis khusus. Dataset dalam kondisi baik dan siap digunakan "
            "untuk analisis lebih lanjut.",
            en=
            "Based on the analysis results, no significant issues were found that require "
            "specific strategic recommendations. The dataset is in good condition and ready "
            "for further analysis.")))

    _sink.append(PageBreak())
    _sink = story

    # ========================================================================
    # BAB XI — PENUTUP
    # ========================================================================
    _sink = story if _inc_action else []
    _sink.append(Paragraph(_(id="BAB XI<br/>PENUTUP", en="CHAPTER XI<br/>CONCLUSION"), s['bab']))
    _sink.append(Spacer(1, 8))

    _sink.append(P(_(id="11.1. Kesimpulan Akhir", en="11.1. Final Conclusion"), 'sub_bab'))
    total_cols = len(cols_q)
    ok_count = sum(1 for c in cols_q if c.get('issues', '') == 'OK')
    needs_attention = total_cols - ok_count
    _sink.append(P(_(id=
        f"Laporan ini telah menyajikan analisis komprehensif terhadap dataset <b>{filename}</b> "
        f"yang terdiri dari <b>{rows_total}</b> observasi dan <b>{total_cols}</b> variabel. "
        f"Berdasarkan hasil audit kualitas data, <b>{ok_count}</b> dari <b>{total_cols}</b> kolom "
        f"dinyatakan dalam kondisi baik, sementara <b>{needs_attention}</b> kolom memerlukan "
        f"perhatian lebih lanjut. Analisis statistik deskriptif telah mengungkap karakteristik "
        f"distribusi dari setiap variabel, termasuk tendensi sentral, penyebaran, dan kemiringan data.",
        en=
        f"This report has presented a comprehensive analysis of the dataset <b>{filename}</b> "
        f"consisting of <b>{rows_total}</b> observations and <b>{total_cols}</b> variables. "
        f"Based on the data quality audit results, <b>{ok_count}</b> of <b>{total_cols}</b> columns "
        f"are declared in good condition, while <b>{needs_attention}</b> columns require "
        f"further attention. Descriptive statistical analysis has revealed the distribution "
        f"characteristics of each variable, including central tendency, spread, and skewness.")))

    if is_cleaned:
        _sink.append(P(_(id=
            f"Proses pembersihan data telah dilakukan melalui <b>{steps_taken}</b> tahapan, "
            f"berhasil mengurangi jumlah sel kosong dan menghilangkan duplikasi data. "
            f"Dataset saat ini berada dalam kondisi bersih dan siap untuk analisis lebih lanjut.",
            en=
            f"The data cleaning process has been carried out through <b>{steps_taken}</b> stages, "
            f"successfully reducing the number of empty cells and eliminating data duplication. "
            f"The dataset is currently in a clean state and ready for further analysis.")))
    else:
        _sink.append(P(_(id=
            "Dataset masih dalam kondisi mentah dan belum melalui proses pembersihan. "
            "Disarankan untuk menjalankan pipeline pembersihan DS Generator guna memastikan "
            "data siap digunakan untuk analisis lanjutan atau pemodelan prediktif.",
            en=
            "The dataset is still in raw condition and has not undergone any cleaning process. "
            "It is recommended to run the DS Generator cleaning pipeline to ensure "
            "the data is ready for further analysis or predictive modeling.")))

    _sink.append(P(_(id="11.2. Saran Penggunaan", en="11.2. Usage Suggestions"), 'sub_bab'))
    _sink.append(P(_(id=
        "DS Generator menyediakan berbagai fitur lanjutan yang dapat dieksplorasi lebih mendalam, "
        "termasuk analisis korelasi interaktif, pemodelan time series, serta visualisasi "
        "dinamis berbasis Plotly. Pengguna disarankan untuk melakukan ekspor data bersih ke "
        "format CSV atau Excel guna keperluan analisis tambahan menggunakan perangkat lunak "
        "statistik lainnya. Dokumentasi sistem dan panduan penggunaan tersedia pada portal "
        "dokumentasi resmi DS Generator.",
        en=
        "DS Generator provides various advanced features that can be explored in greater depth, "
        "including interactive correlation analysis, time series modeling, and dynamic "
        "Plotly-based visualizations. Users are advised to export clean data to "
        "CSV or Excel format for additional analysis using other statistical "
        "software. System documentation and usage guides are available on the "
        "official DS Generator documentation portal.")))

    _sink.append(P(_(id="11.3. Pernyataan Penutup", en="11.3. Closing Statement"), 'sub_bab'))
    _sink.append(P(_(id=
        "Demikian laporan analisis data ini disusun oleh Kelompok 2 Program Studi Data Science, "
        "Institut Teknologi dan Sains Bandung. Seluruh temuan dan rekomendasi yang disajikan "
        "didasarkan pada data yang tersedia pada saat analisis dilakukan. Data dan hasil analisis "
        "ini bersifat rahasia dan hanya diperuntukkan bagi pihak-pihak yang berkepentingan.",
        en=
        "This data analysis report has been prepared by Group 2 of the Data Science Study Program, "
        "Institut Teknologi dan Sains Bandung. All findings and recommendations presented "
        "are based on data available at the time of analysis. The data and analysis results "
        "are confidential and intended only for authorized parties.")))

    # ── Build PDF ──────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(dest_path, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=72, bottomMargin=72)
    doc.build(story, canvasmaker=NumberedCanvas, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
    return True
