import json
import re

from backend.ai_client import call_ai, AIClientError


SYSTEM_PROMPT_TEMPLATE = """
Kamu adalah AI Data Analyst senior untuk aplikasi DS Generator (Kelompok 2 - ITSB).
Tugasmu: berikan interpretasi MENYELURUH dan ANALISIS MENDALAM terhadap dataset berikut.

Gunakan kerangka **O-A-I (Observation → Analysis → Implication)** untuk setiap temuan:
  - Observation:   Fakta statistik yang terlihat (sebutkan variabel, nilai numerik spesifik).
  - Analysis:      Mengapa hal itu terjadi? Hubungan antar variabel, kausalitas, atau faktor yang memengaruhi.
  - Implication:   Dampak terhadap tahap pemodelan selanjutnya. Apa yang harus dilakukan?

Output dalam format JSON valid (tanpa markdown code fence), dengan struktur:
{{
  "summary": "Ringkasan EKSEKUTIF (3-5 kalimat). Sebutkan jumlah baris, kolom, dan 2-3 temuan paling penting. Gunakan kerangka O-A-I implisit.",
  "key_findings": [
    "**Observation:** [Fakta dengan angka spesifik]. **Analysis:** [Interpretasi hubungan/kausal]. **Implication:** [Dampak pada model/keputusan].",
    "**Observation:** ... **Analysis:** ... **Implication:** ...",
    "**Observation:** ... **Analysis:** ... **Implication:** ..."
  ],
  "recommendations": [
    "**Rekomendasi 1:** Langkah konkret berdasarkan temuan. Contoh: Karena korelasi antara Hours_Studied dan Exam_Score sebesar 0.65, **Observation:** setiap kenaikan 1 jam belajar dikaitkan dengan kenaikan skor ujian. **Analysis:** Hubungan ini moderat, menunjukkan faktor lain juga berperan. **Implication:** Intervensi peningkatan jam belajar dapat direkomendasikan namun perlu dikombinasikan dengan faktor kualitas belajar.",
    "**Rekomendasi 2:** ...",
    "**Rekomendasi 3:** ..."
  ],
  "conclusion": "Kesimpulan akhir berisi: (1) apakah dataset layak dipakai, (2) risiko/keterbatasan utama dengan analisis O-A-I, (3) langkah selanjutnya."
}}

PANDUAN ANALISIS KETAT:
1. HARAM menggunakan kalimat deskriptif saja seperti 'Rata-rata adalah X' tanpa analisis dan implikasi.
2. WAJIB menggunakan struktur O-A-I untuk setiap temuan dan rekomendasi.
3. Setiap temuan HARUS menyebutkan nama variabel, nilai numerik, dan interpretasi.
4. Contoh BAIK: "**Observation:** Kolom Attendance memiliki rata-rata 82.5% dengan std 12.3. **Analysis:** Variasi kehadiran yang cukup lebar (CV=14.9%) menunjukkan perbedaan signifikan antar individu, kemungkinan dipengaruhi faktor eksternal seperti jarak tempuh atau jadwal kerja. **Implication:** Model prediktif perlu mempertimbangkan heterogenitas ini — stratified sampling atau mixed-effects models mungkin diperlukan."
5. Contoh BURUK: "Tingkat kehadiran bervariasi." (tanpa angka, tanpa analisis, tanpa implikasi).
6. Untuk korelasi: sebutkan r, R², dan apakah multikolinearitas menjadi risiko.
7. Untuk distribusi: sebutkan skewness dan dampaknya terhadap pemilihan model (parametrik vs non-parametrik).
8. RECOMMENDATIONS: Langkah konkret yang bisa DIAMBIL oleh pengguna data. Terkait langsung dengan temuan.
9. CONCLUSION: Ya/tidak layak pakai + risiko + langkah selanjutnya. Gunakan data sebagai pendukung argumen.

Gunakan bahasa sesuai parameter 'lang' (id = Bahasa Indonesia, en = English).
JAWAB HANYA DENGAN JSON valid, tanpa teks tambahan apapun.
"""


