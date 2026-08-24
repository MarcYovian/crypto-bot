# Task 05: Live Active Positions & Take Profit Milestone Tracker

## 1. Deskripsi Task
Membangun modul pemantauan posisi terbuka (*Live Active Positions*) secara real-time yang menyajikan data harga mark dinamis dengan animasi kilat harga (*price flash*), progress bar pencapaian Take Profit 3-tingkat (TP1 50%, TP2 30%, TP3 20%), kalkulasi *unrealized PnL* live, serta aksi penutupan pasar manual darurat per posisi:
1. Membangun komponen **Active Trades Table (`src/features/trades/components/ActiveTradesTable.tsx`)** yang mengonsumsi endpoint `GET /api/v1/trades/active`:
   * **Symbol & Side**: Simbol koin (misal: `BTCUSDT`) + Badge Arah (`BUY / LONG` hijau `#10B981`, `SELL / SHORT` merah `#EF4444`).
   * **Status**: Badge status posisi (`WAITING_ENTRY`, `OPEN`, `PARTIAL`).
   * **Entry Price vs Mark Price**: Menampilkan harga entry vs harga mark terkini dari exchange dengan efek animasi *uptick/downtick price flash* (hijau jika naik, merah jika turun selama 150ms).
   * **Position Size & Remaining Qty**: Ukuran volume posisi koin dan notional value USDT.
   * **Effective Leverage**: Badge leverage (misal: `20x Isolated`).
   * **Stop Loss (SL)**: Harga SL aktual dan status proteksi (`INITIAL_SL`, `BEP_SL`, `TRAILING_SL`).
   * **Unrealized Floating PnL**: Nilai nominal USDT dan ROI (%) yang diperbarui secara live.
2. Membangun komponen **Take Profit Milestone Progress Bar (`src/features/trades/components/TPMilestoneBar.tsx`)**:
   * Visualisasi 3-tahap pencapaian target profit:
     * `TP1 (50%)`: Berubah hijau neon dengan ikon centang saat `tp1_hit === true`.
     * `TP2 (30%)`: Berubah hijau neon saat `tp2_hit === true` (dan indikator SL bergeser ke Trailing SL).
     * `TP3 (20%)`: Berubah hijau neon saat `tp3_hit === true`.
3. Membangun komponen **Manual Market Close Modal (`src/features/trades/components/ManualCloseModal.tsx`)**:
   * Tombol *Close Position* pada setiap baris trade aktif (Terproteksi RBAC hanya untuk Admin).
   * Modal dialog konfirmasi cepat: Menampilkan detail simbol, volume tersisa yang akan ditutup, dan estimasi harga pasar.
   * Memanggil endpoint `POST /api/v1/trades/{id}/close` dengan payload `{"reason": "UI_MANUAL_CLOSE"}`.
   * Optimistic removal dari tabel aktif, diikuti notifikasi toast sukses dan auto-refresh riwayat transaksi.
4. Mengintegrasikan **Virtual Scrolling (`@tanstack/react-virtual`)** untuk menjaga performa rendering tabel stabil pada $60\text{ FPS}$.

---

## 2. File yang Akan Dibuat / Dimodifikasi

### API Endpoints & Types:
* `frontend/src/api/endpoints/trades.ts`: Fungsi API `getActiveTradesApi()`, `closeTradeApi(id: number, reason?: string)`.
* `frontend/src/types/trades.ts`: TypeScript interfaces (`ActiveTradeDTO`, `TPLevelDTO`, `GenericActionResponseDTO`).

### Komponen UI Posisi Aktif:
* `frontend/src/features/trades/ActiveTradesPage.tsx`: Halaman utama manajemen posisi terbuka.
* `frontend/src/features/trades/components/ActiveTradesTable.tsx`: Tabel posisi aktif dengan sticky header dan virtual scrolling.
* `frontend/src/features/trades/components/ActiveTradeRow.tsx`: Komponen baris posisi dengan price flash animation dan action button.
* `frontend/src/features/trades/components/TPMilestoneBar.tsx`: Progress bar bertingkat TP1, TP2, TP3.
* `frontend/src/features/trades/components/ManualCloseModal.tsx`: Modal konfirmasi penutupan market instan.
* `frontend/src/features/trades/components/EmptyPositionsState.tsx`: Ilustrasi empty state yang elegan jika tidak ada posisi berjalan.

