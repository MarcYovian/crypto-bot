# Task 16: Cron Scheduler & Telegram Bot Services Implementation (Expanded - 7 Jobs & 12 Commands)

## 1. Deskripsi Task
Membangun dan memodernisasi **Layanan Pemeliharaan Otomatis Terjadwal (7 Background Jobs) & Antarmuka Interaktif Kontrol Telegram Bot (12 Commands & Interactive Buttons)**:
* **`SchedulerService`**: Mengelola 7 recurring background jobs menggunakan `APScheduler` untuk pemeliharaan berkala, manajemen risiko modal harian, sinkronisasi filter bursa, sanitasi database, dan pelaporan performa otomatis.
* **`TelegramService`**: Mengelola antarmuka interaktif Telegram Bot untuk monitoring akun, perintah kontrol darurat (`/panic`, `/pause`, `/resume`), manajemen watchlist & risiko, serta alur konfirmasi sinyal interaktif via tombol inline keyboard (`[ ✅ Approve ]` / `[ ❌ Reject ]`).

---

## 2. File yang Dibuat / Diubah
* `[MODIFY]` [`backend/src/services/scheduler_service.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/services/scheduler_service.py) *(SchedulerService - 7 Background Jobs)*
* `[MODIFY]` [`backend/src/services/telegram_service.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/services/telegram_service.py) *(TelegramService - 12 Commands & Interactive Handlers)*
* `[NEW]` [`backend/tests/services/test_scheduler_telegram_services.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/tests/services/test_scheduler_telegram_services.py)

---

## 3. Rincian Arsitektur & Isi Komponen

### 1. `SchedulerService` (`src/services/scheduler_service.py`)
* **Injeksi Dependensi:**
  * Repositories: `DailyRiskRepository`, `TradingAccountRepository`, `RiskProfileRepository`, `TradeRepository`, `OrderRepository`, `InstrumentRepository`, `TradeSummaryRepository`, `TradeEventRepository`, `BotLogRepository`, `BotSettingRepository`.
  * Services: `PositionManager`.
  * Clients: `BinanceRestClient`, `TelegramNotifierClient`.

* **Daftar 7 Background Cron Jobs:**
  1. **`run_daily_risk_snapshot_job(account_id: int = 1)`** *(Setiap 00:00 WIB)*:
     * Mengambil saldo ekuitas wallet riil dari `BinanceRestClient.fetch_balance()`.
     * Mengambil profil risiko aktif dari `RiskProfileRepository.get_active_profile()`.
     * Menghitung anggaran risiko harian: $\text{risk\_amount} = \text{balance} \times (\text{daily\_loss\_limit\_pct} / 100)$.
     * Menyimpan snapshot harian via `DailyRiskRepository.get_or_create_daily_snapshot(...)`.
     * Mengirim notifikasi ringkasan saldo & anggaran harian ke Telegram.
  2. **`run_cleanup_orphan_orders_job(account_id: int = 1, max_age_hours: int = 4)`** *(Setiap 30 Menit)*:
     * Mengambil trade `WAITING_ENTRY` yang menggantung > 4 jam via `TradeRepository.get_expired_waiting_trades()`.
     * Membatalkan sisa order di Binance (`BinanceRestClient.cancel_all_orders`) dan DB (`OrderRepository.cancel_all_open_orders_for_trade`).
     * Memperbarui status trade menjadi `CANCELLED` via `TradeRepository.update_trade_status`.
     * Mencatat event jejak audit `CANCELLED` / `ORDER_ERROR`.
  3. **`run_failsafe_sync_job(account_id: int = 1)`** *(Setiap 15 Menit)*:
     * Mengambil posisi terbuka riil dari Binance (`BinanceRestClient.fetch_positions()`).
     * Mengambil seluruh trade berstatus `OPEN` / `PARTIAL` dari `TradeRepository.get_all_active_trades()`.
     * Jika posisi di Binance sudah tertutup (size = 0) tetapi di database masih `OPEN`, sistem otomatis memanggil `PositionManager.finalize_trade_closure(trade_id, close_reason="FAILSAFE_SYNC")`.
  4. **`run_sync_instruments_metadata_job(exchange_id: int = 1)`** *(Setiap 12 Jam)*:
     * Mengambil metadata instrumen terbaru dari Binance (`BinanceRestClient.fetch_instruments_metadata()`).
     * Memperbarui `tick_size`, `step_size`, `min_notional`, dan `price_precision` di tabel `instruments` via `InstrumentRepository.bulk_upsert()`.
  5. **`run_purge_old_logs_job(days: int = 30)`** *(Setiap 03:00 WIB)*:
     * Menghapus log sistem lama di tabel `bot_logs` yang berusia lebih dari 30 hari via `BotLogRepository.purge_old_logs(days)`.
  6. **`run_daily_performance_report_job(account_id: int = 1)`** *(Setiap 00:05 WIB)*:
     * Mengambil riwayat closed trades kemarin dari `TradeSummaryRepository` / `TradeRepository`.
     * Menghitung total trade, win rate %, gross PnL, total komisi fee, dan net PnL.
     * Mengirimkan kartu laporan rekap harian otomatis ke Telegram.
  7. **`run_heartbeat_health_check_job()`** *(Setiap 1 Jam)*:
     * Memeriksa konektivitas database (kueri liveness), latency koneksi API Binance, dan status listener Telegram bot.
     * Mencatat log kesehatan `INFO` di `BotLogRepository`.

---

### 2. `TelegramService` (`src/services/telegram_service.py`)
* **Injeksi Dependensi:**
  * Services: `SignalParserService`, `RiskCalculatorService`, `TradeService`, `PositionManager`.
  * Repositories: `SignalRepository`, `TradeRepository`, `OrderRepository`, `DailyRiskRepository`, `TradeSummaryRepository`, `WatchlistRepository`, `InstrumentRepository`, `RiskProfileRepository`, `BotLogRepository`, `BotSettingRepository`.
  * Clients: `BinanceRestClient`, `TelegramNotifierClient`.

* **Daftar Lengkap 12 Command Handlers:**
  1. **`/start` & `/help`**: Menampilkan menu panduan perintah dan ringkasan status operasional bot.
  2. **`/account` & `/balance`**: Menampilkan saldo total wallet USDT, free margin, equity, dan unrealized PnL real-time dari Binance.
  3. **`/status` & `/positions`**: Menampilkan seluruh posisi terbuka, harga entry, target TP/SL, PnL berjalan, dan status BEP/Trailing.
  4. **`/pending` & `/orders`**: Menampilkan seluruh limit order yang sedang menunggu fill (`WAITING_ENTRY`) beserta usia antreannya.
  5. **`/summary` & `/performance`**: Menampilkan statistik performa trading akumulatif (Total Trades, Win Rate %, Net PnL, Total Fee Komisi, Avg R:R).
  6. **`/circuit_breaker`**: Menampilkan status proteksi kerugian harian, sisa batas risiko modal hari ini, dan status lock breaker.
  7. **`/close <trade_id/symbol>`**: Menutup 1 trade/posisi tertentu secara manual di pasar via `TradeService.close_trade_manually()`.
  8. **`/close_all` / `/panic`** *(Kill-Switch Darurat)*: Membatalkan seluruh pending orders di Binance & DB dan menutup seluruh posisi terbuka secara simultan.
  9. **`/pause`**: Menjeda bot sementara waktu agar tidak memproses atau mengeksekusi sinyal baru (misal saat rilis berita ekonomi besar).
  10. **`/resume`**: Mengaktifkan kembali penerimaan dan eksekusi sinyal trading otomatis.
  11. **`/watchlist [enable/disable <symbol>]`**: Menampilkan daftar pair yang dipantau serta mengaktifkan/menonaktifkan pair langsung dari Telegram.
  12. **`/logs` & `/ping`**: Mengambil 5 error log sistem terbaru untuk diagnosa cepat serta memeriksa latensi ke Binance dan database.

* **Alur Penanganan Pesan Sinyal & Tombol Interaktif (Interactive Confirmation):**
  1. Menerima pesan teks sinyal (dari grup/channel Telegram atau input manual).
  2. Mem-parsing teks menggunakan `SignalParserService.parse(text)`.
  3. Jika valid & bot tidak dalam status `PAUSED`:
     * Menyimpan sinyal ke `SignalRepository` (status `PENDING_CONFIRMATION`).
     * Menghitung estimasi lot size dan margin required via `RiskCalculatorService`.
     * Mengirim pesan kartu sinyal ke admin dengan tombol inline keyboard `[ ✅ Approve Trade ]` dan `[ ❌ Reject ]`.
  4. **Callback Query Handler (`on_callback_query`)**:
     * Saat user klik `APPROVE_<signal_id>`:
       * Mengubah status sinyal menjadi `APPROVED`.
       * Menjalankan eksekusi live via `TradeService.execute_signal()`.
       * Mengedit pesan Telegram menjadi kartu status konfirmasi sukses eksekusi.
     * Saat user klik `REJECT_<signal_id>`:
       * Mengubah status sinyal menjadi `REJECTED`.
       * Mengedit pesan Telegram menjadi "Sinyal Ditolak".

---

## 4. Rincian Unit Test & Test Cases (`test_scheduler_telegram_services.py`)

### File Test: `backend/tests/services/test_scheduler_telegram_services.py`

### Daftar Test Cases yang Diuji:
1. **`test_scheduler_daily_risk_snapshot_job_success`**:
   * *Aksi:* Eksekusi `run_daily_risk_snapshot_job()` pada pukul 00:00 WIB.
   * *Assert:* Snapshot modal tersimpan di database, anggaran risiko 2% terhitung akurat, notifikasi Telegram terkirim.
2. **`test_scheduler_cleanup_orphan_orders_job`**:
   * *Aksi:* Simulasikan trade `WAITING_ENTRY` yang menggantung > 4 jam, jalankan `run_orphan_order_cleanup_job()`.
   * *Assert:* Order di Binance & DB dibatalkan, status trade menjadi `CANCELLED`.
3. **`test_scheduler_failsafe_sync_closes_desynced_trade`**:
   * *Aksi:* Simulasikan posisi di DB berstatus `OPEN` namun di Binance posisi sudah 0, jalankan `run_failsafe_sync_job()`.
   * *Assert:* Trade ditutup otomatis dengan `close_reason="FAILSAFE_SYNC"` dan `TradeSummary` dibuat.
4. **`test_scheduler_sync_instruments_metadata_job`**:
   * *Aksi:* Jalankan `run_sync_instruments_metadata_job()`.
   * *Assert:* Filter `tick_size` dan `step_size` terbaru di-upsert ke database.
5. **`test_scheduler_purge_old_logs_job`**:
   * *Aksi:* Simulasikan log berusia > 30 hari, jalankan `run_purge_old_logs_job()`.
   * *Assert:* Log lama terhapus dari tabel `bot_logs`.
6. **`test_scheduler_daily_performance_report_job`**:
   * *Aksi:* Jalankan `run_daily_performance_report_job()`.
   * *Assert:* Rekap PnL dihitung dan pesan rekap performa terkirim ke Telegram.
7. **`test_scheduler_heartbeat_health_check_job`**:
   * *Aksi:* Jalankan `run_heartbeat_health_check_job()`.
   * *Assert:* Status health check berhasil dan record log sistem tercatat.
8. **`test_telegram_command_balance_response`**:
   * *Aksi:* Handler command `/balance`.
   * *Assert:* Membaca saldo dari Binance client dan mengembalikan format pesan HTML yang rapi.
9. **`test_telegram_command_status_active_positions`**:
   * *Aksi:* Handler command `/status` dengan 2 posisi aktif.
   * *Assert:* Format pesan mencantumkan simbol, side, leverage, entry price, dan status BEP.
10. **`test_telegram_command_pending_orders`**:
    * *Aksi:* Handler command `/pending`.
    * *Assert:* Format pesan mencantumkan daftar limit order yang menunggu eksekusi.
11. **`test_telegram_command_summary_performance`**:
    * *Aksi:* Handler command `/summary`.
    * *Assert:* Menampilkan total trade, win rate, net PnL, dan total fee komisi.
12. **`test_telegram_command_close_manual_trade`**:
    * *Aksi:* Handler command `/close <trade_id>`.
    * *Assert:* Menutup posisi via `TradeService.close_trade_manually` dan membalas konfirmasi sukses.
13. **`test_telegram_command_panic_close_all`**:
    * *Aksi:* Handler command `/panic` / `/close_all`.
    * *Assert:* Seluruh trade aktif ditutup simultan dan order dibatalkan.
14. **`test_telegram_command_pause_and_resume`**:
    * *Aksi:* Handler command `/pause` dan `/resume`.
    * *Assert:* Flag bot setting `is_trading_paused` berubah status di database.
15. **`test_telegram_command_watchlist_management`**:
    * *Aksi:* Handler command `/watchlist disable BTCUSDT` dan `/watchlist enable BTCUSDT`.
    * *Assert:* Status whitelist pair berubah di `WatchlistRepository`.
16. **`test_telegram_interactive_signal_approval_callback`**:
    * *Aksi:* Simulasikan klik tombol inline `APPROVE_<signal_id>`.
    * *Assert:* Sinyal diproses, `TradeService.execute_signal` dipanggil, pesan inline di-update.
17. **`test_telegram_interactive_signal_rejection_callback`**:
    * *Aksi:* Simulasikan klik tombol inline `REJECT_<signal_id>`.
    * *Assert:* Status sinyal menjadi `REJECTED` dan tidak memicu order Binance.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/services/test_scheduler_telegram_services.py -v
```
