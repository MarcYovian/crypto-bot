# Task 04: Telegram Signals Feed & Manual Signal Execution Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint feed sinyal Telegram terpaginasi (`GET /api/v1/signals`) dan form eksekusi sinyal manual dari web UI (`POST /api/v1/signals/manual-execute`). 

Implementasi ini secara ketat menerapkan **Domain-Driven Service-Repository Pattern** yang telah disepakati:
* **Repository Layer**: Query murni ke tabel `trading_signals` dengan filtering status dan paginasi.
* **Domain Layer**: Menggunakan `ParsedSignalDTO`, `TradeExecutionResultDTO`, serta melempar domain exceptions (`SignalParseError`, `InvalidSignalDataError`, `SymbolNotWhitelistedError`, `PairAlreadyActiveError`, `DailyRiskLimitReachedError`, `MaxRiskExceededError`).
* **Service Layer**: `SignalService` memproses feed sinyal, parsing payload manual ke format sinyal standar, dan mengorkestrasi eksekusi sinyal melalui `TradeService` (menerapkan proteksi risiko 2.0% dan eksekusi dual order MARKET/LIMIT).
* **Router Layer**: Controller tipis yang hanya memvalidasi DTO HTTP, memanggil Service via Dependency Injection, mengelola caching in-memory, dan memetakan domain exceptions ke HTTP status codes.

---

## 2. File yang Akan Dibuat & Dimodifikasi

### File Baru:
1. `backend/src/services/signal_service.py`: Domain service untuk orkestrasi feed sinyal dan eksekusi sinyal manual.
2. `backend/src/api/routers/signals.py`: Router FastAPI untuk endpoints `/api/v1/signals` dan `/api/v1/signals/manual-execute`.
3. `backend/tests/api/test_signals_api.py`: Test suite komprehensif menguji seluruh skenario positif, negatif, bisnis/risiko, keamanan, dan edge cases.

### Modifikasi File:
1. `backend/src/schemas/signal.py` & `backend/src/schemas/__init__.py`: Menambahkan schema DTO:
   * `SignalItemDTO` & `PaginatedSignalListDTO` (sesuai spesifikasi `docs/openapi.yaml`).
   * `ManualSignalExecutionRequest` (mendukung raw text sinyal atau field terstruktur: `symbol`, `side`, `entry_price`, `sl_price`, `tp_targets`, `leverage`, `auto_tp_sl`).
2. `backend/src/repository/signal_repository.py`: Menambahkan method `get_signals_paginated(page, page_size, status)`.
3. `backend/src/services/__init__.py`: Mengekspor `SignalService`.
4. `backend/src/api/deps.py`: Menambahkan dependency provider `get_signal_service()`.
5. `backend/src/api/app.py`: Me-mount `signals_router` ke aplikasi FastAPI.

---

## 3. Spesifikasi Rinci Endpoint & Alur Kerja

### A. `GET /api/v1/signals` (Feed Sinyal Telegram)
* **Summary**: List incoming Telegram signals feed.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Query Parameters**:
  * `page: int = 1` (min: 1)
  * `page_size: int = 20` (min: 1, max: 100)
  * `status: Optional[str] = None` (Filter: `RECEIVED`, `EXECUTED`, `REJECTED`, `CANCELLED`, `EXPIRED`, `PENDING`, `PROCESSED`)
* **Caching**: In-memory cache singleton dengan TTL 5 detik (`signals:feed:{account_id}:{page}:{page_size}:{status}`).
* **Alur Logika**:
  1. Periksa cache; jika ada kembalikan langsung.
  2. Panggil `SignalService.get_signals_feed()`.
  3. `SignalRepository.get_signals_paginated()` menjalankan query SQL dengan eager loading `instrument` dan `provider`.
  4. Petakan ORM entity ke `PaginatedSignalListDTO` (termasuk `trace_id`, `raw_text`, `confidence_score`, `entry_price`, `sl_price`, `tp_targets`, dan status).
  5. Simpan ke cache 5 detik lalu kembalikan response.
* **Response (200 OK)**: `PaginatedSignalListDTO`.

---

### B. `POST /api/v1/signals/manual-execute` (Eksekusi Sinyal Manual)
* **Summary**: Manually execute a trading signal with strict 2% risk budget enforcement.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Request Body (`ManualSignalExecutionRequest`)**:
  ```json
  {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "entry_price": 50000.00,
    "sl_price": 49000.00,
    "tp_targets": [51000.00, 52000.00, 53000.00],
    "leverage": 20,
    "auto_tp_sl": true
  }
  ```
