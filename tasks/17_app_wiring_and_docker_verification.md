# Task 17: Application Wiring, Dependency Injection & Docker Verification (Expanded)

## 1. Deskripsi Task
Menggabungkan seluruh komponen arsitektur modular baru (**Database ➔ Repositories ➔ Clients ➔ Services**) ke dalam entry point utama [`backend/main.py`](../backend/main.py) menggunakan prinsip *Clean Dependency Injection*, menangani *Graceful Shutdown* (`SIGINT`/`SIGTERM`), membangun pengujian integrasi E2E komprehensif (*End-to-End Trade Lifecycle*), serta verifikasi containerisasi Docker.

---

## 2. File yang Dibuat / Diubah
* `[MODIFY]` [`backend/main.py`](../backend/main.py) *(Main Application Entry Point & Clean DI Container)*
* `[MODIFY]` [`Dockerfile`](../Dockerfile) *(Update Python 3.12 & optimize build)*
* `[MODIFY]` [`docker-compose.yml`](../docker-compose.yml) *(Configuration & healthchecks)*
* `[NEW]` [`backend/tests/test_e2e_integration.py`](../backend/tests/test_e2e_integration.py) *(Full E2E Trade Lifecycle Suite)*

---

## 3. Rincian Arsitektur & Wiring di `main.py`

### 1. Inisialisasi Dependency Injection Layer:
```
                                ┌──────────────────────────────────────────────┐
                                │             DATABASE ENGINE POOL             │
                                │           (AsyncSessionLocal / Pool)         │
                                └──────────────────────┬───────────────────────┘
                                                       │
               ┌───────────────────────────────────────┴──────────────────────────────────────┐
               ▼                                                                              ▼
┌───────────────────────────────┐                                              ┌───────────────────────────────┐
│     DATA ACCESS LAYER (11)    │                                              │      EXTERNAL CLIENTS (4)     │
│ • ExchangeRepo                │                                              │ • BinanceRestClient           │
│ • TradingAccountRepo          │                                              │ • BinanceWebSocketClient      │
│ • InstrumentRepo              │                                              │ • TelegramNotifierClient      │
│ • WatchlistRepo               │                                              │ • TelegramChannelListener     │
│ • StrategyRepo                │                                              └──────────────┬────────────────┘
│ • SignalProviderRepo          │                                                             │
│ • RiskProfileRepo             │                                                             │
│ • SignalRepo                  │                                                             │
│ • DailyRiskRepo               │                                                             │
│ • TradeRepo                   │                                                             │
│ • TradeRiskRepo               │                                                             │
│ • OrderRepo                   │                                                             │
│ • ExecutionRepo               │                                                             │
│ • TradeEventRepo              │                                                             │
│ • TradeSummaryRepo            │                                                             │
│ • BotLogRepo                  │                                                             │
│ • BotSettingRepo              │                                                             │
└──────────────┬────────────────┘                                                             │
               │                                                                              │
               └───────────────────────────────────────┬──────────────────────────────────────┘
                                                       ▼
                                ┌──────────────────────────────────────────────┐
                                │            BUSINESS LOGIC SERVICES           │
                                │ • PrecisionFilterService                     │
                                │ • SignalParserService                        │
                                │ • RiskCalculatorService                      │
                                │ • TradeService                               │
                                │ • PositionManager                            │
                                │ • SchedulerService (7 Jobs)                  │
                                │ • TelegramService (12 Commands)              │
                                └──────────────────────┬───────────────────────┘
                                                       ▼
                                ┌──────────────────────────────────────────────┐
                                │             MAIN RUNTIME RUNNERS             │
                                │ 1. APScheduler Cron Runner                   │
                                │ 2. Telegram Bot Polling / Webhook            │
                                │ 3. Binance WebSocket Stream Consumer         │
                                │ 4. Channel Signal Listener                   │
                                └──────────────────────────────────────────────┘
```

### 2. Startup Sequence:
1. `init_db()`: Validasi koneksi database engine dan migrasi tabel ORM.
2. Inisialisasi seluruh instance Repositories dengan database session manager.
3. Inisialisasi Third-Party Clients (Binance REST/WS, Telegram Bot Client & Channel Listener).
4. Inisialisasi Business Services (`RiskCalculator`, `SignalParser`, `TradeService`, `PositionManager`).
5. Inisialisasi & Start `SchedulerService` (7 background maintenance jobs).
6. Start Asynchronous WebSocket Stream Consumer (mendengarkan event fill order real-time dari Binance).
7. Start Telegram Bot polling (menangani 12 commands dan konfirmasi tombol sinyal inline).
8. Logging: `"🚀 Crypto Bot Successfully Started & Listening for Market Signals..."`.

