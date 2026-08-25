# Task 06: Signal Providers Leaderboard & Trading Strategies Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint manajemen saluran/channel sumber sinyal Telegram (`GET & POST /api/v1/providers`), analitik performa per provider (`GET /api/v1/providers/{id}/analytics`), dan manajemen strategi alokasi Take Profit & Break-Even (`GET /api/v1/strategies` & `PUT /api/v1/strategies/{id}`).

Implementasi ini secara ketat menerapkan **Domain-Driven Service-Repository Pattern**:
* **Repository Layer**:
  * `SignalProviderRepository`: Query data provider dan agregasi performa finansial provider (`total_signals`, `executed_trades`, `win_rate`, `total_net_pnl_usdt`) dalam **1 single SQL aggregate query** (mencegah $N+1$ query problem).
  * `StrategyRepository`: Query konfigurasi strategi dan pembaruan aturan TP allocation.
* **Domain Layer**:
  * DTO: `SignalProviderDTO`, `SignalProviderCreateRequest`, `ProviderPerformanceDTO`, `StrategyDTO`, `StrategyUpdateRequest`, `TPAllocationDTO`.
  * Domain Exceptions: `ProviderNotFoundError`, `DuplicateProviderError`, `StrategyNotFoundError`, `InvalidStrategyConfigError`.
* **Service Layer**:
  * `ProviderService`: Menangani registrasi channel, validasi duplikasi nama/channel, dan kalkulasi performa statistik provider.
  * `StrategyService`: Menangani pembacaan dan pembaruan alokasi TP ratio & level proteksi BEP/Trailing.
* **Router Layer**: Controller tipis yang mendelegasikan ke Service via Dependency Injection, mengelola caching in-memory (TTL 30 detik untuk analitik provider, write-through invalidation saat create/update), serta menangani response HTTP dan domain exceptions.

---

## 2. File yang Akan Dibuat & Dimodifikasi

### File Baru:
1. `backend/src/domain/exceptions/provider.py`: Domain exceptions untuk Signal Providers & Strategies (`ProviderNotFoundError`, `DuplicateProviderError`, `StrategyNotFoundError`, `InvalidStrategyConfigError`).
2. `backend/src/services/provider_service.py`: Domain service untuk provider channel & leaderboard agregasi.
3. `backend/src/services/strategy_service.py`: Domain service untuk konfigurasi strategi trading.
4. `backend/src/api/routers/providers.py`: Router FastAPI untuk endpoints `/api/v1/providers` dan `/api/v1/providers/{id}/analytics`.
5. `backend/src/api/routers/strategies.py`: Router FastAPI untuk endpoints `/api/v1/strategies` dan `/api/v1/strategies/{id}`.
6. `backend/tests/api/test_providers_strategies_api.py`: Test suite komprehensif untuk providers & strategies.

### Modifikasi File:
1. `backend/src/schemas/master.py` & `backend/src/schemas/__init__.py`: Menambahkan schema DTO:
   * `SignalProviderDTO`: (`id`, `name`, `channel_id`, `is_active`, `confidence_weight`).
   * `SignalProviderCreateRequest`: (`name: str`, `channel_id: str`, `confidence_weight: float = 1.0`).
   * `ProviderPerformanceDTO`: (`provider_id`, `provider_name`, `total_signals`, `executed_trades`, `win_rate`, `total_net_pnl_usdt`).
   * `TPAllocationDTO`: (`tp_level: int`, `percentage: float`).
   * `StrategyDTO`: (`id`, `name`, `tp_allocations: List[TPAllocationDTO]`, `bep_trigger_level`, `trailing_trigger_level`, `is_active`).
   * `StrategyUpdateRequest`: (`tp1_percent: Optional[float]`, `tp2_percent: Optional[float]`, `tp3_percent: Optional[float]`, `bep_trigger_level: Optional[int]`, `trailing_trigger_level: Optional[int]`).
2. `backend/src/domain/exceptions/__init__.py`: Mengekspor domain exceptions provider & strategy.
3. `backend/src/repository/signal_provider_repository.py`: Menambahkan method `get_provider_performance_summary(provider_id: int)` dan `get_all_providers()`.
4. `backend/src/services/__init__.py`: Mengekspor `ProviderService` dan `StrategyService`.
5. `backend/src/api/deps.py`: Menambahkan dependency provider `get_provider_service()` dan `get_strategy_service()`.
6. `backend/src/api/routers/__init__.py`: Mengekspor `providers_router` dan `strategies_router`.
7. `backend/src/api/app.py`: Me-mount `providers_router` dan `strategies_router`.

---

## 3. Spesifikasi Rinci Endpoint & Alur Kerja

