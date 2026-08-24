# Task 09: Order & Execution Repositories Implementation (Expanded)

## 1. Deskripsi Task
Membangun repository terpisah untuk model **Pesanan Bursa** (`Order` / `orders` table) dan **Riwayat Eksekusi Fill** (`Execution` / `executions` table) yang bertugas menangani pesanan exchange secara atomik, lookup berkecepatan tinggi dari event WebSocket Binance, pembatalan massal order terbuka, serta kalkulasi akumulasi Realized PnL dan fee komisi.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/order_repository.py`](../backend/src/repository/order_repository.py) *(Model: Order)*
* `[NEW]` [`backend/src/repository/execution_repository.py`](../backend/src/repository/execution_repository.py) *(Model: Execution)*
* `[NEW]` [`backend/tests/repository/test_order_execution_repositories.py`](../backend/tests/repository/test_order_execution_repositories.py)

---

## 3. Rincian Isi Repositories

### 1. `order_repository.py` (`OrderRepository`)
* Mewarisi `BaseRepository[Order, OrderCreate, OrderUpdate]`.
* **Method Khusus:**
  * `async def get_by_exchange_order_id(self, exchange_order_id: str) -> Optional[Order]`:
    * Lookup order instan saat menerima WebSocket execution report (`ORDER_TRADE_UPDATE`) dari Binance.
  * `async def get_by_client_order_id(self, client_order_id: str) -> Optional[Order]`:
    * Lookup cepat menggunakan index `idx_orders_client_id` untuk pencarian via custom client order ID bot.
  * `async def get_orders_by_trade_id(self, trade_id: int) -> List[Order]`:
    * Mengambil seluruh order yang terikat pada posisi trading tertentu (menggunakan index `idx_orders_trade_status`).
  * `async def get_open_orders_by_trade_id(self, trade_id: int) -> List[Order]`:
    * Mengambil order yang masih aktif di bursa (`status.in_(['NEW', 'PARTIALLY_FILLED'])`) untuk dievaluasi atau dibatalkan.
  * `async def get_orders_by_purpose(self, trade_id: int, purpose: str) -> List[Order]`:
    * Mengambil order berdasarkan fungsinya (`ENTRY`, `TP1`, `TP2`, `TP3`, `SL`) untuk kebutuhan modifikasi atau penggantian order SL dinamis.
  * `async def cancel_all_open_orders_for_trade(self, trade_id: int) -> int`:
    * Mengupdate secara massal seluruh order berstatus `NEW` atau `PARTIALLY_FILLED` menjadi `CANCELLED` di database saat trade ditutup. Mengembalikan jumlah baris yang diupdate.
  * `async def update_order_fill(self, exchange_order_id: str, status: str, filled_qty: Optional[Decimal] = None) -> Optional[Order]`:
    * Memperbarui status order dan kuantitas terisi secara atomik saat event WebSocket tiba.

### 2. `execution_repository.py` (`ExecutionRepository`)
* Mewarisi `BaseRepository[Execution, ExecutionCreate, BaseSchema]`.
* **Method Khusus:**
  * `async def get_executions_by_trade_id(self, trade_id: int) -> List[Execution]`:
    * Mengambil seluruh riwayat eksekusi fill pada trade terurut kronologis (`executed_at ASC`) menggunakan index `idx_executions_trade_time`.
  * `async def get_executions_by_order_id(self, order_id: int) -> List[Execution]`:
    * Mengambil riwayat eksekusi per order spesifik.
  * `async def get_total_commission_by_trade(self, trade_id: int) -> Decimal`:
    * Menghitung total biaya fee komisi yang dibayarkan ke bursa untuk seluruh eksekusi pada trade tersebut: `SUM(Execution.commission)`.
  * `async def get_total_realized_pnl_by_trade(self, trade_id: int) -> Decimal`:
    * Menghitung total keuntungan/kerugian bersih yang sudah terealisasi dari seluruh fill penutupan: `SUM(Execution.realized_pnl)`.

---

## 4. Rincian Unit Test & Test Cases (`test_order_execution_repositories.py`)

### File Test: `backend/tests/repository/test_order_execution_repositories.py`

### Daftar Test Cases yang Diuji:
1. **`test_order_create_and_fetch_by_exchange_and_client_id`**:
   * *Aksi:* Buat order dengan `exchange_order_id="bin_123"` dan `client_order_id="BOT_SL_01"`. Query via kedua method pencarian.
   * *Assert:* Order ditemukan dan atribut sesuai dengan data pembuatan.
2. **`test_order_get_by_purpose`**:
   * *Aksi:* Buat 1 order `ENTRY`, 2 order `TP1`, dan 1 order `SL` pada suatu trade. Query `get_orders_by_purpose(trade_id, "SL")`.
   * *Assert:* Mengembalikan tepat 1 order ber-purpose `SL`.
3. **`test_order_cancel_all_open_orders_for_trade`**:
   * *Aksi:* Buat 1 order `FILLED` (ENTRY), 1 order `NEW` (TP1), dan 1 order `NEW` (SL). Panggil `cancel_all_open_orders_for_trade(trade_id)`.
   * *Assert:* Mengembalikan 2 (jumlah order yang dibatalkan). Status kedua order `NEW` berubah menjadi `CANCELLED`, sedangkan order `FILLED` tetap `FILLED`.
4. **`test_order_update_fill_event`**:
   * *Aksi:* Update order dari `NEW` ke `FILLED` dengan `filled_qty = Decimal("0.1")` via `update_order_fill()`.
   * *Assert:* Status dan `filled_qty` terupdate dengan benar di database.
5. **`test_execution_record_and_total_commission_calc`**:
   * *Aksi:* Catat 2 eksekusi fill dengan fee komisi masing-masing `0.50 USDT` dan `0.70 USDT`. Panggil `get_total_commission_by_trade()`.
   * *Assert:* Mengembalikan tepat **`Decimal("1.20")`**.
6. **`test_execution_total_realized_pnl_calculation`**:
   * *Aksi:* Catat 2 eksekusi take-profit dengan `realized_pnl = +25.50` dan `+35.00`. Panggil `get_total_realized_pnl_by_trade()`.
   * *Assert:* Mengembalikan total Realized PnL tepat **`Decimal("60.50")`**.
7. **`test_execution_chronological_ordering`**:
   * *Aksi:* Catat 3 eksekusi fill dengan timestamp berbeda, query via `get_executions_by_trade_id()`.
   * *Assert:* Mengembalikan 3 eksekusi yang terurut kronologis (`executed_at ASC`).

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_order_execution_repositories.py -v
```
