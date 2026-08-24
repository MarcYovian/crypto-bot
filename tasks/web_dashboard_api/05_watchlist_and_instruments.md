# Task 05: Watchlist & Market Instruments Management Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint pengelolaan daftar whitelist koin yang diizinkan untuk trading (`GET /api/v1/watchlist`), toggle enable/disable trading pair (`POST /api/v1/watchlist/toggle`), daftar spesifikasi instrumen Binance Futures beserta leverage tier brackets (`GET /api/v1/instruments`), dan endpoint sinkronisasi metadata bursa on-demand (`POST /api/v1/instruments/sync`).

Implementasi ini secara ketat menerapkan **Domain-Driven Service-Repository Pattern**:
* **Repository Layer**: Query murni menggunakan `selectinload` untuk eager-load relasi `Watchlist -> Instrument -> LeverageBrackets` dalam 1 batch query (mencegah $N+1$ problem).
* **Domain Layer**: Menggunakan DTO `WatchlistItemDTO`, `WatchlistToggleRequest`, `InstrumentDTO`, `SyncInstrumentsResponseDTO`, serta melempar domain exceptions (`SymbolNotWhitelistedError`, `ExchangeError`).
* **Service Layer**:
  * `WatchlistService`: Menangani query data watchlist lengkap dengan max leverage & filter presisi, serta mutasi toggle status.
  * `InstrumentService`: Menangani query seluruh instrumen bursa aktif dan sinkronisasi metadata exchange info + leverage brackets dari Binance REST API.
* **Router Layer**: Controller tipis yang mendelegasikan ke Service via Dependency Injection, mengelola caching in-memory (TTL 30 menit untuk instrumen dan write-through invalidation untuk watchlist), serta menangani response HTTP dan exceptions.

---

## 2. File yang Akan Dibuat & Dimodifikasi

### File Baru:
1. `backend/src/services/watchlist_service.py`: Domain service untuk manajemen watchlist dan kalkulasi tier leverage koin.
2. `backend/src/api/routers/watchlist.py`: Router FastAPI untuk endpoint `/api/v1/watchlist` dan `/api/v1/watchlist/toggle`.
3. `backend/src/api/routers/instruments.py`: Router FastAPI untuk endpoint `/api/v1/instruments` dan `/api/v1/instruments/sync`.
4. `backend/tests/api/test_watchlist_instruments_api.py`: Test suite komprehensif untuk watchlist & instruments.

### Modifikasi File:
1. `backend/src/schemas/master.py` & `backend/src/schemas/__init__.py`: Menambahkan schema DTO:
   * `WatchlistItemDTO`: (`id`, `symbol`, `enabled`, `max_leverage`, `tick_size`, `min_qty`).
   * `WatchlistToggleRequest`: (`symbol: str`, `enabled: bool`).
   * `InstrumentDTO`: (`symbol`, `base_asset`, `quote_asset`, `price_precision`, `qty_precision`, `tick_size`, `step_size`, `min_notional`, `max_leverage`).
   * `SyncInstrumentsResponseDTO`: (`synced_instruments: int`, `synced_brackets: int`, `timestamp: datetime`).
2. `backend/src/repository/watchlist_repository.py`: Menambahkan `get_all_watchlist_with_instruments()`.
3. `backend/src/repository/instrument_repository.py`: Menambahkan `get_all_instruments_with_brackets()`.
4. `backend/src/services/instrument_service.py`: Menambahkan method DTO-mapper `list_all_instruments()`.
5. `backend/src/services/__init__.py`: Mengekspor `WatchlistService`.
6. `backend/src/api/deps.py`: Menambahkan dependency provider `get_watchlist_service()` dan `get_instrument_service()`.
7. `backend/src/api/routers/__init__.py`: Mengekspor `watchlist_router` dan `instruments_router`.
8. `backend/src/api/app.py`: Me-mount `watchlist_router` dan `instruments_router`.

---

## 3. Spesifikasi Rinci Endpoint & Alur Kerja

### A. `GET /api/v1/watchlist` (Daftar Watchlist Trading Pairs)
* **Summary**: List all watchlist pairs with trading specifications.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Caching**: In-memory cache singleton dengan key `watchlist:all` (di-cache hingga terjadi mutasi toggle/sync).
* **Alur Logika**:
  1. Periksa cache `watchlist:all`; jika ada kembalikan langsung.
  2. Panggil `WatchlistService.get_watchlist()`.
  3. `WatchlistRepository.get_all_watchlist_with_instruments()` menjalankan query SQL dengan eager loading `Instrument` dan `InstrumentLeverageBracket`.
  4. Petakan setiap record ke `WatchlistItemDTO`:
     * `id`: ID Watchlist.
     * `symbol`: Simbol trading pair (e.g. `BTCUSDT`).
     * `enabled`: Status aktif trading (`True`/`False`).
     * `max_leverage`: Leverage maksimum dari bracket tier 1 (fallback 125 jika tidak ada bracket).
     * `tick_size`: Minimum pergerakan harga instrumen.
     * `min_qty`: Minimum lot order quantity.
  5. Simpan ke cache `watchlist:all` lalu kembalikan response `List[WatchlistItemDTO]`.

---

### B. `POST /api/v1/watchlist/toggle` (Toggle Enable/Disable Trading Pair)
* **Summary**: Enable or disable active trading for a specific symbol.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Request Body (`WatchlistToggleRequest`)**:
  ```json
  {
    "symbol": "BTCUSDT",
    "enabled": false
  }
  ```