### Custom Hooks & Stores:
* `frontend/src/hooks/useActiveTrades.ts`: TanStack Query hook dengan auto-invalidation dari WebSocket broker.

### Unit & Integration Tests:
* `frontend/tests/features/active_trades_table.test.tsx`: Pengujian render baris posisi, kalkulasi floating PnL, dan update milestone TP.
* `frontend/tests/features/manual_close_modal.test.tsx`: Pengujian alur konfirmasi close position dan proteksi role RBAC.

---

## 3. Rincian Endpoint API yang Diintegrasikan

### 1. `GET /api/v1/trades/active`
* **Query Parameters**: `account_id` (default: 1).
* **Response (200 OK)**:
  ```json
  [
    {
      "trade_id": 101,
      "symbol": "BTCUSDT",
      "side": "BUY",
      "status": "OPEN",
      "entry_price": 50000.00,
      "current_price": 50600.00,
      "sl_price": 49000.00,
      "position_size": 0.02,
      "remaining_qty": 0.02,
      "unrealized_pnl": 12.00,
      "unrealized_pnl_percent": 1.20,
      "leverage": 20,
      "margin_mode": "ISOLATED",
      "tp_levels": [
        {"level": 1, "price": 51000.00, "is_hit": false},
        {"level": 2, "price": 52000.00, "is_hit": false},
        {"level": 3, "price": 53000.00, "is_hit": false}
      ],
      "opened_at": "2026-08-24T13:00:00Z"
    }
  ]
  ```

### 2. `POST /api/v1/trades/{id}/close`
* **Path Parameter**: `id` (integer, Trade ID).
* **Request Body**: `{"reason": "UI_MANUAL_CLOSE"}`.
* **Response (200 OK)**: `{"success": true, "message": "Trade closed successfully."}`.
* **Response (400 Bad Request)**: `{"detail": "Trade is not in a closeable status."}`.

---

## 4. Rincian Interaksi & Animasi Real-Time

### 4.1 Price Flash Micro-Animation
* Setiap kali `current_price` diperbarui dari WebSocket atau interval polling:
  * Bandingkan dengan `prevPrice.current`.
  * Jika $\text{current} > \text{prev}$: Tambahkan class `bg-emerald-500/20 text-emerald-400` selama $150\text{ms}$.
  * Jika $\text{current} < \text{prev}$: Tambahkan class `bg-rose-500/20 text-rose-400` selama $150\text{ms}$.

### 4.2 Take Profit Milestone Hit State
* Saat event `TP_HIT` masuk:
  * Milestone `TP1 (50%)` bertransisi warna abu-abu -> hijau neon dengan animasi scale-in centang.
  * Teks Stop Loss otomatis menampilkan badge `BEP_SL` untuk menegaskan risiko modal telah dinetralisir.

---

## 5. Edge Cases & Error Handling
1. **Trade Telah Ditutup oleh Exchange saat User Menekan Tombol Close**: Jika posisi baru saja tersentuh SL di Binance sebelum tombol close diklik $\rightarrow$ Backend mengembalikan HTTP 400 (*"Trade is not in a closeable status"*), frontend menangkap error ini dan menampilkan toast info: *"Posisi telah ditutup otomatis oleh sistem"* lalu me-refresh tabel.
2. **High-Frequency Ticker Update Throttling**: Membungkus update harga mark ke dalam throttling $100\text{ms}$ agar browser tidak freeze saat ratusan tick data masuk per detik.
3. **Empty State**: Jika tidak ada trade aktif, render `EmptyPositionsState` dengan pesan: *"Tidak ada posisi aktif saat ini. Bot sedang standby menunggu sinyal valid."*

---

## 6. Kriteria Keberhasilan (Acceptance Criteria)
1. Tabel Active Trades menampilkan seluruh posisi aktif dengan kolom simbol, side badge, harga mark, leverage, SL, dan floating PnL monospaced.
2. Milestone progress bar TP1/TP2/TP3 berubah status dan warna secara instan saat target harga tercapai.
3. Klik tombol *Close Position* membuka modal konfirmasi; setelah submit, request `POST /api/v1/trades/{id}/close` dieksekusi dan posisi terhapus dari tabel aktif.
4. User dengan role `VIEWER` tidak dapat mengklik tombol *Close Position*.
5. Seluruh unit test di `frontend/tests/features/active_trades_table.test.tsx` dan `frontend/tests/features/manual_close_modal.test.tsx` lulus 100%.
