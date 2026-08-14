# 🏗 System Architecture & Technical Specifications

Dokumen ini menjelaskan arsitektur teknis, struktur repositori, dan *design patterns* dari **Semi-Automated Binance Futures Trading Bot V2** (`backend/`).

---

## 1. Backend Repository Structure (`backend/`)

```text
backend/
├── config/
│   └── settings.py          # Konfigurasi aplikasi & Pydantic BaseSettings (.env loader)
├── src/
│   ├── database/
│   │   ├── connection.py    # Async Engine SQLAlchemy & Session Factory (SQLite/PostgreSQL)
│   │   └── models.py        # Skema Tabel Relasional ORM (TradingSignal, Trade, Order, Execution, dll)
│   ├── repository/
│   │   ├── signal_repository.py  # Repository pattern CRUD untuk data TradingSignal
│   │   └── trade_repository.py   # Repository pattern CRUD & Query agregasi PnL (Trade, Order, Summary)
│   ├── services/
│   │   ├── execution_engine.py   # Wrapper CCXT Async Binance Futures (Leverage, Margin, Order Placement)
│   │   ├── position_manager.py   # Event-driven State Machine posisi (SL to BEP, Trailing SL, TP, Closure)
│   │   ├── precision_filter.py   # PrecisionFilter & SymbolInfo (Formatting Step Size & Min Notional)
│   │   ├── risk_calculator.py    # RiskCalculatorService (2.0% Daily Risk & Dynamic Position Sizing)
│   │   ├── scheduler_service.py  # CronSchedulerService (APScheduler: Snapshot 00:00 WIB & Daily Broadcast)
│   │   ├── signal_parser.py      # Regex & Pattern Extractor sinyal perdagangan dari Telegram
│   │   ├── telegram_service.py   # Bot Interaktif Telegram (Commands, Inline Button Callbacks, Alerts)
│   │   ├── trade_service.py      # Orchestrator eksekusi sinyal (Validation -> Prep -> Order Execution)
│   │   └── websocket_listener.py # CCXT Pro WebSocket Listener (Binance User Data Stream)
│   └── utils/
│       └── error_parser.py       # Centralized Error Parser (Kategorisasi Exception RISK, BALANCE, EXCHANGE, SYSTEM)
├── scripts/
│   └── test_integration.py  # Script tes integrasi backend secara terisolasi
├── tests/                   # Suite Unit Test Pytest (Coverage service, repo, error parser)
└── main.py                  # Application Entry Point & Async Startup/Shutdown Sequence Lifecycle
```

---

## 2. Architectural Pattern: Service-Repository & Event-Driven Architecture

Aplikasi dirancang menggunakan **Layered Architecture (Service-Repository Pattern)** yang dikombinasikan dengan **Event-Driven WebSocket Stream**:

```text
               ┌───────────────────────────────────────────────┐
               │           Telegram Bot Interface              │
               │   (Commands: /status, /balance, Callbacks)    │
               └───────────────────────┬───────────────────────┘
                                       │
               ┌───────────────────────▼───────────────────────┐
               │                Services Layer                 │
               │  - SignalParser       - TradeService          │
               │  - RiskCalculator     - ExecutionEngine       │
               │  - PositionManager    - PrecisionFilter       │
               │  - WebSocketListener  - CronScheduler         │
               └───────────┬───────────────────────┬───────────┘
                           │                       │
 ┌─────────────────────────▼────────┐    ┌─────────▼────────────────────────┐
 │        Repository Layer          │    │       External Integrations      │
 │ (TradeRepo, SignalRepo)          │    │ (Binance REST API & CCXT Pro WS) │
 └────────────┬─────────────────────┘    └──────────────────────────────────┘
              │
 ┌────────────▼─────────────────────┐
 │     Database Layer (SQLAlchemy)   │
 └──────────────────────────────────┘
```

### Layer Breakdown & Responsibilities

1. **Application Entry Point (`main.py`)**:
   - Menangani siklus hidup startup async: Inisialisasi DB (`init_db`), instansiasi execution engine, repositori, `PositionManager`, `TelegramService`, `CronSchedulerService` (APScheduler), dan background task `BinanceStreamListener`.
   - Mengelola *graceful shutdown* saat menerima sinyal `KeyboardInterrupt` atau `SystemExit`.

