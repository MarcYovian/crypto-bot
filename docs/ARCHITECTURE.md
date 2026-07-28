# 🏗 System Architecture & Technical Specifications

Dokumen ini menjelaskan arsitektur teknis dan *design patterns* dari **Semi-Automated Binance Futures Trading Bot V2**.

---

## 1. Architectural Pattern: Service-Repository Pattern

Aplikasi dirancang menggunakan **Layered Architecture (Service-Repository Pattern)** untuk memastikan pemisahan tanggung jawab (*Separation of Concerns*) secara bersih:

```text
       ┌─────────────────────────────────────────┐
       │             Telegram Bot                │
       └────────────────────┬────────────────────┘
                            │
       ┌────────────────────▼────────────────────┐
       │            Services Layer               │
       │  (SignalParser, ExecutionEngine, etc.)   │
       └────────────────────┬────────────────────┘
                            │
       ┌────────────────────▼────────────────────┐
       │           Repositories Layer            │
       │   (TradeRepo, SignalRepo, EventRepo)    │
       └────────────────────┬────────────────────┘
                            │
       ┌────────────────────▼────────────────────┐
       │         Database Layer (SQLite)         │
       └─────────────────────────────────────────┘
```

1. **Database Layer (`src/database/`)**:
   - Skema tabel relasional SQLAlchemy Async ORM (`TradingSignal`, `Trade`, `Order`, `Execution`, `TradeEvent`, `DailyRiskConfig`, `TradeSummary`, `Watchlist`).
2. **Repository Layer (`src/repository/`)**:
   - Menangani operasi *Create, Read, Update, Delete* (CRUD) serta query agregasi PnL/Summary tanpa mengandung logika bisnis.
3. **Services Layer (`src/services/`)**:
   - Berisi seluruh logika domain bisnis (Risk Calculation, Order Execution Engine, Position Lifecycle State Machine, Telegram Service, WebSocket Listener, Cron Scheduler).
4. **Utils Layer (`src/utils/`)**:
   - Helper independen seperti `ErrorParser` untuk mengklasifikasi exception ke Telegram.

---

## 2. Risk Management & Slippage Protection Algorithm

Bot menjamin tidak pernah merugikan saldo melebihi **2.0% Daily Risk**:

1. **Daily Risk Snapshot (00:00 WIB)**:
   - Mengambil saldo akun Binance Futures jam 00:00 WIB, menghitung `Risk Amount = Balance * 0.02`, dan menguncinya di DB untuk seluruh transaksi hari tersebut.
2. **Real-time Market Order Recalculation**:
   - Jika eksekusi berupa `MARKET` order dan terjadi pergeseran harga pasar (*slippage*), bot mengukur ulang *Stop Distance* riil terhadap harga pasar detik itu juga.
   - Ukuran posisi (`position_size`) secara otomatis disesuaikan (*downsized*) sehingga `Potential Loss = Position Size * (Current Price - SL Price)` **tetap dijamin ≤ 2.0%**.

---

## 3. Real-time Event-Driven Position State Machine

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
- **TP3 / SL Hit**: Log penutupan, batalkan seluruh order sisa di Binance, hitung **Gross PnL, Est. Commission, Funding Fee, Net PnL, ROI, RR, & Duration**, lalu simpan ke `TradeSummary`.

---

## 4. Centralized Error Parser System

Seluruh kegagalan eksekusi diproses melalui `ErrorParser` di `src/utils/error_parser.py`:
- **`RISK`**: Kegagalan validasi jarak SL atau Min Notional.
- **`BALANCE`**: Saldo margin tidak mencukupi (API `-2019`).
- **`EXCHANGE`**: Presisi desimal berlebih (API `-1111`) atau melebihi batas lot bursa (API `-4005`).
- **`SYSTEM`**: Exception internal atau database timeout.

Pesan diformat menggunakan ikon dan rekomendasi tindakan yang jelas sebelum dikirimkan ke Telegram.
