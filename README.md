# 🤖 SMC CryptoBot – Semi-Automated Binance Futures Trading Platform

[![Architecture](https://img.shields.io/badge/Architecture-Clean%20Architecture%20%2B%20Service%20Repository-blue.svg)](docs/V3/ARCHITECTURE.md)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20SQLAlchemy%20Async-009688.svg)](backend/)
[![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript%20%2B%20TailwindCSS-61DAFB.svg)](frontend/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%2016-336791.svg)](docs/V3/DATABASE.md)
[![Tests](https://img.shields.io/badge/Backend%20Tests-346%20Passed%20(100%25)-success.svg)](backend/tests/)

Platform trading Binance Futures semi-otomatis berkinerja tinggi berbasis **Smart Money Concepts (SMC)** dan **Clean Architecture**. Sistem mengintegrasikan Telegram Signal Parser, Strict 2% Daily Risk Management, Real-Time Position Lifecycle State Machine, REST & WebSocket API, Central Nginx Gateway, serta Modern Web Dashboard UI.

---

## 🌟 Fitur Utama Sistem

### 1. 🧠 Core Trading Engine & Risk Management
* **Strict 2.0% Risk Guard**: Kalkulasi lot size dinamis *real-time* saat eksekusi agar risiko kerugian maksimal per trade tidak pernah melebihi 2.0% dari saldo terkunci harian (00:00 WIB).
* **Dynamic Leverage Downscaling**: Otomatis menyesuaikan leverage ke batas aman bracket notional Binance jika ukuran posisi melebihi tier exchange.
* **Dual Execution Mode**: Eksekusi instan `MARKET` jika harga pasar berada dekat target sinyal ($\le 0.2\%$ toleransi), atau `LIMIT` jika harga pasar bergeser terlalu jauh.
* **Real-time Position State Machine**:
  * Menggeser Stop Loss ke **Break-Even (BEP)** secara otomatis saat **TP1 (50%)** tercapai.
  * Mengaktifkan **Trailing Stop** (SL digeser ke level TP1) saat **TP2 (30%)** tercapai.
  * Menutup seluruh order exchange pendukung dan menghitung realized PnL saat posisi **CLOSED** (`TP3`, `SL`, atau `MANUAL_CLOSE`).
* **Emergency Circuit Breaker**: Menghentikan bot secara otomatis (*Auto-Pause*) jika akumulasi kerugian harian melampaui batas toleransi risiko modal.

### 2. ⚡ Web Dashboard REST & WebSocket API
* **FastAPI Lifespan Architecture**: Mengorkestrasi background runners (Telegram Poller, APScheduler 7 cron jobs, Binance User Stream) dan REST/WebSocket server secara terpadu.
* **Real-Time WebSocket Event Broker (`/api/v1/ws`)**: Streaming instan pembaruan order fill, pergerakan PnL, notifikasi TP/SL hit, dan perubahan status bot ke antarmuka web.
* **In-Memory Asynchronous Cache Layer**: Smart caching ber-TTL (10 detik s/d 30 menit) dengan mekanisme *write-through invalidation* saat mutasi data terjadi.
* **JWT Security & Silent Token Refresh**: Autentikasi dengan isolasi memory token dan penanganan otorisasi Role-Based Access Control (`ADMIN` vs `VIEWER`).

### 3. 🖥️ Web Dashboard UI (Pro-Trading Terminal)
* **Cyber-Fintech Dark Aesthetics**: Desain bertaraf TradingView/Binance Dark Mode dengan glassmorphism depth dan tipografi monospaced untuk seluruh angka finansial.
* **Executive Portfolio Analytics**: 6 KPI Summary Cards live dan grafik kurva pertumbuhan ekuitas (*TradingView Lightweight Charts*).
* **1-Click Signal Execution Wizard**: Eksekusi sinyal manual berkecepatan tinggi ($< 2\text{s}$) dengan verifikasi proteksi risiko maksimal 2% dan validasi geometri harga.
* **5-Level Trade Drilldown**: Inspeksi audit hierarki menyeluruh (*Overview*, *Risk Allocation*, *Order Lifecycle*, *Fill Executions*, *Financial Summary*).
* **Command Center**: Tombol *Pause/Resume*, *Watchlist Manager*, *Risk Sandbox Simulator*, dan *2-Step Emergency Panic Close All*.

---

## 📁 Struktur Direktori Monorepo

```text
crypto-bot/
├── backend/                             # 🐍 PURE PYTHON BACKEND ENGINE
│   ├── Dockerfile                       # Container definition backend
│   ├── requirements.txt                 # Dependencies Python
│   ├── alembic.ini                      # Konfigurasi migrasi database
│   ├── .env.example                     # Template environment backend
│   ├── main.py                          # Unified FastAPI Lifespan & Uvicorn entrypoint
│   ├── config/                          # Central Pydantic Settings
│   ├── src/
│   │   ├── api/                         # FastAPI Routers, Deps, WS Manager, App Factory
│   │   ├── clients/                     # CCXT Binance Futures & Telegram Clients
│   │   ├── database/                    # SQLAlchemy Async Engine, Models, Alembic Migrations
│   │   ├── repository/                  # Strict Repository Pattern (1 Model = 1 Repo)
│   │   ├── services/                    # Domain Services (Trade, Risk, Telegram, Scheduler)
│   │   └── utils/                       # Cache, Security, Precision, Error Parser
│   └── tests/                           # 346 Unit, Service, API & E2E Tests (100% Passing)
│
├── frontend/                            # ⚛️ PURE REACT/TYPESCRIPT WEB DASHBOARD
│   ├── Dockerfile                       # Multi-stage container build (Node 20 -> Nginx)
│   ├── nginx.conf                       # SPA routing & reverse proxy
│   ├── package.json                     # Dependencies npm (React 18, TanStack Query, Tailwind)
│   ├── tsconfig.json                    # Strict TypeScript configuration
│   ├── vite.config.ts                   # Vite bundler configuration
│   ├── tailwind.config.js               # Pro-trading dark theme tokens
│   ├── src/                             # Atomic components, feature modules, hooks, stores
│   └── tests/                           # Vitest & React Testing Library suites
│
├── docker/                              # 🐳 DOCKER GATEWAY & CONFIGS
│   └── nginx/
│       └── nginx.conf                   # Central Reverse Proxy Gateway (Port 80)
│
├── docs/                                # 📚 SYSTEM SPECIFICATIONS & PRD
│   ├── V3/                              # Backend V3 Clean Architecture Specifications
│   ├── frontend/                        # Frontend UI Docs (PRD, REQUIREMENTS, FEATURES, USER_FLOW, DESIGN)
│   ├── openapi.yaml                     # OpenAPI 3.1.0 Specification Contract
│   └── SCHEMA.md                        # Database Schema DDL Reference
│
├── tasks/                               # 📋 IMPLEMENTATION ROADMAPS & BACKLOGS
│   ├── web_dashboard_api/               # Tasks 01-11 Backend API (100% Completed)
│   └── frontend/                        # Tasks 01-13 Frontend UI (Ready to Execute)
│
├── docker-compose.yml                   # Master Multi-Container Orchestrator
└── README.md                            # Main Documentation Entrypoint
```

---

## 🚀 Panduan Menjalankan Sistem (Docker Compose)

### 1. Prasyarat Sistem
* [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/) v2.0+

### 2. Setup Environment Variables
Salin template environment di folder `backend/`:
```bash
cp backend/.env.example backend/.env
```

Sesuaikan variabel di `backend/.env`:
```env
# Binance Futures API Credentials
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
BINANCE_TESTNET=True

# Telegram Bot Notifications
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Database Configuration (PostgreSQL Docker)
DATABASE_URL=postgresql+asyncpg://cryptobot:cryptobot_pass@postgres:5432/cryptobot_db

# Security & JWT Authentication
JWT_SECRET_KEY=generate_a_secure_random_key_here
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=AdminPassword123!
```

---

### 3. Menjalankan Seluruh Service
Jalankan seluruh stack container (**PostgreSQL 16 + Backend API + Frontend UI + Nginx Gateway**) hanya dengan satu perintah:

```bash
docker compose up --build -d
```

---

### 4. Mengakses Layanan Sistem

| Layanan | URL Akses | Keterangan |
| :--- | :--- | :--- |
| **🌐 Web Dashboard UI** | [http://localhost](http://localhost) (atau `http://localhost:3000`) | Antarmuka Visual Trading Terminal |
| **⚡ REST API & Swagger UI** | [http://localhost/docs](http://localhost/docs) (atau `http://localhost:8000/docs`) | Dokumentasi Interaktif OpenAPI |
| **📡 WebSocket Stream** | `ws://localhost/ws` (atau `ws://localhost:8000/api/v1/ws`) | Live Data Event Stream |
| **🐘 PostgreSQL Database** | `localhost:5432` (`db: cryptobot_db`, `user: cryptobot`) | Relational Database Storage |

---

## 🧪 Menjalankan Test Suite

### 1. Menjalankan Backend Tests (346 Tests)
```bash
docker exec -it crypto_bot_app pytest tests/ -v
```

### 2. Menjalankan Static Type Checking (Mypy)
```bash
docker exec -it crypto_bot_app mypy --explicit-package-bases --ignore-missing-imports src/ main.py
```

### 3. Menjalankan Database Migrations (Alembic)
```bash
docker exec -it crypto_bot_app alembic upgrade head
```

---

## 📚 Indeks Dokumentasi Sistem

* **Spesifikasi Backend V3**:
  * [Product Requirements Document (docs/V3/PRD.md)](docs/V3/PRD.md)
  * [Clean Architecture Overview (docs/V3/ARCHITECTURE.md)](docs/V3/ARCHITECTURE.md)
  * [Business Rules & Risk Sizing (docs/V3/BUSINESS_RULES.md)](docs/V3/BUSINESS_RULES.md)
  * [Database Design & Relations (docs/V3/DATABASE.md)](docs/V3/DATABASE.md)
* **Spesifikasi Frontend Web Dashboard**:
  * [Product Requirements Document (docs/frontend/PRD.md)](docs/frontend/PRD.md)
  * [Software Requirements Specification (docs/frontend/REQUIREMENTS.md)](docs/frontend/REQUIREMENTS.md)
  * [Feature Specifications & User Stories (docs/frontend/FEATURES.md)](docs/frontend/FEATURES.md)
  * [User Flow & Interaction Diagrams (docs/frontend/USER_FLOW.md)](docs/frontend/USER_FLOW.md)
  * [Design System & Color Tokens (docs/frontend/DESIGN.md)](docs/frontend/DESIGN.md)
* **API Contract**:
  * [OpenAPI 3.1.0 Specification (docs/openapi.yaml)](docs/openapi.yaml)

---

## 📄 Lisensi
Hak Cipta © 2026 SMC CryptoBot. Seluruh hak cipta dilindungi undang-undang.
