# 📚 SMC CryptoBot Backend Documentation

Selamat datang di direktori dokumentasi resmi **SMC CryptoBot Backend**. Dokumen-dokumen di sini mencakup seluruh aspek arsitektur server, database, algoritma trading, dan kontrak API.

---

## 🗺️ Peta Navigasi Dokumentasi

### 1. [API & Integrasi Client](api/)
Dokumentasi interface HTTP REST dan WebSocket yang disediakan oleh backend:
* **[api/SPECIFICATION.md](api/SPECIFICATION.md)** — Spesifikasi rinci seluruh endpoint REST API (Auth, Bot, Trades, Signals, Analytics, Settings, Logs).
* **[api/openapi.yaml](api/openapi.yaml)** — Spesifikasi OpenAPI 3.0 standar (bisa diimpor ke Postman, Swagger UI, atau code generator).
* **[api/WEBSOCKET.md](api/WEBSOCKET.md)** — Spesifikasi event-driven streaming WebSocket real-time (`/api/v1/ws`).

### 2. [Database & Persistence](database/)
Panduan arsitektur basis data relasional PostgreSQL & SQLite:
* **[database/DATABASE_GUIDE.md](database/DATABASE_GUIDE.md)** — Panduan lengkap konfigurasi database, connection pooling, dan prosedur migrasi Alembic.
* **[database/SCHEMA.md](database/SCHEMA.md)** — Kamus data tabel, relasi foreign key, constraint, dan indexing.

### 3. [Trading Engine & SMC Logic](trading_engine/)
Logika algoritma bisnis trading dan manajemen risiko:
* **[trading_engine/SMC_LOGIC.md](trading_engine/SMC_LOGIC.md)** — Penjelasan aturan Smart Money Concepts (Order Block, FVG), kalkulator risiko, dan Circuit Breaker.
* **[trading_engine/materials/](trading_engine/materials/)** — Materi dan riset PDF mengenai analisa teknikal Binance Futures dan strategi pasar.

### 4. [Roadmap & Fitur Mendatang](future_v3/)
Rancangan arsitektur dan fungsionalitas untuk iterasi berikutnya:
* **[future_v3/](future_v3/)** — PRD, Business Rules, Architecture, dan Roadmap untuk SMC QuantEngine V3.

### 5. [Arsip Legacy](archive/)
Dokumentasi versi lawas untuk referensi historis:
* **[archive/v2_legacy/](archive/v2_legacy/)** — Dokumentasi bot Telegram V2 monolitik sebelumnya.

---

## 🔗 Tautan Eksternal Terkait
* **Frontend Repository:** [`crypto-bot-frontend`](https://github.com/MarcYovian/crypto-bot-frontend.git)
* **Local API Docs (Swagger):** `http://localhost:8000/docs` (saat backend berjalan)
* **Local ReDoc:** `http://localhost:8000/redoc`
