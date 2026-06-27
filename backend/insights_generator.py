"""
backend/insights_generator.py
Week 15 — Intelligent Insight Generator (Bilingual: EN + ID)

Menggunakan kerangka O-A-I (Observation → Analysis → Implication)
untuk setiap insight agar tidak sekadar deskriptif, tetapi juga
interpretatif dan relevan terhadap tahap pemodelan.

Output format per insight:
  { type, icon, title, desc,
    observation, analysis, implication }

Returns dict: { 'en': [...], 'id': [...] }
"""

import numpy as np
import pandas as pd
import re
from scipy import stats as scipy_stats

from backend.data_sanitizer import sanitize_series, safe_corr_matrix


def _pct(a, b):
    return round(a / b * 100, 1) if b > 0 else 0.0


def _normality(series, max_sample=5000):
    clean = sanitize_series(series)
    if len(clean) < 3 or clean.nunique() <= 1:
        return 'N/A'
    sample = clean if len(clean) <= max_sample else clean.sample(max_sample, random_state=42)
    try:
        _, p = scipy_stats.shapiro(sample)
        return 'Normal' if p > 0.05 else 'Not Normal'
    except Exception:
        return 'N/A'


def _outlier_count(series):
    clean = sanitize_series(series)
    if len(clean) < 4:
        return 0
    try:
        q1, q3 = float(clean.quantile(0.25)), float(clean.quantile(0.75))
        iqr = q3 - q1
        if iqr == 0:
            return 0
        return int(((clean < q1 - 1.5 * iqr) | (clean > q3 + 1.5 * iqr)).sum())
    except Exception:
        return 0


def _model_impact_from_skew(skw):
    """
    Return rekomendasi model berdasarkan nilai skewness.
    """
    skw = abs(skw)
    if skw > 2:
        return (
            "Distribusi highly skewed menyarankan penggunaan teknik transformasi "
            "logaritma atau Box-Cox sebelum pemodelan parametrik. Alternatifnya, "
            "algoritma tree-based (Random Forest, XGBoost) yang tidak bergantung "
            "pada asumsi normalitas lebih toleran terhadap distribusi semacam ini."
        )
    elif skw > 1:
        return (
            "Skewness moderat ini mengindikasikan bahwa model parametrik seperti "
            "regresi linier mungkin menghasilkan estimasi yang bias pada ekor distribusi. "
            "Transformasi log atau sqrt direkomendasikan sebelum pemodelan. "
            "Untuk pendekatan non-parametrik, Mann-Whitney atau Kruskal-Wallis "
            "dapat digunakan sebagai alternatif uji hipotesis."
        )
    else:
        return (
            "Distribusi relatif simetris sehingga model parametrik (regresi linier, "
            "ANOVA, t-test) dapat digunakan tanpa transformasi khusus."
        )


def _multicollinearity_warning(corr_df, valid_cols, threshold=0.7):
    """
    Deteksi potensi multikolinearitas dari matriks korelasi.
    Returns list of dict: {pair, r, risk, implication}
    """
    warnings = []
    cols_list = list(corr_df.columns)
    for i in range(len(cols_list)):
        for j in range(i + 1, len(cols_list)):
            val = corr_df.iloc[i, j]
            if pd.notna(val) and abs(val) >= threshold:
                warnings.append({
                    'pair': (cols_list[i], cols_list[j]),
                    'r': round(float(val), 3),
                    'risk': 'high' if abs(val) >= 0.85 else 'moderate',
                })
    return warnings