### A. `GET /api/v1/providers` (Daftar Signal Providers)
* **Summary**: List all configured signal channels.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Caching**: In-memory cache key `providers:all`.
* **Alur Logika**:
  1. Periksa cache `providers:all`; jika ada kembalikan langsung.
  2. Panggil `ProviderService.list_providers()`.
  3. `SignalProviderRepository.get_all_providers()` mengambil seluruh provider terdaftar.
  4. Petakan ke `List[SignalProviderDTO]`.
  5. Simpan ke cache `providers:all` lalu return `200 OK`.

---

### B. `POST /api/v1/providers` (Registrasi Signal Provider Baru)
* **Summary**: Add a new Telegram signal provider channel.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Request Body (`SignalProviderCreateRequest`)**:
  ```json
  {
    "name": "Crypto VIP Signals",
    "channel_id": "-100123456789",
    "confidence_weight": 1.0
  }
  ```
* **Alur Logika & Aturan Bisnis**:
  1. Validasi keunikan nama provider. Jika sudah ada, lempar `DuplicateProviderError` (HTTP 409 Conflict).
  2. Simpan record provider baru ke tabel `signal_providers` (tipe default: `TELEGRAM`).
  3. **Write-Through Invalidation**:
     * `await cache.invalidate("providers")`
  4. Kembalikan `201 Created` dengan `SignalProviderDTO`.

---

### C. `GET /api/v1/providers/{id}/analytics` (Analitik Performa Provider)
* **Summary**: Get performance metrics for a specific signal provider.
* **Path Param**: `id: int` (ID Provider).
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Caching**: In-memory cache key `providers:analytics:{id}` (**TTL 30 detik**).
* **Alur Logika & Penanganan Query (No N+1)**:
  1. Periksa cache `providers:analytics:{id}`; jika hit kembalikan data.
  2. `ProviderService.get_provider_performance(provider_id)`:
     * Cek keberadaan provider di DB. Jika tidak ditemukan, lempar `ProviderNotFoundError` (HTTP 404).
     * Panggil `SignalProviderRepository.get_provider_performance_summary(provider_id)`:
       * Mengambil total sinyal dari `trading_signals` (`total_signals`).
       * Mengambil data trade hasil eksekusi sinyal provider via SQL join ke `trades` dan `trade_summaries` (`executed_trades`, `winning_trades`, `total_net_pnl`).
       * Menghitung Win Rate: `(winning_trades / executed_trades) * 100` (atau `0.0` jika belum ada trade).
  3. Petakan ke `ProviderPerformanceDTO`:
     * `provider_id`: ID Provider.
     * `provider_name`: Nama Provider.
     * `total_signals`: Jumlah sinyal yang pernah diterima dari provider.
     * `executed_trades`: Jumlah order/trade yang dieksekusi dari sinyal tersebut.
     * `win_rate`: Rasio kemenangan trade (persentase).
     * `total_net_pnl_usdt`: Total keuntungan/kerugian bersih terealisasi dalam USDT.
  4. Simpan ke cache `providers:analytics:{id}` dengan TTL 30s dan return `200 OK`.

---

### D. `GET /api/v1/strategies` (Daftar Strategi Trading)
* **Summary**: List all trading strategies.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Caching**: In-memory cache key `strategies:all`.
* **Alur Logika**:
  1. Periksa cache `strategies:all`; jika hit kembalikan data.
  2. Panggil `StrategyService.list_strategies()`.
  3. `StrategyRepository.get_all()` mengambil seluruh data strategi.
  4. Petakan ke `List[StrategyDTO]`:
     * `id`: ID Strategi.
     * `name`: Nama Strategi.
     * `tp_allocations`: Rincian alokasi TP per level (e.g. TP1: 50%, TP2: 30%, TP3: 20%).
     * `bep_trigger_level`: Level TP yang memicu pergeseran Stop Loss ke Break-Even (default: 1).
     * `trailing_trigger_level`: Level TP yang memicu Trailing Stop Loss aktif (default: 2).
     * `is_active`: Status aktif strategi.
  5. Simpan ke cache `strategies:all` dan return `200 OK`.

---

### E. `PUT /api/v1/strategies/{id}` (Update Aturan Alokasi TP Strategi)
* **Summary**: Update strategy TP allocation ratios and trailing rules.
* **Path Param**: `id: int`.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Request Body (`StrategyUpdateRequest`)**:
  ```json
  {
    "tp1_percent": 50.0,
    "tp2_percent": 30.0,
    "tp3_percent": 20.0,
    "bep_trigger_level": 1,
    "trailing_trigger_level": 2
  }
  ```
