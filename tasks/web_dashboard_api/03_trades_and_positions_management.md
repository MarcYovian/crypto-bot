# Task 03: Trades & Live Positions Management Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint pemantauan posisi aktif secara *real-time* (`/api/v1/trades/active`), daftar riwayat transaksi terpaginasi dengan filter (`/api/v1/trades/history`), detail mendalam 1 trade dengan 5 relasi anak (`/api/v1/trades/{id}`), dan tombol darurat/manual untuk menutup posisi tertentu via Market Order (`POST /api/v1/trades/{id}/close`).

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/routers/trades.py`: Router FastAPI untuk manajemen trades.
* `backend/tests/api/test_trades_api.py`: Test suite untuk endpoint trades.

### Modifikasi File:
* `backend/src/api/app.py`: Menambahkan mounting `trades_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `GET /api/v1/trades/active`:
  * **Query Params**: `account_id: int = 1`.
  * **Logika**: Mengambil trade dengan status `OPEN`, `PARTIAL`, atau `WAITING_ENTRY`. Mengambil harga live koin dari Binance Ticker untuk menghitung *Unrealized PnL* dan *Unrealized ROI %* secara real-time. Memetakan level-level TP beserta status tersentuh/tidaknya.
  * **Response (200)**: `List[ActiveTradeDTO]`.
* `GET /api/v1/trades/history`:
  * **Query Params**: `page: int = 1`, `page_size: int = 20`, `symbol: Optional[str]`, `result: Optional[str]`, `start_date: Optional[date]`, `end_date: Optional[date]`.
  * **Logika**: Query tabel `trades` berstatus `CLOSED` / `CANCELLED` dengan relasi `trade_summaries`.
  * **Response (200)**: `PaginatedTradeHistoryDTO` (`total`, `page`, `page_size`, `items`).
* `GET /api/v1/trades/{id}`:
  * **Path Param**: `id: int`.
  * **Logika**: Query trade lengkap dengan 5 entitas relasi: `trade_risk`, `orders`, `executions`, `trade_events`, dan `trade_summary`.
  * **Response (200)**: `TradeDetailDTO` atau `404 Not Found`.
* `POST /api/v1/trades/{id}/close`:
  * **Path Param**: `id: int`.
  * **Payload**: `{"reason": "UI_MANUAL_CLOSE"}`.
  * **Logika**: Memanggil `PositionManager.close_position_market(trade_id, reason)` yang mengirim order `MARKET` Reduce-Only ke Binance dan menutup trade di database.
  * **Response (200)**: `GenericActionResponse`.

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Posisi Aktif**: Endpoint `/active` menampilkan seluruh posisi terbuka beserta Unrealized PnL yang akurat.
2. **Paginasi & Filter**: Endpoint `/history` mendukung pagination dan filter `result` (`WIN`/`LOSS`) dan rentang tanggal dengan benar.
3. **Pohon Relasi Lengkap**: Endpoint `/{id}` mengembalikan data terpadu dari orders, executions, events, risk, dan summary.
4. **Manual Close**: Endpoint `/{id}/close` berhasil memicu `close_position_market` dan merubah status trade menjadi `CLOSED`.
5. **Testing**: Seluruh test di `backend/tests/api/test_trades_api.py` lulus 100%.
