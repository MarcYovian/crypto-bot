# Task 08: Bot Operations, Circuit Breaker & Settings Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint kontrol operasional runtime trading bot (`/api/v1/bot/status`, `/pause`, `/resume`, `/panic`), konfigurasi bot dinamis (`/api/v1/settings`), dan rotasi kredensial Binance API Key dengan validasi uji handshake otomatis (`/api/v1/settings/credentials`).

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/routers/bot.py`: Router FastAPI untuk kontrol operasional bot.
* `backend/src/api/routers/settings.py`: Router FastAPI untuk konfigurasi setting & kredensial Binance.
* `backend/tests/api/test_bot_settings_api.py`: Test suite untuk router bot dan settings.

### Modifikasi File:
* `backend/src/api/app.py`: Menambahkan mounting `bot_router` dan `settings_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `GET /api/v1/bot/status`:
  * **Logika**: Mengambil status runtime engine (apakah bot aktif/pause, status circuit breaker, koneksi User Data Stream Binance WebSocket, status polling Telegram, dan jumlah background cron job aktif).
  * **Response (200)**: `BotStatusDTO`.
* `POST /api/v1/bot/pause`:
  * **Logika**: Mengubah `is_paused = True` di tabel `bot_settings`. Sinyal baru yang masuk akan ditolak, posisi berjalan tetap dimonitor.
  * **Response (200)**: `GenericActionResponse`.
* `POST /api/v1/bot/resume`:
  * **Logika**: Mengubah `is_paused = False` dan mengaktifkan kembali bot.
  * **Response (200)**: `GenericActionResponse`.
* `POST /api/v1/bot/panic`:
  * **Payload**: `{"confirmation": true}`.
  * **Logika**: Menutup seluruh posisi terbuka (`OPEN`, `PARTIAL`, `WAITING_ENTRY`) via Market order Reduce-Only, membatalkan seluruh pending orders di Binance, dan mengubah status bot menjadi `PAUSED`.
  * **Response (200)**: `{"success": true, "closed_trades_count": int, "canceled_orders_count": int, "timestamp": str}`.
* `GET /api/v1/settings`:
  * **Strategi Caching**: Cache key `settings:active` disimpan di in-memory cache.
  * **Logika**: Mengambil konfigurasi aktif dari tabel `bot_settings` dan `risk_profiles`.
  * **Response (200)**: `BotSettingsDTO`.
* `PUT /api/v1/settings`:
  * **Payload**: `BotSettingsUpdateRequest` (`default_leverage`, `confidence_threshold`, `risk_percent_per_trade`, `max_daily_loss_percent`, `max_open_trades`).
  * **Strategi Caching**: Memanggil `cache.invalidate("settings")` seketika saat setting disimpan.
  * **Logika**: Menyimpan pembaruan konfigurasi ke database.
  * **Response (200)**: `BotSettingsDTO`.
* `POST /api/v1/settings/credentials`:
  * **Payload**: `TradingCredentialCreateRequest` (`api_key`, `secret_key`, `environment: TESTNET | LIVE`).
  * **Strategi Caching**: Memanggil `cache.invalidate("settings")` dan `cache.invalidate("accounts")`.
  * **Logika**: Melakukan uji handshake (*account balance check*) ke Binance. Jika handshake sukses, menyimpan kredensial terenkripsi ke database dan me-reload engine client secara dinamis (*hot-reload*).
  * **Response (200)**: `{"success": true, "account_id": int, "wallet_balance_usdt": float, "environment": str}`.

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Pause/Resume Efektif**: Toggle pause melalui API langsung menghentikan penerimaan sinyal baru di seluruh service.
2. **Panic Close Teruji**: Memanggil `/bot/panic` dengan konfirmasi benar-benar menutup semua posisi terbuka dan membatalkan seluruh order.
3. **Uji Handshake Kredensial**: Input API key yang salah ditolak dengan pesan error yang jelas; API key yang benar terhubung dan langsung menampilkan saldo bursa.
4. **Smart Settings Invalidation**: Pembaruan setting via API langsung memperbarui cache tanpa restart server.
5. **Testing**: Seluruh test di `backend/tests/api/test_bot_settings_api.py` lulus 100%.
