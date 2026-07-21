# Gunakan image Python yang ringan
FROM python:3.10-slim

# Set timezone (opsional, tapi disarankan agar cron scheduler sinkron)
ENV TZ=Asia/Jakarta
RUN apt-get update && apt-get install -y tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# Set working directory di dalam container
WORKDIR /app

# Copy file requirements.txt ke dalam container
COPY requirements.txt .

# Install dependensi
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh source code ke dalam container
COPY . .

# Set PYTHONPATH agar import `backend` dapat ditemukan
ENV PYTHONPATH=/app

# Jalankan backend/main.py saat container dimulai
CMD ["python", "backend/main.py"]

