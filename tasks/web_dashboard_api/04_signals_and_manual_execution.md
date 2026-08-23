# Task 04: Telegram Signals Feed & Manual Signal Execution Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint feed sinyal Telegram yang terpaginasi (`/api/v1/signals`) dan form eksekusi sinyal manual dari web UI (`/api/v1/signals/manual-execute`) yang secara ketat menerapkan aturan proteksi risiko 2.0%.

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/routers/signals.py`: Router FastAPI untuk sinyal Telegram & eksekusi manual.
* `backend/tests/api/test_signals_api.py`: Test suite untuk router signals.

### Modifikasi File:
* `backend/src/api/app.py`: Menambahkan mounting `signals_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `GET /api/v1/signals`:
  * **Query Params**: `page: int = 1`, `page_size: int = 20`, `status: Optional[str]` (`PENDING`, `PROCESSED`, `REJECTED`, `EXPIRED`).
  * **Logika**: Query tabel `trading_signals` dengan pagination, mengembalikan raw text, hasil parsing, confidence score, dan `trace_id`.
  * **Response (200)**: `PaginatedSignalListDTO`.
* `POST /api/v1/signals/manual-execute`:
  * **Payload**: `ManualSignalExecutionRequest` (`symbol`, `side`, `entry_price`, `sl_price`, `tp_targets`, `leverage: Optional[int]`, `auto_tp_sl: bool`).
  * **Logika**: 
    1. Mengonversi request ke `ParsedSignalDTO` dengan trace ID unik.
    2. Menjalankan validasi logika harga (SL harus di bawah entry untuk BUY, di atas entry untuk SELL).
    3. Menjalankan `TradeService.execute_signal()` yang menghitung alokasi lot risiko 2%, mengecek watchlist & balance, lalu memasang order ke Binance.
  * **Response (200)**: `TradeExecutionResultDTO` (`is_success`, `trade_id`, `position_size`, `entry_order_id`, `sl_order_id`, `tp_order_ids`).
  * **Response (400)**: Jika validasi parameter sinyal atau aturan risiko gagal.

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Feed Sinyal Terpaginasi**: Endpoint `GET /signals` mengembalikan daftar sinyal beserta `trace_id` dan skor keyakinan (*confidence score*).
2. **Kunci Risiko 2%**: Eksekusi manual melalui `POST /manual-execute` secara ketat mengunci kerugian maksimal pada 2% dari saldo akun.
3. **Eksekusi Dual Order**: Otomatis mengeksekusi order `MARKET` jika harga saat ini berada dalam toleransi 0.2%, atau `LIMIT` jika di luar batas toleransi.
4. **Testing**: Seluruh test di `backend/tests/api/test_signals_api.py` lulus 100%.
