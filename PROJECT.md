# 🏛️ Crypto-Bot System & Backend Architecture Blueprint

Dokumen ini adalah referensi arsitektur teknis utama untuk sistem trading **SMC CryptoBot**, berfokus pada arsitektur server backend, orkestrasi kontainer Docker, dan kontrak integrasi dengan frontend dashboard.

---

## 1. Arsitektur Repositori (Decoupled Multirepo)

Sistem telah dipisahkan secara modular menjadi dua repositori independen:

1. **Backend Repository (Repo Ini):**
   * **Path Lokal:** `/home/rodex/Documents/cell/projects/crypto-bot`
   * **Remote Git:** `https://github.com/MarcYovian/crypto-bot.git`
   * **Tanggung Jawab:** Core trading engine, signal parsing, risk calculation, bracket order execution di Binance Futures, database persistence (PostgreSQL), background scheduler (APScheduler), Telegram bot gateway, REST API (FastAPI), dan streaming event WebSocket.
2. **Frontend Repository:**
   * **Path Lokal:** `/home/rodex/Documents/cell/projects/crypto-bot-frontend`
   * **Remote Git:** `https://github.com/MarcYovian/crypto-bot-frontend.git`
   * **Tanggung Jawab:** Single Page Application (SPA) dashboard interaktif berbasis React 18, Vite, TypeScript, Zustand, TanStack Query, dan TailwindCSS.

---

## 2. Arsitektur Backend (Clean Architecture / DDD)

Backend dibangun dengan prinsip *Dependency Inversion* ketat, di mana alur dependensi selalu mengarah ke dalam (*Inward Dependency Rule*):

```
┌─────────────────────────────────────────────────────────┐
│                   Presentation Layer                    │
│   • FastAPI REST API (14 Routers)                       │
│   • WebSocket Stream Manager (/api/v1/ws)               │
│   • Telegram Bot Wizard & Command Listeners             │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                    Application Layer                    │
│   • 54 Use Cases (Command & Query Orchestrators)        │
│   • Domain Event Handlers (Trade, Order, Risk events)   │
│   • Data Transfer Objects (DTOs)                        │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                      Domain Layer                       │
│   • TradeAggregate & Order Entity                       │
│   • TradeStateMachine (Finite State Machine)            │
│   • Domain Services: RiskCalculator, SignalParser       │
│   • Abstract Repository Ports (Interfaces)              │
└───────────────────────────▲─────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────┐
│                   Infrastructure Layer                  │
│   • Async SQLAlchemy (PostgreSQL / In-memory SQLite)    │
│   • Binance Exchange Gateway (CCXT & CCXTPro WebSocket) │
│   • Telegram Bot Gateway (python-telegram-bot)          │
│   • APScheduler Background Jobs & Maintenance           │
│   • Native Dependency Injection Container (DI)          │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Kontrak Interface & Komunikasi (API Contract)

### A. HTTP REST API
* **Base URL:** `/api/v1`
* **Dokumentasi OpenAPI:** [docs/api/openapi.yaml](docs/api/openapi.yaml) dan [docs/api/SPECIFICATION.md](docs/api/SPECIFICATION.md)
* **Healthcheck:** `GET /health` $\rightarrow$ `{"status": "ok", "service": "crypto-bot-api", "version": "2.0.0"}`
* **Autentikasi:** JWT Bearer Token (`Authorization: Bearer <token>`).

### B. WebSocket Real-Time Stream
* **Endpoint:** `/api/v1/ws?token=<JWT>` (atau fallback `/ws?token=<JWT>`)
* **Spesifikasi Lengkap:** [docs/api/WEBSOCKET.md](docs/api/WEBSOCKET.md)
* **Events Dispatched:** `TRADE_OPENED`, `ORDER_FILLED`, `TP_HIT`, `SL_HIT`, `TRADE_CLOSED`, `BOT_STATUS_CHANGED`, `CIRCUIT_BREAKER_TRIGGERED`.

---

## 4. Lingkungan Docker & Alokasi Port

### A. Mode Development (Lokal)
Masing-masing repository memiliki `docker-compose.yml` terisolasi:
* **Backend Dev (`docker-compose.yml`):**
  * Port `8000:8000` (FastAPI dengan auto-reload `--reload` dan auto-migration `alembic upgrade head`)
  * Port `5433:5432` (PostgreSQL 16 Alpine dengan persistent volume `postgres_data`)
* **Frontend Dev (`docker-compose.yml`):**
  * Port `3000:3000` (Vite dev server dengan live HMR via polling watch)
  * Otomatis melakukan reverse proxy permintaan `/api` ke backend di port `8000`.

### B. Mode Production (Server Homelab/VPS)
Orkestrasi production menggunakan file [docker-compose.prod.yml](docker-compose.prod.yml) di repo ini:
* **Nginx Gateway (`crypto_bot_gateway`):**
  * Port `8088:80` (atau `80:80` jika langsung)
  * Menyatukan routing:
    * `/api/`, `/health`, `/docs`, `/ws` $\rightarrow$ Container `crypto-bot:8000`
    * `/*` $\rightarrow$ Container `frontend:80`
  * Mencegah masalah CORS dan mengamankan akses internal container.

---

## 5. Tata Letak File Backend

```text
├── Dockerfile                  # Multi-stage production build (Python 3.12-slim)
├── alembic.ini                 # Konfigurasi database migration
├── config/                     # Settings & environment parser (Pydantic Settings)
├── docker-compose.prod.yml     # Orkestrasi production (Postgres + Backend + Frontend + Gateway)
├── docker-compose.yml          # Lingkungan development lokal (Postgres + Backend)
├── docker/nginx/nginx.conf     # Konfigurasi production reverse gateway
├── docs/                       # Dokumentasi terstruktur (api, database, trading_engine)
├── main.py                     # ASGI application entrypoint
├── mypy.ini                    # Konfigurasi static typechecker
├── pytest.ini                  # Konfigurasi testing suite
├── requirements.txt            # Dependensi Python
├── scripts/                    # Skrip operasional & testing
├── src/                        # Source code Clean Architecture (domain, app, infra, pres)
└── tests/                      # Suite pengujian otomatis (570+ test cases)
```
