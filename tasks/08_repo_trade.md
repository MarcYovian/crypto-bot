# Task 08: Trade Repository Implementation (Expanded)

## 1. Deskripsi Task
Membangun `TradeRepository` khusus untuk entitas inti posisi perdagangan (`Trade` / `trades` table) yang bertindak sebagai pusat pengelolaan siklus hidup perdagangan (*Trade Lifecycle State Machine*), mendukung **Async Eager-Loading (`selectinload`)** untuk query detail relasi posisi, serta query berkecepatan tinggi memanfaatkan composite indexes yang telah dioptimalkan.

---

## 2. File yang Dibuat / Diubah
* `[MODIFY]` [`backend/src/repository/trade_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/trade_repository.py) *(Model: Trade)*
* `[NEW]` [`backend/tests/repository/test_trade_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/tests/repository/test_trade_repository.py)

---

## 3. Rincian Isi `trade_repository.py`

### Kelas `TradeRepository`
```python
class TradeRepository(BaseRepository[Trade, TradeCreate, TradeUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(Trade, session)
```

### Method Khusus:
1. `async def get_detail(self, trade_id: int) -> Optional[Trade]`:
   * Menggunakan `options(selectinload(Trade.trade_risk), selectinload(Trade.orders), selectinload(Trade.executions), selectinload(Trade.events), selectinload(Trade.summary))` untuk memuat seluruh 5 relasi anak dalam 1 query bersih tanpa memicu *DetachedInstanceError*.
2. `async def get_active_trade_by_instrument(self, instrument_id: int) -> Optional[Trade]`:
   * Menggunakan index `idx_trades_instrument_status` untuk mencari trade yang sedang berjalan (`WAITING_ENTRY`, `OPEN`, `PARTIAL`) pada instrumen tertentu (mencegah duplikasi posisi).
3. `async def count_active_trades(self, account_id: int) -> int`:
   * Menghitung jumlah posisi yang sedang aktif pada akun untuk validasi aturan `RiskProfile.max_open_trade`.
4. `async def get_all_active_trades(self, account_id: Optional[int] = None) -> List[Trade]`:
   * Menggunakan index `idx_trades_account_status` untuk mengambil seluruh trade aktif (`WAITING_ENTRY`, `OPEN`, `PARTIAL`).
5. `async def get_active_trades_with_instrument(self, account_id: Optional[int] = None) -> List[Trade]`:
   * Mengambil seluruh trade aktif dengan eager load relasi `Trade.instrument` (metadata presisi dan simbol) untuk pemantauan WebSocket.
6. `async def get_expired_waiting_trades(self, max_hours: int = 4) -> List[Trade]`:
   * Menggunakan index `idx_trades_status_created_at` untuk mencari trade `WAITING_ENTRY` yang menggantung lebih dari `max_hours` jam agar dibatalkan oleh cron job.
7. `async def update_entry_fill(self, trade_id: int, entry_price: Decimal, avg_entry_price: Optional[Decimal] = None, opened_at: Optional[datetime] = None) -> Optional[Trade]`:
   * Mencatat harga entry aktual saat order entry terisi di bursa, mengubah status menjadi `OPEN`, dan mengisi timestamp `opened_at`.
8. `async def update_sl_price(self, trade_id: int, new_sl_price: Decimal) -> Optional[Trade]`:
   * Memperbarui harga Stop Loss di database saat posisi digeser ke **Break-Even Point (BEP)** atau **Trailing Stop**.
9. `async def reduce_position_qty(self, trade_id: int, closed_qty: Decimal, is_closed: bool = False) -> Optional[Trade]`:
   * Mengurangi `remaining_qty` saat partial TP dieksekusi. Jika `remaining_qty <= 0` atau `is_closed=True`, otomatis mengubah status menjadi `CLOSED` dan mengisi `closed_at`.
10. `async def update_trade_status(self, trade_id: int, schema: TradeStatusUpdate) -> Optional[Trade]`:
    * Mengupdate status posisi (`WAITING_ENTRY`, `OPEN`, `PARTIAL`, `CLOSED`, `CANCELLED`) beserta timestamp terkait.
11. `async def get_closed_trades_history(self, account_id: int, skip: int = 0, limit: int = 50, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[Trade]`:
    * Mengambil histori trade yang sudah `CLOSED` atau `CANCELLED` dengan pagination dan filter rentang tanggal, diurutkan `closed_at DESC`.

---

## 4. Rincian Unit Test & Test Cases (`test_trade_repository.py`)

### File Test: `backend/tests/repository/test_trade_repository.py`

### Daftar Test Cases yang Diuji:
1. **`test_trade_create_and_active_lookup`**:
   * *Aksi:* Buat trade status `WAITING_ENTRY` pada BTCUSDT, panggil `get_active_trade_by_instrument(instrument_id)`.
   * *Assert:* Trade ditemukan dan terdeteksi sebagai posisi aktif.
2. **`test_trade_active_trade_count_per_account`**:
   * *Aksi:* Buat 2 trade status `OPEN`, 1 trade `WAITING_ENTRY`, dan 1 trade `CLOSED`.
   * *Assert:* `count_active_trades()` mengembalikan tepat **3** (mengabaikan trade `CLOSED`).
3. **`test_trade_entry_fill_update_avg_price`**:
   * *Aksi:* Panggil `update_entry_fill(trade_id, entry_price=60050.0, avg_entry_price=60050.0)`.
   * *Assert:* Status trade berubah menjadi `OPEN`, `entry_price` terisi, dan `opened_at` tercatat.
4. **`test_trade_sl_price_update_bep_and_trailing`**:
   * *Aksi:* Panggil `update_sl_price(trade_id, new_sl_price=60050.0)` (geser ke BEP), lalu update lagi ke `61000.0` (trailing stop).
   * *Assert:* `sl_price` terupdate di database secara presisi.
5. **`test_trade_partial_qty_reduction_and_auto_close`**:
   * *Aksi:* Trade dengan size `0.10`, panggil `reduce_position_qty(closed_qty=0.05)` ➔ status `PARTIAL`. Panggil lagi `reduce_position_qty(closed_qty=0.05)` ➔ status `CLOSED`.
   * *Assert:* `remaining_qty` menjadi 0.0, status otomatis `CLOSED`, dan `closed_at` terisi.
6. **`test_trade_eager_load_all_children`**:
   * *Aksi:* Buat 1 Trade dengan anak TradeRisk, 2 Orders, 1 Execution, 1 Event, dan 1 Summary. Panggil `get_detail(trade_id)`.
   * *Assert:* Seluruh anak relasi dapat diakses langsung tanpa error async session / detached session.
7. **`test_trade_expired_waiting_filter`**:
   * *Aksi:* Buat 1 trade `WAITING_ENTRY` dengan `created_at` 5 jam lalu. Panggil `get_expired_waiting_trades(max_hours=4)`.
   * *Assert:* Trade kadaluwarsa terdeteksi oleh query.
8. **`test_trade_closed_history_pagination_and_date_filter`**:
   * *Aksi:* Buat 5 trade tertutup dalam rentang hari berbeda, query via `get_closed_trades_history(skip=1, limit=2)`.
   * *Assert:* Mengembalikan 2 trade terurut `closed_at DESC`.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_trade_repository.py -v
```