* **Alur Logika & Aturan Bisnis**:
  1. Router mendelegasikan request ke `SignalService.manual_execute_signal()`.
  2. **Validasi Geometri Harga**:
     * `BUY`: `sl_price` harus `< entry_price`, seluruh `tp_targets` harus `> entry_price`.
     * `SELL`: `sl_price` harus `> entry_price`, seluruh `tp_targets` harus `< entry_price`.
     * Jika melanggar, lemparkan `InvalidSignalDataError` (diterjemahkan router menjadi `HTTP 400 Bad Request`).
  3. **Konversi ke Domain DTO**: Buat `ParsedSignalDTO` dengan `trace_id` unik (format `manual-exec-<uuid>`).
  4. **Eksekusi via `TradeService.execute_signal()`**:
     * Verifikasi instrumen terdaftar & aktif di watchlist (`SymbolNotWhitelistedError` -> HTTP 400).
     * Cek duplikasi posisi aktif pada simbol yang sama (`PairAlreadyActiveError` -> HTTP 400).
     * Cek batas maksimum open trade (`MaxRiskExceededError` -> HTTP 400).
     * Cek sisa kuota risiko harian (`DailyRiskLimitReachedError` -> HTTP 400).
     * Hitung ukuran lot posisi presisi berdasarkan risiko 2% dari saldo (`RiskCalculatorService`).
     * Tentukan tipe order entry: `MARKET` jika deviasi harga saat ini $\le 0.2\%$, atau `LIMIT` jika di luar batas.
     * Pasang order entry dan TP/SL otomatis ke Binance jika terhubung.
  5. **Invalidasi Cache**: Hapus cache feed sinyal, ringkasan dashboard, dan daftar trade aktif (`signals:feed`, `analytics:summary`, `trades:active`).
* **Response (200 OK)**: `TradeExecutionResultDTO`.
* **Response (400 Bad Request)**: Jika validasi parameter sinyal, whitelist, atau aturan risiko gagal.
* **Response (401 / 403)**: Jika token tidak ada, kedaluwarsa, atau role tidak mencukupi.

---

## 4. Matriks Pengujian Lengkap (Test Matrix)

Test suite `backend/tests/api/test_signals_api.py` akan mencakup minimal 10 test case:

| Kategori | Nama Test | Deskripsi Skenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **Positif** | `test_get_signals_feed_success` | Ambil feed sinyal halaman 1 dengan data mock di database. | `200 OK`, `PaginatedSignalListDTO` sesuai item database. |
| **Positif** | `test_get_signals_feed_filter_status` | Filter feed sinyal berdasarkan status `RECEIVED` / `EXECUTED`. | `200 OK`, hanya item dengan status tersebut yang kembali. |
| **Positif** | `test_manual_execute_signal_buy_success` | Eksekusi manual sinyal BUY yang valid dengan risiko 2%. | `200 OK`, `is_success=True`, `trade_id` terbentuk, posisi tercatat di database. |
| **Positif** | `test_manual_execute_signal_sell_success` | Eksekusi manual sinyal SELL yang valid. | `200 OK`, `is_success=True`, `side="SELL"`. |
| **Negatif** | `test_manual_execute_invalid_price_geometry_buy` | Sinyal BUY dengan `sl_price >= entry_price`. | `400 Bad Request`, pesan validasi jelas. |
| **Negatif** | `test_manual_execute_invalid_price_geometry_sell` | Sinyal SELL dengan `sl_price <= entry_price`. | `400 Bad Request`, pesan validasi jelas. |
| **Business/Risk** | `test_manual_execute_symbol_not_in_watchlist` | Eksekusi sinyal untuk simbol yang disabled atau tidak ada di watchlist. | `400 Bad Request` (`SymbolNotWhitelistedError`). |
| **Business/Risk** | `test_manual_execute_duplicate_active_pair` | Eksekusi sinyal pada pasangan yang sudah memiliki posisi OPEN. | `400 Bad Request` (`PairAlreadyActiveError`). |
| **Business/Risk** | `test_manual_execute_daily_risk_limit_reached` | Eksekusi sinyal saat sisa budget risiko harian $\le 0$. | `400 Bad Request` (`DailyRiskLimitReachedError`). |
| **Security & Auth**| `test_signals_unauthorized_rejection` | Request ke `/signals` dan `/manual-execute` tanpa token JWT atau token expired. | `401 Unauthorized`. |
| **Performance** | `test_signals_feed_caching_and_invalidation` | Validasi feed cache 5s dan auto-invalidasi saat eksekusi manual berhasil. | Cache hit terbukti dan ter-reset setelah eksekusi. |

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. **Arsitektur Murni**: Seluruh akses data sinyal melalui `SignalRepository`, kalkulasi & logika melalui `SignalService` / `TradeService`, dan router murni sebagai HTTP controller.
2. **Kepatuhan OpenAPI**: Endpoint `GET /api/v1/signals` dan `POST /api/v1/signals/manual-execute` memenuhi kontrak `docs/openapi.yaml`.
3. **Enforcement Risiko 2%**: Eksekusi manual tidak dapat menembus batas risiko 2% akun atau batasan sisa budget harian.
4. **Mypy Static Typing**: 0 errors pada static type checking (`mypy backend/src/`).
5. **Testing**: 100% test pada `test_signals_api.py` dan seluruh test suite backend lulus tanpa error.