* **Alur Logika & Aturan Bisnis**:
  1. Validasi simbol: mencari instrumen di database berdasarkan `symbol`.
  2. Jika simbol belum terdaftar di database, panggil `InstrumentService.get_or_sync_instrument(symbol)` untuk resolve on-demand dari Binance. Jika tetap tidak valid, lempar `SymbolNotWhitelistedError` (HTTP 400).
  3. Update / Insert status `enabled` pada tabel `watchlist`.
  4. **Write-Through Invalidation**:
     * `await cache.invalidate("watchlist")`
     * `await cache.invalidate("signals:feed")`
  5. Kembalikan data `WatchlistItemDTO` yang terupdate.

---

### C. `GET /api/v1/instruments` (Daftar Seluruh Instrumen Bursa & Leverage)
* **Summary**: List all synced Binance Futures instruments and specifications.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Caching**: In-memory cache singleton dengan key `instruments:all` (**TTL 30 Menit / 1800 detik**).
* **Alur Logika**:
  1. Periksa cache `instruments:all`; jika hit kembalikan data.
  2. Panggil `InstrumentService.list_all_instruments()`.
  3. `InstrumentRepository.get_all_instruments_with_brackets()` query seluruh instrumen aktif beserta leverage bracket.
  4. Petakan ke `List[InstrumentDTO]`: `symbol`, `base_asset`, `quote_asset`, `price_precision`, `qty_precision`, `tick_size`, `step_size`, `min_notional`, `max_leverage`.
  5. Simpan ke cache `instruments:all` dengan TTL 30 menit.

---

### D. `POST /api/v1/instruments/sync` (Sinkronisasi On-Demand dari Exchange)
* **Summary**: Trigger manual on-demand synchronization of exchange info & leverage brackets from Binance Futures.
* **Authentication**: Wajib Bearer JWT (`ADMIN`).
* **Alur Logika**:
  1. Panggil `InstrumentService.sync_all_instruments()`.
  2. Mengunduh exchange info & leverage brackets terbaru dari Binance REST API.
  3. Melakukan bulk upsert instrumen dan brackets ke database.
  4. **Invalidasi Cache**:
     * `await cache.invalidate("instruments")`
     * `await cache.invalidate("watchlist")`
  5. Kembalikan response:
     ```json
     {
       "synced_instruments": 245,
       "synced_brackets": 245,
       "timestamp": "2026-08-24T09:00:00Z"
     }
     ```

---

## 4. Matriks Pengujian Lengkap (Test Matrix)

Test suite `backend/tests/api/test_watchlist_instruments_api.py` mencakup:

| Kategori | Nama Test | Deskripsi Skenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **Positif** | `test_get_watchlist_success` | Ambil seluruh daftar watchlist pasangan koin. | `200 OK`, list item lengkap dengan `symbol`, `enabled`, `max_leverage`, `tick_size`, `min_qty`. |
| **Positif** | `test_toggle_watchlist_disable_and_enable` | Toggle status dari `enabled=True` menjadi `False`, lalu kembali ke `True`. | `200 OK`, status `enabled` terupdate di database & response. |
| **Positif** | `test_toggle_watchlist_new_symbol_on_demand` | Toggle simbol yang belum ada di watchlist tapi ada di bursa. | `200 OK`, instrumen otomatis didaftarkan dan diaktifkan. |
| **Positif** | `test_get_instruments_list_success` | Ambil daftar seluruh spesifikasi instrumen aktif dan leverage. | `200 OK`, list item sesuai model `InstrumentDTO`. |
| **Positif** | `test_sync_instruments_from_exchange_success` | Panggil endpoint `/instruments/sync` dengan mock Binance client. | `200 OK`, mengembalikan jumlah instrumen & brackets tersinkronisasi. |
| **Negatif** | `test_toggle_watchlist_invalid_symbol` | Toggle simbol yang tidak valid / tidak ada di bursa (e.g. `FAKESYMBOL`). | `400 Bad Request`, pesan error jelas. |
| **Negatif** | `test_toggle_watchlist_missing_parameters` | Request toggle tanpa parameter `symbol` atau `enabled`. | `422 Unprocessable Entity`. |
| **Security & Auth** | `test_watchlist_unauthorized_rejection` | Akses GET & POST watchlist tanpa token JWT. | `401 Unauthorized`. |
| **Security & Auth** | `test_instruments_unauthorized_rejection` | Akses GET & POST instruments tanpa token JWT. | `401 Unauthorized`. |
| **Caching & Invalidation** | `test_watchlist_cache_and_write_through_invalidation` | Uji hit cache watchlist dan invalidasi seketika saat toggle dilakukan. | Cache hit terbukti, dan data baru langsung terbaca setelah toggle. |
| **Caching & Invalidation** | `test_instruments_30m_caching_and_sync_invalidation` | Uji TTL 30m cache instrumen dan invalidasi saat `/instruments/sync` dipanggil. | Cache ter-reset setelah sinkronisasi. |

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. **Pencegahan Masalah N+1**: Seluruh query watchlist & instruments menggunakan eager loading `selectinload` dalam $O(1)$ batch query.
2. **Kepatuhan OpenAPI**: Endpoint `GET /watchlist`, `POST /watchlist/toggle`, `GET /instruments`, `POST /instruments/sync` 100% konsisten dengan `docs/openapi.yaml`.
3. **Mypy Static Typing**: 0 errors pada static type checking (`mypy backend/src/`).
4. **Testing Komprehensif**: Seluruh test di `test_watchlist_instruments_api.py` dan suite backend lulus 100%.