2. **Configuration (`config/settings.py`)**:
   - Menggunakan Pydantic `BaseSettings` untuk memuat environment variables secara aman (`.env`), seperti API Keys, Telegram Token, Chat ID, Leverage default, Risk Percent limit, dan Database URL.

3. **Database Layer (`src/database/`)**:
   - **`connection.py`**: Mengelola koneksi database async (`AsyncEngine`, `AsyncSessionLocal`).
   - **`models.py`**: Berisi skema ORM SQLAlchemy:
     - `TradingSignal`: Teks sinyal mentah, hasil parsing JSON, dan status (`PENDING`, `PREPARED`, `EXECUTED`, `REJECTED`, `EXPIRED`, `CANCELLED`).
     - `Trade`: Metadata perdagangan, sisi (`LONG`/`SHORT`), posisi margin, leverage, parameter SL/TP.
     - `Order`: Log detail pesanan yang ditempatkan di Binance Futures.
     - `Execution`: Log fill aktual dari bursa (fill price, fill qty, komisi, realized PnL).
     - `TradeEvent`: Timeline audit perubahan status trade dan event bursa.
     - `DailyRiskConfig`: Lock saldo awal & batasan *Risk Amount* harian (diambil 00:00 WIB).
     - `TradeSummary`: Hasil akhir trade setelah ditutup (Gross PnL, Net PnL, Komisi, Funding Fee, ROI, RR Ratio, Durasi).
     - `Watchlist`: Daftar pair mata uang kripto yang dipantau.

4. **Repository Layer (`src/repository/`)**:
   - **`SignalRepository`**: Abstraksi CRUD untuk tabel `TradingSignal`.
   - **`TradeRepository`**: Abstraksi CRUD dan fungsi agregasi PnL/Summary tanpa mengandung logika bisnis.

5. **Services Layer (`src/services/`)**:
   - **`TradeService`**: Mengorkestrasi workflow persiapan transaksi (`prepare_trade`) dan pengiriman pesanan ke bursa (`execute_trade`).
   - **`RiskCalculatorService`**: Menghitung ukuran posisi (*position size*), margin yang dibutuhkan, dan memvalidasi batas *Min Notional* serta *LOT_SIZE*.
   - **`PrecisionFilter`**: Menyesuaikan presisi harga dan jumlah lot sesuai spesifikasi filter bursa Binance (`SymbolInfo`).
   - **`BinanceExecutionEngine`**: Mengelola komunikasi REST API ke Binance Futures menggunakan CCXT (margin mode, leverage, order placement, cancel order).
   - **`PositionManager`**: State machine pengelola posisi berbasis WebSocket event (`ORDER_TRADE_UPDATE`, `ACCOUNT_UPDATE`).
   - **`BinanceStreamListener`**: Membuka stream WebSocket CCXT Pro User Data untuk menerima pembaruan order dan saldo secara real-time.
   - **`TelegramService`**: Antarmuka bot Telegram untuk menerima sinyal, menangani tombol konfirmasi inline, serta eksekusi command (`/start`, `/status`, `/balance`, `/active`, `/history`, `/summary`, `/cancel`, `/close`).
   - **`SignalParser`**: Extractor regex untuk mengurai pesan sinyal mentah menjadi objek `ParsedSignal`.
   - **`CronSchedulerService`**: Menjalankan cron job terjadual (Daily Risk Snapshot 00:00 WIB, Daily PnL Summary Broadcast 23:59 WIB, dan Watchlist Update).

6. **Utils Layer (`src/utils/`)**:
   - **`ErrorParser`**: Mengklasifikasi exception runtime menjadi kategori `RISK`, `BALANCE`, `EXCHANGE`, atau `SYSTEM` dan menghasilkan pesan alert Telegram yang ramah pengguna.

---

## 3. End-to-End Signal & Trade Execution Lifecycle Workflow

