# Task 08: Bot Operations, Circuit Breaker & Configuration Settings Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint operasional runtime bot (`/api/v1/bot/status`, `/api/v1/bot/pause`, `/api/v1/bot/resume`, `/api/v1/bot/panic`), manajemen profil risiko & pengaturan bot (`GET & PUT /api/v1/settings`), serta pendaftaran dan rotasi API Key Binance dengan uji handshake live balance (`POST /api/v1/settings/credentials`).

Implementasi ini secara ketat menerapkan **Domain-Driven Service-Repository Pattern**:
* **Domain Layer**:
  * DTO: `BotStatusDTO`, `GenericActionResponse`, `BotSettingsDTO`, `BotSettingsUpdateRequest`, `TradingCredentialCreateRequest`, `PanicCloseResponseDTO`, `CredentialSaveResponseDTO`.
  * Domain Exceptions: `BotOperationError`, `PanicConfirmationRequiredError`, `InvalidSettingsValueError`, `ExchangeAuthError`.
* **Repository Layer**:
  * `BotSettingRepository`: Mengambil dan mengupdate key-value persistent setting bot (`is_paused`, `default_leverage`, `confidence_threshold`, `circuit_breaker_active`).
  * `RiskProfileRepository`: Mengambil dan memperbarui active risk profile (`risk_percent`, `max_daily_loss`, `max_open_trade`).
  * `TradingCredentialRepository` & `TradingAccountRepository`: Menyimpan dan merotasi kredensial bursa terenkripsi.
  * `TradeRepository` & `OrderRepository`: Query dan update massal saat prosedur darurat *Emergency Panic Close*.
* **Domain Service Layer**:
  * `BotSettingService` / `BotOperationService`: Mengorkestrasi pause/resume state machine, kalkulasi status kesehatan bot, eksekusi emergency panic close (menutup seluruh posisi & membatalkan open orders), agregasi setting bot & risk profile, serta validasi live handshake REST API ke Binance.
* **Router Layer**:
  * Controller tipis yang mendelegasikan ke Service via Dependency Injection, menerapkan otorisasi RBAC (Admin-only untuk tindakan mutasi/panic), dan mengelola in-memory caching invalidation.

---

## 2. File yang Akan Dibuat & Dimodifikasi

### File Baru:
1. `backend/src/domain/exceptions/system.py`: Domain exceptions untuk operasional bot & settings (`BotOperationError`, `PanicConfirmationRequiredError`, `InvalidSettingsValueError`).
2. `backend/src/services/bot_service.py`: Domain service untuk bot operations, circuit breaker, settings, dan credentials handshake.
3. `backend/src/api/routers/bot.py`: Router FastAPI untuk `/api/v1/bot/status`, `/api/v1/bot/pause`, `/api/v1/bot/resume`, dan `/api/v1/bot/panic`.
4. `backend/src/api/routers/settings.py`: Router FastAPI untuk `/api/v1/settings` dan `/api/v1/settings/credentials`.
5. `backend/tests/api/test_bot_settings_api.py`: Test suite komprehensif untuk pengujian operasional bot dan settings.

### Modifikasi File:
1. `backend/src/schemas/system.py` & `backend/src/schemas/__init__.py`: Menambahkan schema DTO:
   * `BotStatusDTO`: (`is_running`, `is_paused`, `trading_status`, `circuit_breaker_active`, `binance_ws_connected`, `telegram_polling_active`, `scheduler_jobs_count`, `last_heartbeat`).
   * `GenericActionResponse`: (`success: bool`, `message: str`).
   * `BotSettingsDTO`: (`default_leverage`, `confidence_threshold`, `risk_percent_per_trade`, `max_daily_loss_percent`, `max_open_trades`, `is_paused`).
   * `BotSettingsUpdateRequest`: (`default_leverage: Optional[int]`, `confidence_threshold: Optional[float]`, `risk_percent_per_trade: Optional[float]`, `max_daily_loss_percent: Optional[float]`, `max_open_trades: Optional[int]`).
   * `TradingCredentialCreateRequest`: (`api_key: str`, `secret_key: str`, `environment: str = "TESTNET"`).
   * `PanicCloseResponseDTO`: (`success: bool`, `closed_trades_count: int`, `canceled_orders_count: int`, `timestamp: datetime`).
   * `CredentialSaveResponseDTO`: (`success: bool`, `account_id: int`, `credential_id: int`, `wallet_balance_usdt: float`, `environment: str`).
2. `backend/src/domain/exceptions/__init__.py`: Mengekspor domain exceptions system/bot.
3. `backend/src/services/__init__.py`: Mengekspor `BotService`.
4. `backend/src/api/deps.py`: Menambahkan dependency provider `get_bot_service()`.
5. `backend/src/api/routers/__init__.py`: Mengekspor `bot_router` dan `settings_router`.
6. `backend/src/api/app.py`: Me-mount `bot_router` dan `settings_router`.

---

## 3. Spesifikasi Rinci Endpoint & Alur Kerja Bisnis

