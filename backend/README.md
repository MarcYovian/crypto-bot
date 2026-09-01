# 🚀 SMC CryptoBot Backend

Backend API dan Trading Engine untuk **Binance Futures Semi-Automated Trading Bot** berbasis **Smart Money Concepts (SMC)**. Dibangun menggunakan **Python 3.12**, **FastAPI**, **SQLAlchemy AsyncORM**, **CCXT**, dan **python-telegram-bot** dengan arsitektur **Clean Architecture (DDD-inspired)** yang ketat.

---

## 📑 Daftar Isi

- [Arsitektur Sistem](#-arsitektur-sistem)
- [Fitur Utama](#-fitur-utama)
- [Struktur Direktori](#-struktur-direktori)
- [Persyaratan Sistem](#-persyaratan-sistem)
- [Instalasi & Menjalankan Lokal (Native)](#-instalasi--menjalankan-lokal-native)
- [Menjalankan dengan Docker](#-menjalankan-dengan-docker)
- [Konfigurasi Lingkungan (.env)](#-konfigurasi-lingkungan-env)
- [Database Migration (Alembic)](#-database-migration-alembic)
- [Pengujian (Testing)](#-pengujian-testing)
- [Dokumentasi API](#-dokumentasi-api)
- [Keamanan & Best Practices](#-keamanan--best-practices)

---

## 🏛️ Arsitektur Sistem

Backend ini mengimplementasikan **Clean Architecture (Onion Architecture)** di mana setiap layer memiliki tanggung jawab yang terisolasi dengan aturan ketergantungan mengarah ke dalam (*Dependency Rule*):

```
                       ┌──────────────────────────────┐
                       │      Presentation Layer      │
                       │  • FastAPI REST API (14 Routers)
                       │  • WebSocket Manager         │
                       │  • Telegram Bot Controller   │
                       └──────────────┬───────────────┘
                                      │
                       ┌──────────────▼───────────────┐
                       │      Application Layer       │
                       │  • Use Cases (54 use cases)  │
                       │  • Domain Event Handlers     │
                       │  • Command & Query DTOs      │
                       └──────────────┬───────────────┘
                                      │
                       ┌──────────────▼───────────────┐
                       │         Domain Layer         │
                       │  • Aggregates (Trade, Order) │
                       │  • Value Objects & Entities  │
                       │  • Domain Services & Rules   │
                       │  • Abstract Repository Ports │
                       └──────────────▲───────────────┘
                                      │
                       ┌──────────────┴───────────────┐
                       │     Infrastructure Layer     │
                       │  • Persistence (SQLAlchemy)  │
                       │  • Binance CCXT / CCXTPro    │
                       │  • Telegram Gateway          │
                       │  • APScheduler Background Job│
                       │  • Native DI Container       │
                       └──────────────────────────────┘
```

1. **Domain Layer (`src/domain/`)**: Inti logika bisnis murni (*Pure Python* tanpa dependensi eksternal). Berisi `TradeAggregate`, `TradeStateMachine`, `RiskCalculatorDomainService`, `SignalParserDomainService`, dan interface kontrak repository.
2. **Application Layer (`src/application/`)**: Orkestrator alur kerja aplikasi (54 *Use Cases*) seperti `ExecuteSignalUseCase`, `HandleOrderFillUseCase`, `SyncPositionsUseCase`, dll.
3. **Infrastructure Layer (`src/infrastructure/`)**: Implementasi detail teknis, database PostgreSQL/SQLite via Async SQLAlchemy, integrasi Binance REST & WebSocket, integrasi Telegram bot, scheduler, dan *Dependency Injection container*.
4. **Presentation Layer (`src/presentation/`)**: Titik interaksi luar (14 Router FastAPI REST API, WebSocket stream endpoint, dan Telegram command/wizard listeners).

---

## ✨ Fitur Utama

- **Dual-Mode Trading Engine**: Mendukung mode simulasi (*Paper Trading*) dan eksekusi riil (*Live Trading*) di Binance Futures Testnet/Mainnet.
- **Bracket Order Management**: Otomatisasi penempatan limit/market entry, multi-target Take Profit (TP1, TP2, TP3), Stop Loss (SL), Break-Even Point (BEP), dan Trailing Stop.
- **SMC Signal Parsing & Tracing**: Ekstraksi parameter sinyal Telegram (Pair, Side, Entry Zone, SL, TPs) dengan alokasi `trace_id` unik (`sig-{uuid8}`) untuk pelacakan end-to-end.
- **Risk Calculator & Liquidation Guard**: Perhitungan ukuran posisi berbasis persentase risiko modal, batas risiko harian (*Daily Risk Budget*), penyesuaian leverage dinamis, dan estimasi harga likuidasi.
- **Enkripsi Kredensial at-Rest**: Kredensial API Key & Secret Key exchange disimpan terenkripsi secara simetris menggunakan algoritma **Fernet (AES-128-CBC)**.
- **Hot Credential Rotation**: Perubahan API key pada database langsung dimuat secara instan tanpa perlu restart server (*zero-downtime reconfiguration*).
- **Rate Limiting Middleware**: Perlindungan anti-DoS & flooding berbasis IP menggunakan *sliding-window algorithm* dengan response standar `HTTP 429 Too Many Requests`.
- **Automated APScheduler Jobs**:
  - *Daily Risk Snapshot* (Pencatatan modal awal & budget risiko tiap tengah malam WIB)
  - *Failsafe Position Sync* (Rekonsiliasi posisi terbuka database vs exchange tiap 15 menit)
  - *Cleanup Orphan Orders* (Pembatalan order limit gantung yang kadaluarsa)
  - *WebSocket Log Compression* (Kompresi log aktivitas websocket ke `.tar.gz`)
- **Real-Time WebSocket Streaming**: Streaming pembaruan status order, fill event, dan notifikasi trade ke dashboard frontend.

---

## 📁 Struktur Direktori

```text
backend/
├── config/
│   └── settings.py          # Konfigurasi Pydantic Settings & environment validator
├── src/
│   ├── domain/              # Pure Domain (Aggregates, Entities, Value Objects, Ports)
│   │   ├── aggregates/      # TradeAggregate, OrderAggregate, TradeStateMachine
│   │   ├── entities/        # Trade, ParsedSignalDTO, Risk DTOs
│   │   ├── events/          # Domain Events
│   │   ├── exceptions/      # Domain-specific Exceptions
│   │   ├── ports/           # Abstract Gateway & Repository Interfaces
│   │   ├── services/        # RiskCalculator, SignalParser, PrecisionFilter
│   │   └── value_objects/   # Price, Quantity, OrderSide, TradeStatus, dll.
│   ├── application/         # Use Cases & Event Handlers
│   │   ├── use_cases/       # 54 Use Cases terbagi dalam 14 domain area
│   │   └── event_handlers/  # Handler event notifikasi Telegram
│   ├── infrastructure/      # Concrete Adapters & Persistence
│   │   ├── container.py     # Native Dependency Injection Container
│   │   ├── bootstrap.py     # System startup initializer & credential warm-up
│   │   ├── gateways/        # Binance (CCXT) & Telegram Bot Adapters
│   │   ├── persistence/     # SQLAlchemy ORM Models, Repositories, & Migrations
│   │   └── scheduler/       # APScheduler Recurring Background Jobs
│   ├── presentation/        # Delivery Mechanisms
│   │   ├── api/             # FastAPI App Factory, Routers, Middleware, & Schemas
│   │   ├── telegram/        # Telegram Controller & Interactive Setup Wizard
│   │   └── websocket/       # WebSocket Connection & Broadcast Manager
│   └── utils/               # Helpers (Fernet Security, Async Cache, Logger)
├── tests/                   # Test Suite (474 Unit, Integration, & E2E Tests)
├── main.py                  # Application Entrypoint & Lifespan Hooks
├── alembic.ini              # Konfigurasi database migration
├── pytest.ini               # Konfigurasi test runner
├── requirements.txt         # Daftar dependensi Python
└── .env.example             # Template konfigurasi environment
```

---

## 💻 Persyaratan Sistem

- **Python**: Versi `3.12+`
- **Database**: PostgreSQL `14+` (Produksi) atau SQLite (Pengujian lokal)
- **Akun Binance**: Akun Binance Futures (Testnet / Live API Key)
- **Telegram Bot**: Token bot dari `@BotFather` dan ID Chat dari `@userinfobot`

---

## 🚀 Instalasi & Menjalankan Lokal (Native)

### 1. Clone & Masuk ke Direktori Backend

```bash
cd backend
```

### 2. Buat & Aktifkan Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instal Dependensi

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Setup Environment Variables

Salin template konfigurasi dan sesuaikan nilainya:

```bash
cp .env.example .env
```

### 5. Jalankan Database Migration

```bash
alembic upgrade head
```

### 6. Jalankan Server API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Aplikasi akan berjalan di `http://127.0.0.1:8000`.

---

## 🐳 Menjalankan dengan Docker

Proyek ini telah dikonfigurasi menggunakan Docker Compose untuk orchestrasi multi-service yang mudah.

### Skenario A: Menjalankan Seluruh Stack (Full System)

Untuk menjalankan seluruh service (**Database PostgreSQL + Backend Trading Bot + Frontend Dashboard + Nginx Gateway**):

```bash
# Dari root direktori proyek:
docker compose up -d --build
```

- **Gateway URL**: [http://localhost](http://localhost) (Port 80)
- **Frontend Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Backend API Direct**: [http://localhost:8002](http://localhost:8002) (Docs: [http://localhost:8002/docs](http://localhost:8002/docs))
- **PostgreSQL Database**: `localhost:5433`

### Skenario B: Menjalankan Hanya Backend & Database (Tanpa Frontend)

Jika Anda hanya ingin mengembangkan atau menjalankan backend engine dan database:

```bash
# Dari root direktori:
docker compose up -d postgres crypto-bot
```

### Skenario C: Menjalankan Standalone Backend Container

Jika Anda ingin menjalankan container image backend murni dan mengarahkannya ke database eksternal:

```bash
# 1. Masuk ke folder backend
cd backend

# 2. Build image
docker build -t crypto-bot-backend .

# 3. Jalankan container
docker run -d \
  --name crypto_bot_app \
  -p 8000:8000 \
  --env-file .env \
  crypto-bot-backend
```

### Perintah Berguna Docker:

```bash
# Melihat log real-time backend
docker compose logs -f crypto-bot

# Menjalankan migrasi database di dalam container
docker compose exec crypto-bot alembic upgrade head

# Menjalankan automated test suite di dalam container
docker compose exec crypto-bot pytest -n auto

# Masuk ke shell container backend
docker compose exec crypto-bot bash

# Menghentikan container
docker compose down
```

---

## ⚙️ Konfigurasi Lingkungan (.env)

| Variabel | Deskripsi | Default / Contoh |
|---|---|---|
| `ENVIRONMENT` | Mode lingkungan (`development`, `staging`, `production`) | `development` |
| `DATABASE_URL` | Koneksi database SQLAlchemy async | `postgresql+asyncpg://user:pass@localhost:5432/cryptobot_db` |
| `JWT_SECRET_KEY` | Kunci rahasia JWT & enkripsi Fernet (Wajib diisi kuat di production) | `dev-secret-jwt-key-...` |
| `DEFAULT_ADMIN_USERNAME`| Username akun admin bawaan sistem | `admin` |
| `DEFAULT_ADMIN_PASSWORD`| Password akun admin bawaan (Wajib diganti di production) | `AdminPassword123!` |
| `CORS_ORIGINS` | Daftar domain frontend yang diizinkan (Comma-separated) | `http://localhost:3000,http://127.0.0.1:3000` |
| `RATE_LIMIT_ENABLED` | Mengaktifkan middleware pembatas laju request | `true` |
| `RATE_LIMIT_PER_MINUTE`| Batas maksimal request per IP per menit | `120` |
| `TELEGRAM_BOT_TOKEN` | Token API bot Telegram dari BotFather | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | ID chat Telegram penerima alert | `123456789` |
| `DEFAULT_LEVERAGE` | Default leverage futures | `20` |
| `CONFIDENCE_THRESHOLD`| Ambang batas auto-execute sinyal (0.70 = 70%) | `0.70` |
| `LOG_LEVEL` | Level logging aplikasi (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

---

## 🗄️ Database Migration (Alembic)

Kelola skema database menggunakan Alembic:

```bash
# Membuat migration baru otomatis berdasarkan perubahan ORM model
alembic revision --autogenerate -m "deskripsi_perubahan"

# Menjalankan migrasi ke versi terbaru
alembic upgrade head

# Rollback migrasi 1 langkah ke belakang
alembic downgrade -1
```

---

## 🧪 Pengujian (Testing)

Backend dilengkapi dengan **474 automated test cases** yang mencakup pengujian unit, integrasi domain, repositori, API endpoint, dan skenario edge-case:

```bash
# Menjalankan seluruh test suite secara paralel
pytest -n auto

# Menjalankan test dengan laporan code coverage
pytest --cov=src --cov-report=term-missing

# Menjalankan grup pengujian spesifik
pytest tests/domain/           # Domain Layer (Aggregates, Value Objects, Events)
pytest tests/api/              # REST API & Middleware (Rate Limiter, Auth, CORS)
pytest tests/repository/       # SQLAlchemy Async Repositories
```

---

## 📖 Dokumentasi API

Saat backend berjalan, dokumentasi interaktif OpenAPI dapat diakses secara langsung:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🛡️ Keamanan & Best Practices

1. **Aturan Produksi Ketat**: Pengaturan `ENVIRONMENT=production` otomatis memvalidasi bahwa `JWT_SECRET_KEY` dan `DEFAULT_ADMIN_PASSWORD` bukan default development, serta melarang wildcard `*` pada `CORS_ORIGINS`.
2. **Kredensial Terenkripsi**: Jangan pernah mengekspos API secret exchange dalam bentuk teks terbuka. Kunci didekripsi hanya di memori saat melakukan warm-up gateway.
3. **Database Cascade & Invariant**: Relasi tabel `trades`, `orders`, `executions`, dan `events` dilindungi dengan *foreign key cascades* dan *CheckConstraints* database yang selaras dengan domain state machine.