```text
[ Telegram Message ]
        │
        ▼
[ SignalParser ] ─── (Parse Signal Attributes: Symbol, Side, Entry, TPs, SL)
        │
        ▼
[ Telegram Bot UI ] ─── (Displays Signal Card with Interactive Confirm/Cancel Buttons)
        │ (User clicks "Confirm")
        ▼
[ TradeService.prepare_trade ]
        ├── Load / Create Daily Risk Snapshot (00:00 WIB Balance Lock)
        ├── Fetch Binance Symbol Info (Step Size, Price Precision)
        └── RiskCalculatorService.calculate_position
                │
                ├── Valid? ──► DB Record (Trade: WAITING_ENTRY / OPEN)
                └── Invalid? ──► Update Signal Status "REJECTED" & Telegram Error Alert
        │
        ▼
[ TradeService.execute_trade ]
        └── BinanceExecutionEngine.execute_trade_pipeline
                ├── Set Leverage & Margin Mode (Isolated)
                ├── Place Entry Order (MARKET / LIMIT)
                └── Place TP Limit Orders
        │
        ▼
[ BinanceStreamListener (WebSocket CCXT Pro) ]
        │ (Receives ORDER_TRADE_UPDATE)
        ▼
[ PositionManager State Machine ]
        ├── Entry Filled ──► Status: OPEN
        ├── TP1 Hit ──► Status: PARTIAL, Cancel Old SL, Place SL at BEP
        ├── TP2 Hit ──► Status: PARTIAL, Cancel Old SL, Place Trailing SL at TP1
        └── TP3 / SL Hit ──► Cancel Remaining Orders, Calculate Net PnL & Save TradeSummary
```

---

## 4. Risk Management & Slippage Protection Algorithm

Bot menjamin saldo akun tidak pernah mengalami kerugian melebihi **2.0% Daily Risk**:

1. **Daily Risk Snapshot (00:00 WIB)**:
   - Mengambil saldo akun Binance Futures pada jam 00:00 WIB melalui `CronSchedulerService`.
   - Menghitung `Risk Amount = Balance * 0.02` dan menguncinya di tabel `DailyRiskConfig` untuk seluruh transaksi hari tersebut.
2. **Real-time Market Order Recalculation**:
   - Jika eksekusi berupa `MARKET` order dan terjadi pergeseran harga pasar (*slippage*), bot mengukur ulang *Stop Distance* riil terhadap harga pasar detik tersebut.
   - Ukuran posisi (`position_size`) secara otomatis disesuaikan (*downsized*) sehingga `Potential Loss = Position Size * (Current Price - SL Price)` **tetap dijamin ≤ 2.0%**.
3. **Exchange Filters Validation**:
   - Memvalidasi *LOT_SIZE* (minimal quantity & step size) serta *MIN_NOTIONAL* (minimal nilai transaksi USDT). Transaksi yang tidak memenuhi syarat bursa ditolak secara otomatis.

---

## 5. Real-time Event-Driven Position State Machine

Manajemen posisi dilakukan tanpa polling REST API berkat integrasi **CCXT Pro WebSocket User Data Stream (`BinanceStreamListener`)**:

```text
[Signal Received] ──► WAITING_ENTRY / OPEN ──► TP1 Fill ──► SL Moved to BEP (PARTIAL)
                                                  │
                                            TP2 Fill ──► Trailing Stop (SL to TP1)
                                                  │
                                            TP3 / SL Fill ──► CLOSED & Audit Summary
```

- **TP1 Hit**: Log `TP1`, ubah status ke `PARTIAL`, batalkan SL lama, pasang `STOP_MARKET` baru di **BEP Price**.
- **TP2 Hit**: Log `TP2`, ubah status ke `PARTIAL`, batalkan SL BEP, pasang `STOP_MARKET` baru di **TP1 Price (Trailing Stop)**.
- **TP3 / SL Hit**: Log penutupan, batalkan seluruh order sisa di Binance, hitung **Gross PnL, Est. Commission, Funding Fee, Net PnL, ROI, RR, & Duration**, lalu simpan ke `TradeSummary` dan kirimkan ringkasan ke Telegram.

---

## 6. Centralized Error Parser System

Seluruh kegagalan eksekusi diproses melalui `ErrorParser` di `src/utils/error_parser.py`:
- **`RISK`**: Kegagalan validasi jarak SL atau Min Notional.
- **`BALANCE`**: Saldo margin tidak mencukupi (API `-2019`).
- **`EXCHANGE`**: Presisi desimal berlebih (API `-1111`) atau melebihi batas lot bursa (API `-4005`).
- **`SYSTEM`**: Exception internal atau database timeout.

Pesan diformat menggunakan ikon dan rekomendasi tindakan yang jelas sebelum dikirimkan ke Telegram.