def build_dataset_context_text(ctx):
    parts = []

    di = ctx.get('dataset_info', {})
    parts.append(f"Dataset: {di.get('name', 'N/A')}")
    parts.append(f"Rows: {di.get('rows', 'N/A')}, Columns: {di.get('cols', 'N/A')}, Size: {di.get('size', 'N/A')}")

    metrics = ctx.get('metrics', {})
    parts.append(f"Total rows: {metrics.get('total_rows', 'N/A')}, Total cols: {metrics.get('total_columns', 'N/A')}")
    parts.append(f"Numeric cols: {metrics.get('numeric_columns', 'N/A')}, Categorical cols: {metrics.get('categorical_columns', 'N/A')}")
    parts.append(f"Missing values: {metrics.get('missing_values', 0)}, Duplicates: {metrics.get('duplicates', 0)}")

    num_stats = ctx.get('num_stats', [])
    if num_stats:
        parts.append("=== NUMERICAL STATS (ALL COLUMNS) ===")
        for stat in num_stats:
            col = stat.get('Column', 'N/A')
            parts.append(
                f"  [{col}] mean={stat.get('Mean', 'N/A')}, "
                f"median={stat.get('Median', 'N/A')}, "
                f"min={stat.get('Min', 'N/A')}, "
                f"max={stat.get('Max', 'N/A')}, "
                f"std={stat.get('Std Dev', 'N/A')}, "
                f"skew={stat.get('Skewness', 'N/A')}, "
                f"kurtosis={stat.get('Kurtosis', 'N/A')}, "
                f"missing={stat.get('Missing Count', 0)}, "
                f"normality={stat.get('Normality', 'N/A')}, "
                f"outliers={stat.get('Outliers', 0)}"
            )

    cat_stats = ctx.get('cat_stats', [])
    if cat_stats:
        parts.append("=== CATEGORICAL STATS (ALL COLUMNS) ===")
        for stat in cat_stats:
            col = stat.get('Column', 'N/A')
            parts.append(
                f"  [{col}] unique={stat.get('Unique', 'N/A')}, "
                f"mode={stat.get('Mode', 'N/A')}, "
                f"mode_pct={stat.get('Mode %', 'N/A')}, "
                f"missing={stat.get('Missing Count', 0)}"
            )

    advanced = ctx.get('advanced', {})
    if advanced:
        top_corr = advanced.get('top_corr_pairs', [])
        if top_corr:
            parts.append("=== TOP CORRELATIONS ===")
            for pair in top_corr:
                if len(pair) >= 3:
                    parts.append(f"  {pair[0]} ↔ {pair[1]}: r={pair[2]}")

        cat_assoc = advanced.get('cat_assoc', [])
        if cat_assoc:
            parts.append("=== CATEGORICAL ASSOCIATIONS (Cramér's V) ===")
            for assoc in cat_assoc[:5]:
                parts.append(
                    f"  {assoc.get('col_a')} × {assoc.get('col_b')}: "
                    f"V={assoc.get('cramers_v', 'N/A')} "
                    f"(p={assoc.get('p', 'N/A')}, {assoc.get('strength', '')})"
                )

        num_cat = advanced.get('num_cat', [])
        if num_cat:
            parts.append("=== NUMERICAL vs CATEGORICAL (ANOVA) ===")
            for item in num_cat[:4]:
                sig = "SIGNIFICANT" if item.get('significant') else "not significant"
                parts.append(
                    f"  {item.get('num')} × {item.get('cat')}: "
                    f"F={item.get('f_stat', 'N/A')}, "
                    f"p={item.get('p_anova', 'N/A')} ({sig})"
                )

    quality = ctx.get('quality_report', {})
    if isinstance(quality, dict):
        parts.append(
            f"Data quality: missing_pct={quality.get('missing_percentage', 'N/A')}%, "
            f"duplicate_rows={quality.get('duplicate_rows', 0)}"
        )

    insights = ctx.get('insights_en', [])
    if insights:
        parts.append("=== KEY INSIGHTS FROM SYSTEM ===")
        for ins in insights[:5]:
            parts.append(f"  - {ins.get('title', '')}: {ins.get('desc', '')}")

    context_text = '\n'.join(parts)

    if len(context_text) > 8000:
        context_text = context_text[:8000] + '\n[context truncated due to length]'

    return context_text


def generate_interpretation(ctx, lang, ai_settings):
    if not ai_settings or not ai_settings.get('api_key'):
        raise AIClientError('AI API key belum dikonfigurasi.')

    provider = ai_settings.get('provider', 'anthropic')
    api_key = ai_settings.get('api_key', '')
    model = ai_settings.get('model', '')

    context_text = build_dataset_context_text(ctx)
    user_prompt = f"Bahasa: {lang}\n\nDataset context:\n{context_text}"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.strip()

    raw = call_ai(provider, api_key, model, system_prompt, user_prompt)

    json_str = raw.strip()
    json_str = re.sub(r'^```(?:json)?\s*', '', json_str)
    json_str = re.sub(r'\s*```$', '', json_str)

    try:
        result = json.loads(json_str)
        expected_keys = {'summary', 'key_findings', 'recommendations', 'conclusion'}
        if not expected_keys.issubset(result.keys()):
            result = {
                'summary': raw,
                'key_findings': [],
                'recommendations': [],
                'conclusion': '',
            }
        if isinstance(result.get('key_findings'), list):
            result['key_findings'] = [str(f) for f in result['key_findings']]
        else:
            result['key_findings'] = []
        if isinstance(result.get('recommendations'), list):
            result['recommendations'] = [str(r) for r in result['recommendations']]
        else:
            result['recommendations'] = []
        result['summary'] = str(result.get('summary', ''))
        result['conclusion'] = str(result.get('conclusion', ''))
        return result
    except json.JSONDecodeError:
        return {
            'summary': raw,
            'key_findings': [],
            'recommendations': [],
            'conclusion': '',
        }
