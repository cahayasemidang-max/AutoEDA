import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '.')
from backend.cleaning_engine import detect_data_status, reset_session

print('=== Test Quick Fix: Outlier Removal ===')

# Dataset dengan distribusi log-normal (sangat skewed, banyak outlier)
np.random.seed(42)
data = np.random.lognormal(mean=1.5, sigma=1.0, size=200)
df = pd.DataFrame({
    'value': data,
    'category': np.random.choice(['A', 'B', 'C'], 200),
})

status_before = detect_data_status(df)
print(f'Before: {len(df)} baris, status = {status_before}')

# Inisialisasi sesi dan jalankan quick_fix
sess = reset_session('test_session', df)
result = sess.quick_fix()

df_after = sess.df_current
status_after = detect_data_status(df_after)
print(f'After:  {len(df_after)} baris, status = {status_after}')
print(f'OK dari quick_fix: {result["ok"]}')
print(f'Label:  {result["label"]}')
print()

# Verifikasi tidak ada outlier tersisa
num_cols = df_after.select_dtypes(include='number').columns
all_clean = True
for col in num_cols:
    s = df_after[col].dropna()
    if len(s) < 4:
        continue
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        continue
    outliers = s[(s < q1 - 1.5*iqr) | (s > q3 + 1.5*iqr)]
    if len(outliers) > 0:
        print(f'MASIH ADA outlier di kolom [{col}]: {len(outliers)} nilai')
        all_clean = False

if all_clean:
    print('Semua kolom bebas outlier IQR setelah Quick Fix!')

print(f'Status akhir: {status_after}')
assert status_after == 'clean', f'GAGAL: status masih {status_after}'
print('TEST PASSED!')