### A. `GET /api/v1/bot/status` (Bot Runtime Status)
* **Summary**: Get real-time engine runtime status.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Alur Logika**:
  1. Ambil status `is_paused` dan `circuit_breaker_active` dari `BotSettingRepository`.
  2. Susun `BotStatusDTO`:
     * `is_running`: `True`
     * `is_paused`: boolean status
     * `trading_status`: `"PAUSED"` jika `is_paused` bernilai true, sebaliknya `"ACTIVE"`
     * `circuit_breaker_active`: boolean status
     * `binance_ws_connected`: `True`
     * `telegram_polling_active`: `True`
     * `scheduler_jobs_count`: `7`
     * `last_heartbeat`: timestamp UTC terkini
  3. Return `200 OK` dengan `BotStatusDTO`.

---

### B. `POST /api/v1/bot/pause` (Manual Pause Engine)
* **Summary**: Pause trading bot manually.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Alur Logika & Aturan Bisnis**:
  1. Set setting `is_paused = "true"` di `bot_settings`.
  2. Sinyal baru yang masuk setelah ini otomatis ditolak oleh `SignalService`.
  3. Posisi yang sedang terbuka tetap dimonitor untuk penutupan TP/SL.
  4. Invalidate cache: `await cache.invalidate("settings")` dan `await cache.invalidate("bot:status")`.
  5. Return `200 OK`: `{"success": true, "message": "Trading bot paused successfully. Incoming signals will be rejected."}`.

---

### C. `POST /api/v1/bot/resume` (Resume Engine)
* **Summary**: Resume trading bot.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Alur Logika**:
  1. Set setting `is_paused = "false"` di `bot_settings`.
  2. Reset flag `circuit_breaker_active = "false"` jika sebelumnya terpicu.
  3. Invalidate cache: `await cache.invalidate("settings")` dan `await cache.invalidate("bot:status")`.
  4. Return `200 OK`: `{"success": true, "message": "Trading bot resumed successfully. Signal ingestion active."}`.

---

### D. `POST /api/v1/bot/panic` (Emergency Panic Close All)
* **Summary**: Emergency Panic Close All.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Request Body**:
  ```json
  {
    "confirmation": true
  }
  ```
* **Alur Logika & Prosedur Keamanan Darurat**:
  1. Validasi field `confirmation`: jika `false` atau tidak disertakan, lempar `PanicConfirmationRequiredError` (HTTP 400).
  2. Cari seluruh trade yang sedang aktif (`status.in_(["OPEN", "PARTIAL", "WAITING_ENTRY"])`).
  3. Tutup seluruh trade tersebut ke status `"CLOSED"` dan catat `close_reason = "PANIC_CLOSE"`.
  4. Batalkan seluruh order pending di `OrderRepository` (`status = "CANCELED"`).
  5. Set bot ke status `is_paused = "true"`.
  6. Invalidate seluruh cache terkait (`trades`, `settings`, `analytics`, `signals`).
  7. Return `200 OK`:
     ```json
     {
       "success": true,
       "closed_trades_count": 3,
       "canceled_orders_count": 6,
       "timestamp": "2026-08-24T15:00:00Z"
     }
     ```

---

### E. `GET /api/v1/settings` (Ambil Konfigurasi Bot & Risk Profile)
* **Summary**: Get active bot settings & risk profile.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Caching**: In-memory cache key `settings:active`.
* **Alur Logika**:
  1. Periksa cache `settings:active`; jika hit kembalikan data.
  2. Ambil risk profile aktif dari `RiskProfileRepository` (`risk_percent`, `max_daily_loss`, `max_open_trade`).
  3. Ambil konfigurasi dari `BotSettingRepository` (`default_leverage`, `confidence_threshold`, `is_paused`).
  4. Petakan ke `BotSettingsDTO`.
  5. Simpan ke cache `settings:active` dan return `200 OK`.

---

### F. `PUT /api/v1/settings` (Update Konfigurasi Bot & Risk Profile)
* **Summary**: Update bot settings & risk profile.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Request Body (`BotSettingsUpdateRequest`)**:
  ```json
  {
    "default_leverage": 20,
    "confidence_threshold": 0.75,
    "risk_percent_per_trade": 2.0,
    "max_daily_loss_percent": 6.0,
    "max_open_trades": 3
  }
  ```
* **Alur Logika & Validasi**:
  1. Validasi batasan: `default_leverage` (1–125), `confidence_threshold` (0.1–1.0), `risk_percent_per_trade` (0.1–10.0), `max_daily_loss_percent` (1.0–20.0), `max_open_trades` (1–10).
  2. Update record `risk_profiles` dan `bot_settings`.
  3. Invalidate cache: `await cache.invalidate("settings")`.
  4. Return `200 OK` dengan `BotSettingsDTO` yang diperbarui.

---