def generate_auto_insights(df, num_cols, cat_cols, ts_insights=None):
    """
    Menghasilkan list insight otomatis dalam 2 bahasa dengan kerangka O-A-I.

    Parameters
    ----------
    df          : DataFrame lengkap
    num_cols    : list kolom numerik
    cat_cols    : list kolom kategorik
    ts_insights : list insight dari time_series.py (opsional)

    Returns
    -------
    dict: { 'en': list[dict], 'id': list[dict] }
    """
    insights_en = []
    insights_id = []
    total_rows  = len(df)
    total_cells = df.size

    def _extract_oai(text, markers):
        """Parse marker-delimited text into (observation, analysis, implication)."""
        pattern = '|'.join(re.escape(m) for m in markers)
        parts = re.split(pattern, text)
        parts = [p.strip().rstrip('.') for p in parts]
        while len(parts) < 4:
            parts.append('')
        return parts[1], parts[2], parts[3]

    def _parse_oai(desc_en, desc_id, obs_en, ana_en, imp_en, obs_id, ana_id, imp_id):
        """Return (obs_en, ana_en, imp_en, obs_id, ana_id, imp_id), parsing from desc when empty."""
        en_markers = ['Observation:', 'Analysis:', 'Implication:']
        id_markers = ['Observasi:', 'Analisis:', 'Implikasi:']
        if not obs_en or not ana_en or not imp_en:
            o, a, i = _extract_oai(desc_en, en_markers)
            obs_en = obs_en or o
            ana_en = ana_en or a
            imp_en = imp_en or i
        if not obs_id or not ana_id or not imp_id:
            o, a, i = _extract_oai(desc_id, id_markers)
            obs_id = obs_id or o
            ana_id = ana_id or a
            imp_id = imp_id or i
        return obs_en, ana_en, imp_en, obs_id, ana_id, imp_id

    def _add(type_, icon, title_en, desc_en, title_id, desc_id,
             obs_en='', ana_en='', imp_en='',
             obs_id='', ana_id='', imp_id=''):
        obs_en, ana_en, imp_en, obs_id, ana_id, imp_id = _parse_oai(
            desc_en, desc_id, obs_en, ana_en, imp_en, obs_id, ana_id, imp_id)
        entry_en = {
            'type': type_, 'icon': icon, 'title': title_en, 'desc': desc_en,
            'observation': obs_en,
            'analysis': ana_en,
            'implication': imp_en,
        }
        entry_id = {
            'type': type_, 'icon': icon, 'title': title_id, 'desc': desc_id,
            'observation': obs_id,
            'analysis': ana_id,
            'implication': imp_id,
        }
        insights_en.append(entry_en)
        insights_id.append(entry_id)

    # ── 1. DATA QUALITY (missing values) ─────────────────────────────────────
    total_missing = int(df.isna().sum().sum())
    miss_pct = _pct(total_missing, total_cells)

    if total_missing == 0:
        _add(
            'success', 'fa-check-circle',
            ' Excellent Data Quality — Zero Missing Values',
            'Observation: No missing values found in the entire dataset. '
            'Analysis: Complete data indicates robust data collection and minimal preprocessing is required. '
            'Implication: The dataset is immediately suitable for statistical analysis and machine learning without imputation or deletion steps, reducing the risk of bias introduced by missing data handling.',
            ' Kualitas Data Sangat Baik — Tidak Ada Missing Values',
            'Observasi: Tidak ditemukan missing values pada dataset. '
            'Analisis: Data yang lengkap menandakan proses pengumpulan data yang baik dan minim kebutuhan preprocessing. '
            'Implikasi: Dataset dapat langsung digunakan untuk analisis statistik dan pemodelan machine learning tanpa langkah imputasi atau penghapusan data.',
        )
    elif miss_pct < 5:
        _add(
            'warning', 'fa-exclamation-triangle',
            f' Minor Missing Values ({miss_pct}%)',
            f'Observation: {total_missing:,} empty cells found ({miss_pct}% of total cells). '
            f'Analysis: This level is relatively low and typically safe for most analytical methods. '
            f'Missing data at this rate is unlikely to introduce significant bias if handled properly. '
            f'Implication: Imputation (mean/median for numeric, mode for categorical) is recommended before predictive modeling to avoid loss of information.',
            f' Missing Values Kecil ({miss_pct}%)',
            f'Observasi: Terdapat {total_missing:,} sel kosong ({miss_pct}% dari total sel). '
            f'Analisis: Tingkat ini relatif rendah dan umumnya aman untuk sebagian besar metode analisis. '
            f'Data hilang pada tingkat ini tidak mungkin menimbulkan bias signifikan jika ditangani dengan tepat. '
            f'Implikasi: Imputasi (mean/median untuk numerik, modus untuk kategorikal) disarankan sebelum pemodelan prediktif untuk menghindari kehilangan informasi.',
        )
    else:
        _add(
            'danger', 'fa-times-circle',
            f' High Missing Rate ({miss_pct}%)',
            f'Observation: Dataset has {total_missing:,} missing values ({miss_pct}% of total cells). '
            f'Analysis: This is a significant proportion that can compromise statistical power and introduce bias. '
            f'Analysis using listwise deletion would discard a substantial portion of data. '
            f'Implication: Consider aggressive handling strategies — model-based imputation (MICE, KNN), '
            f'column removal if >50% missing per column, or using algorithms inherently robust to missing data (e.g., XGBoost). '
            f'A sensitivity analysis comparing results with and without imputation is strongly advised.',
            f' Tingkat Missing Tinggi ({miss_pct}%)',
            f'Observasi: Dataset memiliki {total_missing:,} missing values ({miss_pct}% dari total sel). '
            f'Analisis: Proporsi ini signifikan dan dapat mengompromikan kekuatan statistik serta menimbulkan bias. '
            f'Penghapusan data secara listwise akan membuang sebagian besar data. '
            f'Implikasi: Pertimbangkan strategi penanganan agresif — imputasi berbasis model (MICE, KNN), '
            f'penghapusan kolom jika >50% missing per kolom, atau gunakan algoritma yang robust terhadap missing data (misal: XGBoost). '
            f'Analisis sensitivitas sangat disarankan untuk membandingkan hasil dengan dan tanpa imputasi.',
        )

    # ── 2. DATASET SIZE & STRUCTURE ──────────────────────────────────────────
    if total_rows >= 100_000:
        size_ana_en = 'Large sample size provides high statistical power and reliable parameter estimates.'
        size_ana_id = 'Ukuran sampel besar memberikan kekuatan statistik tinggi dan estimasi parameter yang andal.'
        size_imp_en = 'Consider strategic sampling or distributed computing for computationally intensive models. PCA or feature selection may be warranted to reduce dimensionality.'
        size_imp_id = 'Pertimbangkan sampling strategis atau distributed computing untuk model yang komputasinya intensif. PCA atau seleksi fitur mungkin diperlukan untuk mereduksi dimensi.'
    elif total_rows >= 10_000:
        size_ana_en = 'Large sample size generally sufficient for robust statistical inference and machine learning.'
        size_ana_id = 'Ukuran sampel besar umumnya cukup untuk inferensi statistik dan machine learning yang robust.'
        size_imp_en = 'Well-suited for complex models including neural networks and ensemble methods. Train-test-validation splits will retain sufficient observations per fold.'
        size_imp_id = 'Cocok untuk model kompleks termasuk neural networks dan ensemble methods. Pembagian train-test-validation akan menyisakan cukup observasi per fold.'
    elif total_rows >= 1_000:
        size_ana_en = 'Sample size is sufficiently representative for most standard statistical analyses.'
        size_ana_id = 'Ukuran sampel cukup representatif untuk sebagian besar analisis statistik standar.'
        size_imp_en = 'Suitable for regression, classification, and clustering. Cross-validation with 5-10 folds remains feasible. Be cautious with deep learning approaches which typically require >10K samples.'
        size_imp_id = 'Cocok untuk regresi, klasifikasi, dan clustering. Cross-validation dengan 5-10 fold tetap layak. Berhati-hati dengan deep learning yang biasanya membutuhkan >10K sampel.'
    elif total_rows >= 100:
        size_ana_en = 'Medium-sized dataset. Standard errors may be wider, affecting confidence interval precision.'
        size_ana_id = 'Dataset berukuran sedang. Standard error mungkin lebih lebar, memengaruhi presisi interval kepercayaan.'
        size_imp_en = 'Results should be validated with bootstrap resampling. Consider regularized models (Ridge, Lasso) to prevent overfitting. Avoid overly complex models with many parameters.'
        size_imp_id = 'Hasil harus divalidasi dengan bootstrap resampling. Pertimbangkan model regularized (Ridge, Lasso) untuk mencegah overfitting. Hindari model yang terlalu kompleks dengan banyak parameter.'
    else:
        size_ana_en = 'Small sample size. Statistical estimates may have large variance and low replicability.'
        size_ana_id = 'Ukuran sampel kecil. Estimasi statistik mungkin memiliki varians besar dan replikabilitas rendah.'
        size_imp_en = 'Non-parametric methods (Spearman, Mann-Whitney) are preferred. '
        'Any findings should be treated as preliminary and validated on larger samples before generalization. '
        'Bayesian approaches can incorporate prior information to stabilize estimates.'
        size_imp_id = 'Metode non-parametrik (Spearman, Mann-Whitney) lebih disarankan. '
        'Temuan harus diperlakukan sebagai preliminary dan divalidasi pada sampel yang lebih besar sebelum generalisasi. '
        'Pendekatan Bayesian dapat menginkorporasi informasi prior untuk menstabilkan estimasi.'

    _add(
        'info', 'fa-database',
        f' Dataset: {total_rows:,} Rows × {len(df.columns)} Columns',
        f'Observation: The dataset contains {total_rows:,} rows and {len(df.columns)} columns '
        f'({len(num_cols)} numeric, {len(cat_cols)} categorical). '
        f'Analysis: {size_ana_en} '
        f'Implication: {size_imp_en}',
        f' Dataset: {total_rows:,} Baris × {len(df.columns)} Kolom',
        f'Observasi: Dataset terdiri dari {total_rows:,} baris dan {len(df.columns)} kolom '
        f'({len(num_cols)} numerik, {len(cat_cols)} kategorikal). '
        f'Analisis: {size_ana_id} '
        f'Implikasi: {size_imp_id}',
        obs_en=f'The dataset has {total_rows:,} rows and {len(df.columns)} columns ({len(num_cols)} numeric, {len(cat_cols)} categorical).',
        ana_en=size_ana_en,
        imp_en=size_imp_en,
        obs_id=f'Dataset memiliki {total_rows:,} baris dan {len(df.columns)} kolom ({len(num_cols)} numerik, {len(cat_cols)} kategorikal).',
        ana_id=size_ana_id,
        imp_id=size_imp_id,
    )

    # ── 3. HIGHEST AVERAGE VARIABLE ──────────────────────────────────────────
    if num_cols:
        means = {}
        for col in num_cols:
            try:
                s = sanitize_series(df[col] if col in df.columns else pd.Series(dtype=float), col)
                if not s.empty:
                    means[col] = float(s.mean())
            except Exception:
                pass
        if means:
            top_mean_col = max(means, key=means.get)
            top_mean_val = round(means[top_mean_col], 2)
            s_top = sanitize_series(df[top_mean_col], top_mean_col)
            median_v = round(float(s_top.median()), 2) if not s_top.empty else 'N/A'
            std_v    = round(float(s_top.std()), 2) if len(s_top) >= 2 else 'N/A'

            cv = round(std_v / abs(top_mean_val) * 100, 1) if top_mean_val != 0 else 0
            spread_note_en = 'wide dispersion' if cv > 30 else 'moderate dispersion' if cv > 15 else 'low dispersion'
            spread_note_id = 'sebaran lebar' if cv > 30 else 'sebaran moderat' if cv > 15 else 'sebaran rendah'

            _add(
                'primary', 'fa-arrow-up',
                f' Highest Average Value: {top_mean_col}',
                f'Observation: Column {top_mean_col} has the highest mean value of {top_mean_val:,} '
                f'(median={median_v}, std={std_v}, CV={cv}%). '
                f'Analysis: The coefficient of variation (CV={cv}%) indicates {spread_note_en} relative to the mean. '
                f'The gap between mean and median suggests {"potential outlier influence" if abs(top_mean_val - median_v) / max(abs(top_mean_val), 0.001) > 0.1 else "a fairly symmetric distribution"}. '
                f'Implication: This variable will dominate any distance-based model (KNN, SVM, clustering) '
                f'unless features are standardized. Consider Min-Max scaling or Z-score normalization '
                f'before feeding into models sensitive to magnitude differences.',
                f' Nilai Rata-rata Tertinggi: {top_mean_col}',
                f'Observasi: Kolom {top_mean_col} memiliki rata-rata tertinggi sebesar {top_mean_val:,} '
                f'(median={median_v}, std={std_v}, CV={cv}%). '
                f'Analisis: Koefisien variasi (CV={cv}%) mengindikasikan {spread_note_id} relatif terhadap mean. '
                f'Kesenjangan mean dan median mengindikasikan {"potensi pengaruh outlier" if abs(top_mean_val - median_v) / max(abs(top_mean_val), 0.001) > 0.1 else "distribusi yang cukup simetris"}. '
                f'Implikasi: Variabel ini akan mendominasi model berbasis jarak (KNN, SVM, clustering) '
                f'kecuali fitur distandarisasi. Pertimbangkan Min-Max scaling atau Z-score normalization '
                f'sebelum digunakan pada model yang sensitif terhadap perbedaan magnitudo.',
            )

    # ── 4. MOST MISSING VALUES VARIABLE ──────────────────────────────────────
    miss_per_col = df.isna().sum()
    if miss_per_col.max() > 0:
        worst_col   = miss_per_col.idxmax()
        worst_count = int(miss_per_col.max())
        worst_pct   = _pct(worst_count, total_rows)

        rec_imp_en = (
            f'Implication: If {worst_pct}% > 50%, column removal is strongly advised '
            f'as imputation would introduce substantial artificial variance. '
            f'If ≤ 50%, model-based imputation (MICE, Iterative Imputer) preserves '
            f'distributional properties better than mean imputation.'
        ) if worst_pct > 50 else (
            f'Implication: Imputation is viable for this column. Mean imputation is '
            f'simple but may distort variance; median imputation is more robust to outliers; '
            f'KNN imputation preserves local data structure. For tree-based models, '
            f'missing values can be treated as a separate category (NaN) without imputation.'
        )
        rec_imp_id = (
            f'Implikasi: Jika {worst_pct}% > 50%, penghapusan kolom sangat disarankan '
            f'karena imputasi akan memasukkan varians artifisial yang substansial. '
            f'Jika ≤ 50%, imputasi berbasis model (MICE, Iterative Imputer) lebih '
            f'baik dalam mempertahankan properti distribusi dibanding imputasi mean.'
        ) if worst_pct > 50 else (
            f'Implikasi: Imputasi layak untuk kolom ini. Imputasi mean sederhana namun '
            f'dapat mendistorsi varians; imputasi median lebih robust terhadap outlier; '
            f'imputasi KNN mempertahankan struktur data lokal. Untuk model tree-based, '
            f'missing values dapat diperlakukan sebagai kategori terpisah tanpa imputasi.'
        )

        _add(
            'danger', 'fa-exclamation',
            f' Most Missing Values: {worst_col}',
            f'Observation: Column {worst_col} has the most missing values: {worst_count:,} rows ({worst_pct}%). '
            f'Analysis: {"Majority" if worst_pct > 50 else "Less than half"} of observations in this column are incomplete. '
            f'If this variable is a key predictor, missing data handling strategy critically affects model validity. '
            f'{rec_imp_en}',
            f' Missing Values Terbanyak: {worst_col}',
            f'Observasi: Kolom {worst_col} memiliki missing values terbanyak: {worst_count:,} baris ({worst_pct}%). '
            f'Analisis: {"Mayoritas" if worst_pct > 50 else "Kurang dari setengah"} observasi pada kolom ini tidak lengkap. '
            f'Jika variabel ini merupakan prediktor kunci, strategi penanganan missing data sangat memengaruhi validitas model. '
            f'{rec_imp_id}',
        )

    # ── 5. MOST OUTLIERS VARIABLE ─────────────────────────────────────────────
    if num_cols:
        outlier_counts = {col: _outlier_count(df[col]) for col in num_cols}
        max_out_col = max(outlier_counts, key=outlier_counts.get)
        max_out_val = outlier_counts[max_out_col]
        max_out_pct = _pct(max_out_val, total_rows)

        if max_out_val > 0:
            model_risk_en = (
                f'Implication: Outliers at this rate ({max_out_pct}%) can significantly affect models '
                f'sensitive to extreme values — linear regression (OLS), PCA, and k-means clustering. '
                f'Tree-based models (Random Forest, Gradient Boosting) are more robust to outliers. '
                f'Consider winsorization (capping at 1st/99th percentile), log transformation, '
                f'or use Huber/Tukey loss functions in robust regression.'
            ) if max_out_pct > 5 else (
                f'Implication: Outlier proportion is low ({max_out_pct}%) and unlikely to significantly '
                f'affect most models. However, for linear models, even a few extreme points can '
                f'disproportionately influence parameter estimates via leverage effects. '
                f'Consider robust standard errors or quantile regression as a sensitivity check.'
            )

            _add(
                'warning', 'fa-dot-circle',
                f' Most Outliers: {max_out_col}',
                f'Observation: Column {max_out_col} has the most outliers: '
                f'{max_out_val:,} data points ({max_out_pct}%) using IQR method (±1.5×IQR). '
                f'Analysis: Outliers may represent data entry errors, genuine extreme phenomena, '
                f'or distributional heavy tails. The IQR method assumes approximately symmetric distributions; '
                f'highly skewed data may produce false positive outlier detections. '
                f'Validate by domain context before removal. {model_risk_en}',
                f' Outlier Terbanyak: {max_out_col}',
                f'Observasi: Kolom {max_out_col} memiliki outlier terbanyak: '
                f'{max_out_val:,} titik data ({max_out_pct}%) menggunakan metode IQR (±1.5×IQR). '
                f'Analisis: Outlier dapat merepresentasikan error entri data, fenomena ekstrem genuin, '
                f'atau ekor distribusi yang berat. Metode IQR mengasumsikan distribusi yang kurang lebih simetris; '
                f'data highly skewed dapat menghasilkan deteksi outlier positif palsu. '
                f'Validasi berdasarkan konteks domain sebelum penghapusan. '
                f'{"Implikasi: Outlier pada tingkat ini dapat memengaruhi model sensitif terhadap nilai ekstrem — regresi linier (OLS), PCA, dan k-means clustering. Model tree-based lebih robust. Pertimbangkan winsorization atau transformasi log." if max_out_pct > 5 else "Implikasi: Proporsi outlier rendah dan tidak mungkin memengaruhi sebagian besar model. Namun untuk model linier, bahkan beberapa titik ekstrem dapat memengaruhi estimasi parameter secara tidak proporsional melalui efek leverage."}',
            )
        else:
            _add(
                'success', 'fa-bullseye',
                ' No Outliers Detected',
                'Observation: No outliers detected in any numeric column using the IQR method. '
                'Analysis: Data is distributed within reasonable bounds without extreme perturbations. '
                'Implication: Models sensitive to extreme values (OLS regression, PCA, k-means) '
                'can be applied without outlier-specific preprocessing. However, also check for '
                'distributional normality as absence of outliers does not guarantee normality.',
                ' Tidak Ada Outlier Terdeteksi',
                'Observasi: Tidak ditemukan outlier pada seluruh kolom numerik menggunakan metode IQR. '
                'Analisis: Data terdistribusi dalam batas wajar tanpa perturbasi ekstrem. '
                'Implikasi: Model yang sensitif terhadap nilai ekstrem (regresi OLS, PCA, k-means) '
                'dapat diterapkan tanpa preprocessing khusus outlier. Namun, periksa juga normalitas '
                'distribusi karena ketiadaan outlier tidak menjamin normalitas.',
            )

    # ── 6. HIGHEST STD DEVIATION VARIABLE ────────────────────────────────────
    if num_cols:
        stds = {}
        for col in num_cols:
            try:
                s = sanitize_series(df[col] if col in df.columns else pd.Series(dtype=float), col)
                if not s.empty and len(s) >= 2:
                    stds[col] = float(s.std())
            except Exception:
                pass
        if stds:
            top_std_col = max(stds, key=stds.get)
            top_std_val = round(stds[top_std_col], 4)
            s_top = sanitize_series(df[top_std_col], top_std_col)
            mean_top = float(s_top.mean()) if not s_top.empty else 0
            cv = round(top_std_val / mean_top * 100, 1) if mean_top != 0 else 0

            var_en = 'very high' if cv > 30 else ('high' if cv > 15 else 'moderate')
            var_id = 'sangat tinggi' if cv > 30 else ('tinggi' if cv > 15 else 'wajar')

            _add(
                'orange', 'fa-ruler-horizontal',
                f' Highest Std Deviation: {top_std_col}',
                f'Observation: Column {top_std_col} has the largest spread: std={top_std_val:,} (CV={cv}%). '
                f'Analysis: A CV above 30% indicates {var_en} variability, meaning values commonly deviate '
                f'by a large proportion from the mean. This could indicate a wide operational range, '
                f'seasonal fluctuations, or the presence of distinct sub-populations within the data. '
                f'Implication: High-variance variables tend to dominate distance-based models and '
                f'dimensionality reduction. Standardization is critical before PCA or clustering. '
                f'For regression, consider heteroskedasticity-robust standard errors or variance-stabilizing '
                f'transformations (log, Box-Cox) if this variable is the target.',
                f' Standar Deviasi Terbesar: {top_std_col}',
                f'Observasi: Kolom {top_std_col} memiliki sebaran terluas: std={top_std_val:,} (CV={cv}%). '
                f'Analisis: CV di atas 30% mengindikasikan variabilitas {var_id}, artinya nilai-nilai '
                f'umumnya menyimpang dalam proporsi besar dari mean. Ini dapat mengindikasikan rentang '
                f'operasional lebar, fluktuasi musiman, atau adanya sub-populasi berbeda dalam data. '
                f'Implikasi: Variabel dengan varians tinggi cenderung mendominasi model berbasis jarak dan '
                f'reduksi dimensi. Standardisasi sangat penting sebelum PCA atau clustering. '
                f'Untuk regresi, pertimbangkan standard error robust terhadap heteroskedastisitas atau '
                f'transformasi penstabil varians (log, Box-Cox) jika variabel ini adalah target.',
            )

    # ── 7. STRONGEST CORRELATION + MULTICOLLINEARITY ────────────────────────
    if len(num_cols) > 1:
        try:
            valid_cols, corr_df = safe_corr_matrix(df, num_cols)
            if corr_df is not None and len(valid_cols) >= 2:
                np.fill_diagonal(corr_df.values, np.nan)
                abs_corr = corr_df.abs()
                flat     = abs_corr.values.flatten()
                flat_nan = flat[~np.isnan(flat)]
                if len(flat_nan) > 0:
                    max_idx  = np.unravel_index(np.nanargmax(abs_corr.values), abs_corr.shape)
                    col_a, col_b = valid_cols[max_idx[0]], valid_cols[max_idx[1]]
                    r_val = round(float(corr_df.iloc[max_idx[0], max_idx[1]]), 3)
                    direction_en = 'positive' if r_val > 0 else 'negative'
                    direction_id = 'positif' if r_val > 0 else 'negatif'
                    r2 = round(r_val**2, 3)

                    if abs(r_val) > 0.8:
                        strength_en, strength_id = 'Very Strong', 'Sangat Kuat'
                        mc_risk_en = f'CRITICAL: r={r_val} (R²={r2}) indicates these two variables share {r2*100:.1f}% variance. '
                        f'If both are included as predictors in linear regression, multicollinearity '
                        f'will inflate coefficient standard errors, making it impossible to isolate '
                        f'their individual effects. VIF (Variance Inflation Factor) will exceed 5. '
                        f'Recommendation: drop one variable, use PCA, or apply Ridge regression.'
                        mc_risk_id = f'KRITIS: r={r_val} (R²={r2}) mengindikasikan kedua variabel berbagi {r2*100:.1f}% varians. '
                        f'Jika keduanya dimasukkan sebagai prediktor dalam regresi linier, multikolinearitas '
                        f'akan menginflasi standard error koefisien, sehingga efek individual tidak dapat diisolasi. '
                        f'VIF (Variance Inflation Factor) akan melampaui 5. '
                        f'Rekomendasi: buang satu variabel, gunakan PCA, atau terapkan Ridge regression.'
                    elif abs(r_val) > 0.6:
                        strength_en, strength_id = 'Strong', 'Kuat'
                        mc_risk_en = f'MODERATE RISK: r={r_val} indicates meaningful overlap. '
                        f'Monitor VIF — if either variable is a derived/composite of the other, consider removal. '
                        f'Partial correlation analysis can help isolate unique variance contributions.'
                        mc_risk_id = f'RISIKO MODERAT: r={r_val} mengindikasikan tumpang tindih berarti. '
                        f'Monitor VIF — jika salah satu variabel merupakan turunan/komposit dari yang lain, '
                        f'pertimbangkan penghapusan. Analisis korelasi parsial dapat membantu mengisolasi '
                        f'kontribusi varians unik.'
                    elif abs(r_val) > 0.4:
                        strength_en, strength_id = 'Moderate', 'Sedang'
                        mc_risk_en = f'LOW RISK: Moderate correlation unlikely to cause multicollinearity issues. '
                        f'Both variables can generally be included together in modeling.'
                        mc_risk_id = f'RISIKO RENDAH: Korelasi moderat tidak mungkin menyebabkan masalah multikolinearitas. '
                        f'Kedua variabel umumnya dapat dimasukkan bersama dalam pemodelan.'
                    else:
                        strength_en, strength_id = 'Weak', 'Lemah'
                        mc_risk_en = f'NEGLIGIBLE: Correlation is too weak to cause multicollinearity. '
                        f'Both variables contribute largely independent information.'
                        mc_risk_id = f'DIABAIKAN: Korelasi terlalu lemah untuk menyebabkan multikolinearitas. '
                        f'Kedua variabel memberikan informasi yang sebagian besar independen.'

                    desc_en = (
                        f'Observation: Strongest correlation found between {col_a} and {col_b} '
                        f'(r={r_val}, {direction_en}, {strength_en}). R²={r2} — '
                        f'they share {r2*100:.1f}% of variance. '
                        f'Analysis: This {"confirms" if r_val > 0 else "inverts"} the expected direction of relationship. '
                        f'A linear relationship of this magnitude is unlikely due to chance alone. '
                        f'{mc_risk_en}'
                    )
                    desc_id = (
                        f'Observasi: Korelasi terkuat ditemukan antara {col_a} dan {col_b} '
                        f'(r={r_val}, {direction_id}, {strength_id}). R²={r2} — '
                        f'keduanya berbagi {r2*100:.1f}% varians. '
                        f'Analisis: Ini {"mengonfirmasi" if r_val > 0 else "membalikkan"} arah hubungan yang diharapkan. '
                        f'Hubungan linier dengan magnitudo ini tidak mungkin terjadi karena kebetulan semata. '
                        f'{mc_risk_id}'
                    )

                    _add('primary', 'fa-link',
                         f' Strongest Correlation: {col_a} ↔ {col_b} (r={r_val})',
                         desc_en,
                         f' Korelasi Terkuat: {col_a} ↔ {col_b} (r={r_val})',
                         desc_id)

                # ── Multi-collinearity warnings (all pairs > 0.7) ──────────
                mc_list = _multicollinearity_warning(corr_df, valid_cols, threshold=0.7)
                if len(mc_list) >= 2:
                    pairs_str_en = '; '.join([f'{p["pair"][0]}↔{p["pair"][1]} (r={p["r"]})' for p in mc_list])
                    pairs_str_id = '; '.join([f'{p["pair"][0]}↔{p["pair"][1]} (r={p["r"]})' for p in mc_list])

                    _add(
                        'warning', 'fa-exclamation-triangle',
                        f' Multicollinearity Alert: {len(mc_list)} High-Correlation Pair(s)',
                        f'Observation: {len(mc_list)} variable pair(s) exceed |r|>=0.7: {pairs_str_en}. '
                        f'Analysis: Including highly correlated predictors simultaneously inflates coefficient '
                        f'variance, reduces statistical significance, and makes interpretation unreliable. '
                        f'Implication: Apply VIF-based feature selection (remove variables with VIF>10), '
                        f'use Ridge/Lasso regression which shrinks correlated coefficients, or '
                        f'apply PCA to orthogonalize predictors before regression-based modeling.',
                        f' Peringatan Multikolinearitas: {len(mc_list)} Pasangan Korelasi Tinggi',
                        f'Observasi: {len(mc_list)} pasangan variabel melampaui |r|>=0.7: {pairs_str_id}. '
                        f'Analisis: Menyertakan prediktor yang berkorelasi tinggi secara simultan menginflasi '
                        f'varians koefisien, mengurangi signifikansi statistik, dan membuat interpretasi tidak andal. '
                        f'Implikasi: Terapkan seleksi fitur berbasis VIF (hapus variabel dengan VIF>10), '
                        f'gunakan regresi Ridge/Lasso yang menyusutkan koefisien berkorelasi, atau '
                        f'terapkan PCA untuk mengortogonalisasi prediktor sebelum pemodelan berbasis regresi.',
                    )
        except Exception:
            pass

    # ── 8. NORMALITY + SKEWNESS + MODEL IMPACT ─────────────────────────────
    if num_cols:
        normal_cols     = []
        not_normal_cols = []
        for col in num_cols:
            result = _normality(df[col])
            if result == 'Normal':
                normal_cols.append(col)
            elif result == 'Not Normal':
                not_normal_cols.append(col)

        if normal_cols or not_normal_cols:
            total_tested = len(normal_cols) + len(not_normal_cols)
            normal_pct   = _pct(len(normal_cols), total_tested)
            nn_list = ', '.join(not_normal_cols[:3]) + (f' (+{len(not_normal_cols)-3} more)' if len(not_normal_cols) > 3 else '')
            nn_list_id = ', '.join(not_normal_cols[:3]) + (f' (+{len(not_normal_cols)-3} lainnya)' if len(not_normal_cols) > 3 else '')
            n_list  = ', '.join(normal_cols[:3])     + (f' (+{len(normal_cols)-3} more)'     if len(normal_cols) > 3 else '')
            n_list_id = ', '.join(normal_cols[:3])   + (f' (+{len(normal_cols)-3} lainnya)'  if len(normal_cols) > 3 else '')

            obs_en = f'{len(normal_cols)}/{total_tested} columns are normally distributed (Shapiro-Wilk, α=0.05).'
            obs_id = f'{len(normal_cols)}/{total_tested} kolom berdistribusi normal (Shapiro-Wilk, α=0.05).'
            if normal_cols:
                obs_en += f' Normal: {n_list}.'
                obs_id += f' Normal: {n_list_id}.'
            if not_normal_cols:
                obs_en += f' Non-normal: {nn_list}.'
                obs_id += f' Tidak normal: {nn_list_id}.'

            if not_normal_cols:
                ana_en = (
                    f'Non-normal columns ({100 - normal_pct}%) violate the normality assumption required for '
                    f'parametric tests (t-test, ANOVA, Pearson correlation, OLS regression inference). '
                    f'Non-normality can inflate Type I or Type II errors depending on sample size and skew direction.'
                )
                ana_id = (
                    f'Kolom tidak normal ({100 - normal_pct}%) melanggar asumsi normalitas yang diperlukan untuk '
                    f'uji parametrik (t-test, ANOVA, korelasi Pearson, inferensi regresi OLS). '
                    f'Non-normalitas dapat menginflasi error Tipe I atau Tipe II tergantung ukuran sampel dan arah skew.'
                )
                imp_en = (
                    f'Use non-parametric alternatives (Spearman correlation, Mann-Whitney U, Kruskal-Wallis) '
                    f'or apply transformations (log, sqrt, Box-Cox, Yeo-Johnson) before parametric analysis. '
                    f'For regression, consider robust standard errors or bootstrap-based inference.'
                )
                imp_id = (
                    f'Gunakan alternatif non-parametrik (korelasi Spearman, Mann-Whitney U, Kruskal-Wallis) '
                    f'atau terapkan transformasi (log, sqrt, Box-Cox, Yeo-Johnson) sebelum analisis parametrik. '
                    f'Untuk regresi, pertimbangkan robust standard errors atau inferensi berbasis bootstrap.'
                )
            else:
                ana_en = 'All columns meet the normality assumption. Parametric methods can be applied safely.'
                ana_id = 'Semua kolom memenuhi asumsi normalitas. Metode parametrik dapat diterapkan dengan aman.'
                imp_en = 'Standard parametric methods (OLS, t-test, ANOVA, Pearson) are appropriate. No transformation needed.'
                imp_id = 'Metode parametrik standar (OLS, t-test, ANOVA, Pearson) sesuai. Tidak diperlukan transformasi.'

            _add(
                'info', 'fa-bell',
                f' Normality Test — {len(normal_cols)}/{total_tested} Columns Normal',
                f'Observation: {obs_en} Analysis: {ana_en} Implication: {imp_en}',
                f' Uji Normalitas — {len(normal_cols)}/{total_tested} Kolom Normal',
                f'Observasi: {obs_id} Analisis: {ana_id} Implikasi: {imp_id}',
                obs_en=obs_en, ana_en=ana_en, imp_en=imp_en,
                obs_id=obs_id, ana_id=ana_id, imp_id=imp_id,
            )

        # Skewness with model impact
        skewed = []
        for col in num_cols:
            try:
                s = sanitize_series(df[col] if col in df.columns else pd.Series(dtype=float), col)
                if not s.empty and s.nunique() >= 2:
                    skw = float(s.skew())
                    if abs(skw) > 1:
                        skewed.append((col, skw))
            except Exception:
                pass
        if skewed:
            pairs_display = [f'{col} (skew={round(skw, 2)})' for col, skw in skewed[:4]]
            top_skew = skewed[0][1]
            model_rec = _model_impact_from_skew(top_skew)

            _add(
                'warning', 'fa-chart-line',
                f' Skewed Distributions: {len(skewed)} Column(s)',
                f'Observation: {len(skewed)} column(s) have |skewness| > 1: {", ".join(pairs_display)}. '
                f'Analysis: Skewness shifts the mass of the distribution toward one tail. '
                f'This violates the normality assumption and can bias mean-based statistics. '
                f'For positively skewed data (right tail), the mean exceeds the median; '
                f'for negatively skewed, the mean is less than the median. '
                f'Implication: {model_rec}',
                f' Distribusi Miring: {len(skewed)} Kolom',
                f'Observasi: {len(skewed)} kolom memiliki |skewness| > 1: {", ".join(pairs_display)}. '
                f'Analisis: Skewness menggeser massa distribusi ke salah satu ekor. '
                f'Ini melanggar asumsi normalitas dan dapat membiaskan statistik berbasis mean. '
                f'Untuk data positif skewed (ekor kanan), mean melebihi median; '
                f'untuk negatif skewed, mean lebih kecil dari median. '
                f'Implikasi: {model_rec}',
            )

    # ── 9. CATEGORICAL DISTRIBUTION ──────────────────────────────────────────
    if cat_cols:
        col = cat_cols[0]
        vc  = df[col].value_counts()
        dom_pct = _pct(vc.iloc[0], total_rows) if not vc.empty else 0

        if dom_pct > 70:
            bt = 'danger'
            bl_en, bl_id = 'Very Imbalanced', 'Sangat Tidak Seimbang'
            ana_en = f'Category "{vc.index[0]}" dominates {dom_pct}% of observations. This extreme imbalance will cause classifiers to be biased toward the majority class.'
            ana_id = f'Kategori "{vc.index[0]}" mendominasi {dom_pct}% observasi. Ketidakseimbangan ekstrem ini akan menyebabkan pengklasifikasi bias ke kelas mayoritas.'
            imp_en = 'Use stratified sampling during train-test split. Apply SMOTE, ADASYN, or class weighting (e.g., sklearn\'s class_weight="balanced"). Evaluation should use precision-recall or F1-score rather than accuracy.'
            imp_id = 'Gunakan stratified sampling saat pembagian train-test. Terapkan SMOTE, ADASYN, atau pembobotan kelas. Evaluasi sebaiknya menggunakan precision-recall atau F1-score daripada akurasi.'
        elif dom_pct > 50:
            bt = 'warning'
            bl_en, bl_id = 'Slightly Imbalanced', 'Kurang Seimbang'
            ana_en = f'Category "{vc.index[0]}" is dominant ({dom_pct}%). Moderate imbalance may still bias standard classifiers.'
            ana_id = f'Kategori "{vc.index[0]}" cukup dominan ({dom_pct}%). Ketidakseimbangan moderat masih dapat membiaskan pengklasifikasi standar.'
            imp_en = 'Consider oversampling the minority class or using class weights. Monitor recall for the minority class in model evaluation.'
            imp_id = 'Pertimbangkan oversampling kelas minoritas atau pembobotan kelas. Pantau recall untuk kelas minoritas dalam evaluasi model.'
        else:
            bt = 'success'
            bl_en, bl_id = 'Balanced', 'Seimbang'
            ana_en = f'Category distribution is fairly balanced. Most frequent: "{vc.index[0]}" ({dom_pct}%).'
            ana_id = f'Distribusi kategori cukup seimbang. Terbanyak: "{vc.index[0]}" ({dom_pct}%).'
            imp_en = 'Standard classification models can be used without special imbalance handling. Accuracy is a valid evaluation metric for balanced data.'
            imp_id = 'Model klasifikasi standar dapat digunakan tanpa penanganan ketidakseimbangan khusus. Akurasi adalah metrik evaluasi yang valid untuk data seimbang.'

        _add(
            bt, 'fa-tags',
            f' Categorical Balance ({col}): {bl_en}',
            f'Observation: First categorical column "{col}" has {df[col].nunique()} unique categories. '
            f'Dominant category: "{vc.index[0]}" ({dom_pct}%). '
            f'Analysis: {ana_en} '
            f'Implication: {imp_en}',
            f' Keseimbangan Kategorik ({col}): {bl_id}',
            f'Observasi: Kolom kategorikal pertama "{col}" memiliki {df[col].nunique()} kategori unik. '
            f'Kategori dominan: "{vc.index[0]}" ({dom_pct}%). '
            f'Analisis: {ana_id} '
            f'Implikasi: {imp_id}',
        )

    # ── 10. TIME SERIES INSIGHTS ────────────────────────────────────────────
    if ts_insights:
        for ts_ins in ts_insights:
            insights_en.append(ts_ins)
            ts_ins_id = dict(ts_ins)
            insights_id.append(ts_ins_id)

    # ── 11. FURTHER ANALYSIS RECOMMENDATIONS ─────────────────────────────────
    recs_en = []
    recs_id = []
    if num_cols and cat_cols:
        recs_en.append('One-Way ANOVA / T-Test to compare means across categorical groups')
        recs_id.append('One-Way ANOVA / T-Test untuk membandingkan rata-rata antar grup kategorik')
    if len(num_cols) > 1:
        recs_en.append('Linear/Logistic Regression for prediction; Ridge/Lasso if multicollinearity is detected')
        recs_id.append('Regresi Linear/Logistik untuk prediksi; Ridge/Lasso jika multikolinearitas terdeteksi')
    if len(cat_cols) >= 2:
        recs_en.append("Chi-Square + Cramér's V for categorical variable association")
        recs_id.append("Chi-Square + Cramér's V untuk asosiasi antar variabel kategorik")
    if any(_normality(df[c]) == 'Not Normal' for c in num_cols):
        recs_en.append('Non-Parametric Tests (Mann-Whitney, Spearman) for non-normal columns')
        recs_id.append('Uji Non-Parametrik (Mann-Whitney, Spearman) untuk kolom tidak normal')
    if len(num_cols) >= 3:
        recs_en.append('Principal Component Analysis (PCA) or t-SNE/UMAP for dimensionality reduction and visualization')
        recs_id.append('Principal Component Analysis (PCA) atau t-SNE/UMAP untuk reduksi dimensi dan visualisasi')

    if recs_en:
        _add(
            'success', 'fa-rocket',
            ' Further Analysis Recommendations',
            f'Observation: Based on the dataset structure ({len(num_cols)} numeric, {len(cat_cols)} categorical). '
            f'Analysis: The combination of variable types and data quality indicators suggests these techniques. '
            f'Implication: ' + '; '.join(recs_en) + '.',
            ' Rekomendasi Analisis Lanjut',
            f'Observasi: Berdasarkan struktur dataset ({len(num_cols)} numerik, {len(cat_cols)} kategorikal). '
            f'Analisis: Kombinasi tipe variabel dan indikator kualitas data menyarankan teknik-teknik berikut. '
            f'Implikasi: ' + '; '.join(recs_id) + '.',
        )

    return {'en': insights_en, 'id': insights_id}