* **Alur Logika & Validasi Bisnis**:
  1. Cari strategi berdasarkan `id`. Jika tidak ditemukan, lempar `StrategyNotFoundError` (HTTP 404).
  2. Validasi jumlah persentase TP: jika `tp1_percent + tp2_percent + tp3_percent != 100.0`, lempar `InvalidStrategyConfigError` (HTTP 400).
  3. Perbarui konfigurasi strategi di database.
  4. **Write-Through Invalidation**:
     * `await cache.invalidate("strategies")`
  5. Return `200 OK` dengan `StrategyDTO` yang terupdate.

---

## 4. Matriks Pengujian Lengkap (Test Matrix)

Test suite `backend/tests/api/test_providers_strategies_api.py` mencakup:

| Kategori | Nama Test | Deskripsi Skenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **Positif** | `test_get_providers_list_success` | Ambil seluruh daftar signal provider yang terdaftar. | `200 OK`, list item memuat `name`, `channel_id`, `confidence_weight`. |
| **Positif** | `test_create_provider_success` | Tambahkan provider sinyal Telegram baru. | `201 Created`, record baru tersimpan dan cache diinvalidasi. |
| **Positif** | `test_get_provider_analytics_success` | Hitung agregasi performa provider dengan riwayat trade (win/loss). | `200 OK`, memuat `total_signals`, `executed_trades`, `win_rate`, `total_net_pnl_usdt`. |
| **Positif** | `test_get_provider_analytics_zero_trades` | Ambil analitik provider yang belum memiliki trade tereksekusi. | `200 OK`, `win_rate=0.0`, `executed_trades=0`, `total_net_pnl_usdt=0.0`. |
| **Positif** | `test_get_strategies_list_success` | Ambil seluruh daftar strategi trading dan alokasi TP. | `200 OK`, list item memuat `tp_allocations`, `bep_trigger_level`, dll. |
| **Positif** | `test_update_strategy_success` | Perbarui rasio alokasi TP (50/30/20) dan trigger level. | `200 OK`, data terupdate dan cache diinvalidasi. |
| **Negatif** | `test_create_provider_duplicate_name` | Daftarkan provider dengan nama yang sudah ada. | `409 Conflict` (`DuplicateProviderError`). |
| **Negatif** | `test_get_provider_analytics_not_found` | Akses analitik provider dengan ID yang tidak ada. | `404 Not Found` (`ProviderNotFoundError`). |
| **Negatif** | `test_update_strategy_not_found` | Update strategi dengan ID yang tidak ada. | `404 Not Found` (`StrategyNotFoundError`). |
| **Negatif** | `test_update_strategy_invalid_tp_sum` | Update alokasi TP dengan total tidak sama dengan 100% (e.g. 50 + 30 + 10 = 90). | `400 Bad Request` (`InvalidStrategyConfigError`). |
| **Security & Auth** | `test_providers_unauthorized_rejection` | Akses GET/POST provider tanpa token JWT. | `401 Unauthorized`. |
| **Security & Auth** | `test_strategies_unauthorized_rejection` | Akses GET/PUT strategi tanpa token JWT. | `401 Unauthorized`. |
| **Security & Auth** | `test_provider_create_and_strategy_update_forbidden_for_viewer` | Akses endpoint mutasi menggunakan token `VIEWER`. | `403 Forbidden`. |
| **Caching & Invalidation** | `test_providers_cache_and_invalidation_on_create` | Uji caching `providers:all` dan auto-invalidation saat POST provider baru. | Cache miss -> cache hit -> invalidasi saat create -> fresh data. |
| **Caching & Invalidation** | `test_provider_analytics_30s_caching` | Uji caching 30 detik pada endpoint `/providers/{id}/analytics`. | Cache hit terbukti dalam interval TTL. |
| **Caching & Invalidation** | `test_strategies_cache_and_invalidation_on_update` | Uji caching `strategies:all` dan auto-invalidation saat PUT update. | Cache ter-reset saat update sukses. |

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. **Pencegahan Masalah N+1**: Endpoint analitik provider mengagregasi performa dalam **1 single SQL query** tanpa looping record per trade.
2. **Kepatuhan OpenAPI**: Endpoint `GET /providers`, `POST /providers`, `GET /providers/{id}/analytics`, `GET /strategies`, `PUT /strategies/{id}` 100% konsisten dengan `docs/openapi.yaml`.
3. **Role-Based Access Control**: Pembuatan provider dan modifikasi strategi hanya dapat dilakukan oleh role `ADMIN`, sedangkan `VIEWER` hanya memiliki izin baca (GET).
4. **Mypy Static Typing**: 0 errors pada static type checking (`mypy backend/src/`).
5. **Testing Komprehensif**: Seluruh test di `test_providers_strategies_api.py` dan seluruh suite backend lulus 100%.
