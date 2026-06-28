# Menggunakan versi Python 3.9
FROM python:3.9-slim

# Menetapkan direktori kerja di dalam server nanti
WORKDIR /app

# Menyalin file daftar pustaka
COPY requirements.txt .

# Menginstal semua yang dibutuhkan
RUN pip install --no-cache-dir -r requirements.txt

# Menyalin seluruh file proyek Anda ke dalam container
COPY . .

# Mengekspos port 7860 agar bisa diakses
EXPOSE 7860

# Perintah untuk menjalankan aplikasi
CMD ["python", "app.py"]