### G. `POST /api/v1/settings/credentials` (Simpan Kredensial & Handshake Test)
* **Summary**: Add or rotate Binance API Key & Secret with handshake test.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Request Body (`TradingCredentialCreateRequest`)**:
  ```json
  {
    "api_key": "valid_binance_api_key_here",
    "secret_key": "valid_binance_secret_key_here",
    "environment": "TESTNET"
  }
  ```
* **Alur Logika & Handshake Real-Time**:
  1. Instansiasi `BinanceRestClient` dengan kredensial yang dikirimkan.
  2. Panggil live handshake check `binance_client.fetch_account_information()`.
  3. Jika handshake gagal (error signature/API key invalid), tangkap exception dan lempar `ExchangeAuthError` (HTTP 400 Bad Request).
  4. Jika handshake sukses:
     * Dapatkan saldo USDT terkini dari respon bursa.
     * Ambil/Buat `TradingAccount` untuk exchange Binance.
     * Simpan kredensial baru via `TradingCredentialRepository.create()` dengan flag `is_active = True` (dan deaktifkan kredensial lama jika ada).
     * Invalidate cache `settings` dan `accounts`.
  5. Return `200 OK`:
     ```json
     {
       "success": true,
       "account_id": 1,
       "credential_id": 1,
       "wallet_balance_usdt": 1000.0,
       "environment": "TESTNET"
     }
     ```

---

## 4. Matriks Pengujian Lengkap (Test Matrix)

Test suite `backend/tests/api/test_bot_settings_api.py` mencakup:

| Kategori | Nama Test | Deskripsi Skenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **Positif** | `test_get_bot_status_success` | Ambil status runtime bot. | `200 OK`, memuat `is_running=True`, `trading_status="ACTIVE"`, `last_heartbeat`. |
| **Positif** | `test_pause_and_resume_bot_lifecycle` | Eksekusi pause lalu resume engine. | `200 OK` untuk pause (`is_paused=True`), `200 OK` untuk resume (`is_paused=False`). |
| **Positif** | `test_panic_close_all_positions_and_cancel_orders` | Eksekusi emergency panic close dengan `confirmation=True`. | `200 OK`, seluruh open trade ditutup, pending order dibatalkan, bot di-pause. |
| **Positif** | `test_get_settings_success` | Ambil konfigurasi gabungan bot & risk profile. | `200 OK`, memuat `default_leverage`, `risk_percent_per_trade`, `max_daily_loss_percent`, dll. |
| **Positif** | `test_update_settings_success` | Perbarui parameter risiko dan leverage. | `200 OK`, konfigurasi terupdate dan cache diinvalidasi. |
| **Positif** | `test_credentials_handshake_success` | Input API key valid, handshake bursa berhasil, saldo live terambil. | `200 OK`, kredensial tersimpan, `wallet_balance_usdt` terisi. |
| **Negatif** | `test_panic_without_confirmation` | Panggil `/bot/panic` dengan `confirmation=False` atau payload kosong. | `400 Bad Request` (`PanicConfirmationRequiredError`). |
| **Negatif** | `test_update_settings_invalid_ranges` | Update parameter di luar batas aman (e.g. leverage = 200 atau risk = 50%). | `400 Bad Request` atau `422 Unprocessable Entity`. |
| **Negatif** | `test_credentials_handshake_failed` | Input API key/secret salah yang ditolak oleh Binance. | `400 Bad Request` (`ExchangeAuthError`). |
| **Security & Auth** | `test_bot_operations_unauthorized_rejection` | Akses GET/POST bot tanpa token JWT. | `401 Unauthorized`. |
| **Security & Auth** | `test_settings_mutation_forbidden_for_viewer` | Akses POST `/bot/pause`, `/bot/panic`, PUT `/settings`, POST `/settings/credentials` dengan token `VIEWER`. | `403 Forbidden`. |
| **Caching & Invalidation** | `test_settings_caching_and_write_through_invalidation` | Validasi caching `settings:active` dan auto-invalidation saat update. | Fresh data terpantau setelah PUT. |

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. **State Machine Efektif**: Toggle pause melalui API langsung menghentikan penerimaan sinyal baru di seluruh service.
2. **Panic Close Teruji**: Memanggil `/bot/panic` dengan konfirmasi benar-benar menutup seluruh posisi terbuka dan membatalkan seluruh order.
3. **Uji Handshake Kredensial**: Input API key yang salah ditolak dengan pesan error yang jelas; API key yang benar terhubung dan langsung menampilkan saldo bursa.
4. **Smart Settings Invalidation**: Pembaruan setting via API langsung memperbarui cache tanpa restart server.
5. **Kepatuhan OpenAPI**: Endpoint `GET /bot/status`, `POST /bot/pause`, `POST /bot/resume`, `POST /bot/panic`, `GET /settings`, `PUT /settings`, `POST /settings/credentials` 100% konsisten dengan `docs/openapi.yaml`.
6. **Mypy Static Typing**: 0 errors pada static type checking (`mypy backend/src/`).
7. **Testing**: Seluruh test di `test_bot_settings_api.py` dan seluruh test backend lulus 100%.