### 3. Graceful Shutdown Sequence (`SIGINT` / `SIGTERM`):
1. Menangkap sinyal OS interrupt.
2. Menghentikan scheduler (`scheduler_service.stop()`).
3. Menghentikan polling Telegram bot updater.
4. Menutup koneksi WebSocket stream Binance (`ws_client.close()`).
5. Menutup koneksi REST client CCXT (`binance_client.close()`).
6. Melepaskan database engine pool (`engine.dispose()`).
7. Logging: `"🛑 Crypto Bot Gracefully Stopped."`.

---

## 4. Rincian Pengujian Integrasi E2E (`test_e2e_integration.py`)

### File Test: `backend/tests/test_e2e_integration.py`

### Skenario Uji Siklus Hidup Penuh (*Full Trade Lifecycle E2E*):
1. **`test_e2e_full_trade_lifecycle_win`**:
   * **Tahap 1 (Snapshot)**: Scheduler menjalankan `run_daily_risk_snapshot_job()` ➔ Saldo $10,000 terkunci, anggaran risiko $200 (2%) aktif.
   * **Tahap 2 (Sinyal)**: Pesan sinyal teks diterima via Telegram ➔ `SignalParserService` mem-parsing sinyal ➔ Sinyal tersimpan sebagai `PENDING_CONFIRMATION`.
   * **Tahap 3 (Approval)**: Admin klik `APPROVE_<signal_id>` ➔ `TradeService.execute_signal()` dijalankan ➔ Validasi whitelist & duplikasi lolos ➔ Ukuran lot dihitung ➔ Order `ENTRY`, `SL`, dan `TP1..3` dibuat di bursa & DB ➔ Status trade: `WAITING_ENTRY`.
   * **Tahap 4 (Entry Fill)**: WebSocket menerima fill order Entry ➔ `PositionManager.handle_order_fill(ENTRY)` ➔ Trade status berubah menjadi `OPEN`.
   * **Tahap 5 (TP1 Hit & BEP)**: WebSocket menerima fill order TP1 ➔ `PositionManager.handle_order_fill(TP1)` ➔ Qty berkurang 50% ➔ SL awal dibatalkan ➔ SL baru digeser ke Break-Even (`entry_price`) ➔ Event `TP1_HIT` & `SL_MOVED_TO_BEP` tercatat ➔ Alert terkirim ke Telegram.
   * **Tahap 6 (TP2 Hit & Trailing)**: WebSocket menerima fill order TP2 ➔ `PositionManager.handle_order_fill(TP2)` ➔ Qty berkurang 25% ➔ SL BEP dibatalkan ➔ SL baru digeser ke Trailing level (`tp1_price`) ➔ Event `TP2_HIT` & `TRAILING_SL_UPDATED` tercatat.
   * **Tahap 7 (TP3 Hit & Trade Finalization)**: WebSocket menerima fill order TP3 ➔ `PositionManager.handle_order_fill(TP3)` ➔ Semua order sisa dibatalkan ➔ Komisi & net PnL dihitung ➔ `TradeSummary` dibuat dengan status `WIN` ➔ Status trade menjadi `CLOSED`.
   * **Tahap 8 (Daily Recap)**: Scheduler menjalankan `run_daily_performance_report_job()` ➔ Laporan Win Rate 100% dan Net PnL positif terkirim ke Telegram.

2. **`test_e2e_trade_lifecycle_stop_loss_hit`**:
   * Sinyal masuk ➔ Dieksekusi ➔ Entry Fill (`OPEN`) ➔ Harga berbalik menyentuh `SL` sebelum TP1 ➔ `PositionManager.handle_order_fill(SL)` ➔ Semua TP dibatalkan ➔ `TradeSummary` dibuat dengan status `LOSS` ➔ Status trade `CLOSED` ➔ Toleransi risiko harian berkurang sesuai loss.

3. **`test_e2e_circuit_breaker_lockout`**:
   * Simulasikan akumulasi loss mencapai batas risiko harian ($200) ➔ Sinyal baru masuk ➔ `TradeService.execute_signal()` menolak eksekusi dengan `DailyRiskLimitReachedError` ➔ Pesan penolakan terkirim.

---

## 5. Rencana Verifikasi (Verification Plan)

### 1. Automated E2E & Full Test Suite:
```bash
PYTHONPATH=backend pytest backend/tests/test_e2e_integration.py -v
PYTHONPATH=backend pytest -v
```

### 2. Docker Verification:
```bash
docker compose build crypto-bot
docker compose up -d
docker compose ps
docker compose logs -n 50 crypto-bot
```

### Kriteria Keberhasilan:
* Seluruh 105+ unit test dan pengujian E2E integrasi lulus 100%.
* Entry point `backend/main.py` bersih, terstruktur rapi dengan Dependency Injection.
* Bot berjalan stabil tanpa crash dalam container Docker.
