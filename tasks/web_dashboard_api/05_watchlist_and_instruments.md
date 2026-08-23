# Task 05: Watchlist & Market Instruments Management Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint pengelolaan daftar whitelist koin yang diizinkan untuk trading (`/api/v1/watchlist`), toggle enable/disable trading pair (`/api/v1/watchlist/toggle`), daftar metadata instrumen Binance Futures beserta leverage tier brackets (`/api/v1/instruments`), dan tombol sinkronisasi metadata bursa secara on-demand (`/api/v1/instruments/sync`).

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/routers/watchlist.py`: Router FastAPI untuk watchlist.
* `backend/src/api/routers/instruments.py`: Router FastAPI untuk instrumen dan leverage bracket.
* `backend/tests/api/test_watchlist_instruments_api.py`: Test suite untuk watchlist & instruments.

### Modifikasi File:
* `backend/src/api/app.py`: Menambahkan mounting `watchlist_router` dan `instruments_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `GET /api/v1/watchlist`:
  * **Strategi Caching**: Cache key `watchlist:all` disimpan di memory.
  * **Logika**: Query tabel `watchlists` terhubung ke `instruments` untuk mengembalikan daftar pair koin yang terdaftar beserta status `enabled`, tick size, step size, dan max leverage.
  * **Response (200)**: `List[WatchlistItemDTO]`.
* `POST /api/v1/watchlist/toggle`:
  * **Payload**: `{"symbol": "BTCUSDT", "enabled": true}`.
  * **Strategi Caching**: Memanggil `cache.invalidate("watchlist")` seketika saat toggle berubah (*write-through invalidation*).
  * **Logika**: Mengubah status `enabled` pada record `watchlists` di database. Jika pair belum ada di watchlist, menambahkannya secara otomatis.
  * **Response (200)**: `WatchlistItemDTO`.
* `GET /api/v1/instruments`:
  * **Strategi Caching**: Cache key `instruments:all` dengan **TTL 30 menit**.
  * **Logika**: Mengambil daftar seluruh instrumen bursa aktif beserta presisi harga/qty dan daftar leverage brackets dari `instrument_leverage_brackets`.
  * **Response (200)**: `List[InstrumentDTO]`.
* `POST /api/v1/instruments/sync`:
  * **Strategi Caching**: Memanggil `cache.invalidate("instruments")` dan `cache.invalidate("watchlist")` saat sinkronisasi sukses.
  * **Logika**: Memanggil `InstrumentService.sync_instruments_from_exchange()` untuk mengunduh exchange info & leverage bracket terbaru dari Binance Futures dan memperbarui database.
  * **Response (200)**: `{"synced_instruments": int, "synced_brackets": int, "timestamp": str}`.

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Toggle Watchlist & Smart Invalidation**: Perubahan status aktif/nonaktif koin melalui API langsung tersimpan di database dan meng-invalidate cache watchlist secara instan.
2. **Efisiensi Caching Instrumen**: Metadata 280+ instrumen bursa disajikan instan dari cache (< 1ms).
3. **Detail Instrumen**: Endpoint `/instruments` menampilkan informasi presisi (`tick_size`, `step_size`, `min_notional`) dan batas leverage tier bracket dengan benar.
4. **Sinkronisasi On-Demand**: Endpoint `/instruments/sync` berhasil memicu pembaruan metadata Binance, me-refresh cache, dan mengembalikan jumlah record yang berhasil disinkronisasi.
5. **Testing**: Seluruh test di `backend/tests/api/test_watchlist_instruments_api.py` lulus 100%.
