# Gunakan image Python 3.12 yang ringan
FROM python:3.12-slim

# Set timezone (disarankan agar cron scheduler sinkron dengan WIB)
ENV TZ=Asia/Jakarta
RUN apt-get update && apt-get install -y tzdata curl && \
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

# Set PYTHONPATH agar import `src` dan `config` dapat ditemukan
ENV PYTHONPATH=/app

# Expose port untuk Web Dashboard REST & WebSocket API
EXPOSE 8000

# Jalankan Uvicorn ASGI Server saat container dimulai
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
