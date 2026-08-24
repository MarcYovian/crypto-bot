# Task 08: Watchlist Manager & Binance Instrument Synchronizer

## 1. Deskripsi Task
Membangun modul manajemen pasangan instrumen kripto (*Watchlist Manager*) yang memungkinkan Admin mengaktifkan/menonaktifkan koin dengan switch toggle seketika (*instant write-through*), menginspeksi aturan limit exchange & tier bracket leverage, serta memicu sinkronisasi aturan instrumen langsung dari Binance Futures:
1. Membangun komponen **Watchlist Grid & Table (`src/features/watchlist/components/WatchlistGrid.tsx`)** yang mengonsumsi endpoint `GET /api/v1/watchlist`:
   * Pencarian live (*Search Bar*) untuk memfilter simbol pasangan (misal: `BTC`, `ETH`, `SOL`).
   * Switch toggle aktifasi per koin (`POST /api/v1/watchlist/toggle`) dengan *optimistic UI update* dan invalidasi cache TanStack Query seketika.
   * Kolom tabel: Simbol koin, Status Aktif (Switch), Max Leverage (misal: `125x`), Tick Size (`0.10`), Min Qty (`0.001`), dan tombol aksi inspeksi bracket.
2. Membangun komponen **Binance Instruments & Leverage Bracket Inspector (`src/features/watchlist/components/InstrumentBracketModal.tsx`)** yang mengonsumsi endpoint `GET /api/v1/instruments`:
   * Menampilkan spesifikasi presisi harga (*price precision*), presisi volume (*qty precision*), notional minimum, dan daftar tier bracket leverage Binance (Bracket level, Initial Leverage, Notional Cap USDT, Maintenance Margin Ratio).
3. Membangun komponen **Manual Exchange Sync Action (`src/features/watchlist/components/InstrumentSyncButton.tsx`)**:
   * Tombol *Sync from Binance Exchange* yang memanggil `POST /api/v1/instruments/sync` (Terproteksi RBAC Admin).
   * Menampilkan animasi putaran loading selama sinkronisasi berlangsung.
   * Menampilkan toast dialog rekap hasil sinkronisasi: *"Berhasil menyinkronkan X instrumen dan Y leverage bracket dari Binance."*

---

## 2. File yang Akan Dibuat / Dimodifikasi

### API Endpoints & Types:
* `frontend/src/api/endpoints/watchlist.ts`: Fungsi API `getWatchlistApi()`, `toggleWatchlistApi(symbol: string, enabled: boolean)`, `getInstrumentsApi()`, `syncInstrumentsApi()`.
* `frontend/src/types/watchlist.ts`: TypeScript interfaces (`WatchlistItemDTO`, `InstrumentDTO`, `LeverageBracketDTO`, `SyncInstrumentsResponseDTO`).

### Komponen UI Watchlist:
* `frontend/src/features/watchlist/WatchlistPage.tsx`: Halaman utama pengelolaan watchlist dan instrumen.
* `frontend/src/features/watchlist/components/WatchlistGrid.tsx`: Grid / tabel daftar koin whitelist dengan toggle interaktif.
* `frontend/src/features/watchlist/components/WatchlistSearchFilter.tsx`: Input search bar filter simbol live.
* `frontend/src/features/watchlist/components/InstrumentBracketModal.tsx`: Modal dialog inspeksi tier bracket leverage dan limit exchange.
* `frontend/src/features/watchlist/components/InstrumentSyncButton.tsx`: Tombol trigger sinkronisasi metadata Binance.

### Unit & Integration Tests:
* `frontend/tests/features/watchlist_grid.test.tsx`: Pengujian toggle switch status aktif, filter pencarian koin, dan penanganan optimistic UI.
* `frontend/tests/features/instrument_sync.test.tsx`: Pengujian pemanggilan endpoint sync dan tampilan loading state.

---

## 3. Rincian Endpoint API yang Diintegrasikan

### 1. `GET /api/v1/watchlist`
* **Response (200 OK)**:
  ```json
  [
    {
      "id": 1,
      "symbol": "BTCUSDT",
      "enabled": true,
      "max_leverage": 125,
      "tick_size": 0.10,
      "min_qty": 0.001
    }
  ]
  ```

### 2. `POST /api/v1/watchlist/toggle`
* **Request Body**: `{"symbol": "BTCUSDT", "enabled": false}`.
* **Response (200 OK)**: `WatchlistItemDTO` yang telah diperbarui.

### 3. `GET /api/v1/instruments`
* **Response (200 OK)**:
  ```json
  [
    {
      "symbol": "BTCUSDT",
      "base_asset": "BTC",
      "quote_asset": "USDT",
      "price_precision": 2,
      "qty_precision": 3,
      "tick_size": 0.10,
      "step_size": 0.001,
      "min_notional": 5.0,
      "max_leverage": 125,
      "brackets": [
        {
          "bracket": 1,
          "initial_leverage": 125,
          "notional_cap": 50000.0,
          "maint_margin_ratio": 0.004
        }
      ]
    }
  ]
  ```

### 4. `POST /api/v1/instruments/sync`
* **Response (200 OK)**:
  ```json
  {
    "synced_instruments": 35,
    "synced_brackets": 140,
    "timestamp": "2026-08-24T14:15:00Z"
  }
  ```

---

## 4. Edge Cases & Error Handling
1. **Menonaktifkan Koin yang Sedang Memiliki Trade Aktif**: Jika Admin menonaktifkan koin yang sedang memiliki posisi terbuka berjalan di exchange $\rightarrow$ Tampilkan modal dialog konfirmasi: *"Perhatian: Ada posisi aktif berjalan untuk simbol ini. Menonaktifkan koin tidak akan menutup posisi yang berjalan, tetapi sinyal baru akan diabaikan. Lanjutkan?"*
2. **Koneksi Binance Rate-Limited saat Sync**: Jika endpoint `/instruments/sync` mengembalikan error $\rightarrow$ Tampilkan alert toast merah: *"Gagal menyinkronkan data exchange. Binance API rate-limit atau jaringan bermasalah."*
3. **Rollback Optimistic Update**: Jika request `toggleWatchlistApi` gagal di server $\rightarrow$ Switch toggle otomatis kembali ke status awal (*rollback*) dan memunculkan toast error.

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. Seluruh simbol dalam watchlist ter-render rapi dengan status toggle switch yang akurat.
2. Mengubah switch toggle seketika mengirimkan request `POST /api/v1/watchlist/toggle` dan meng-invaliasi query cache backend.
3. Tombol *Sync from Binance Exchange* memperbarui metadata instrumen dan menampilkan toast ringkasan sinkronisasi.
4. Modal inspeksi bracket menampilkan tabel rincian tier leverage exchange Binance secara jelas.
5. Seluruh unit test di `frontend/tests/features/watchlist_grid.test.tsx` dan `frontend/tests/features/instrument_sync.test.tsx` lulus 100%.
