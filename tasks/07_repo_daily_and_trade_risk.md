# Task 07: Daily Risk & Trade Risk Repositories Implementation (Expanded)

## 1. Deskripsi Task
Membangun repository terpisah untuk model **Snapshot Risiko Harian** (`DailyRiskConfig`) dan **Alokasi Risiko Per-Posisi** (`TradeRisk`), dilengkapi dengan proteksi idempotensi (mencegah duplikasi data snapshot), kalkulasi akumulasi risiko aktif (*Active Exposure*), pemantauan sisa kuota budget risiko (*Remaining Risk Budget*), dan pelacakan margin terkunci.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/daily_risk_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/daily_risk_repository.py) *(Model: DailyRiskConfig)*
* `[NEW]` [`backend/src/repository/trade_risk_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/trade_risk_repository.py) *(Model: TradeRisk)*
* `[NEW]` [`backend/tests/repository/test_risk_repositories.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/tests/repository/test_risk_repositories.py)

---

## 3. Rincian Isi Repositories

### 1. `daily_risk_repository.py` (`DailyRiskRepository`)
* Mewarisi `BaseRepository[DailyRiskConfig, DailyRiskConfigCreate, BaseSchema]`.
* **Method Khusus:**
  * `async def get_by_date(self, account_id: int, snapshot_date: date) -> Optional[DailyRiskConfig]`:
    * Mengambil snapshot saldo yang dikunci pada tanggal tertentu (`YYYY-MM-DD`).
  * `async def get_latest_snapshot(self, account_id: int) -> Optional[DailyRiskConfig]`:
    * Mengambil snapshot terbaru untuk suatu akun (diurutkan `date DESC`).
  * `async def get_or_create_daily_snapshot(self, schema: DailyRiskConfigCreate) -> DailyRiskConfig`:
    * **Idempotent Snapshot**: Jika snapshot untuk `(account_id, date)` sudah ada, kembalikan record yang sudah ada; jika belum ada, buat record baru.
  * `async def get_daily_history(self, account_id: int, start_date: date, end_date: date) -> List[DailyRiskConfig]`:
    * Mengambil histori saldo harian dalam rentang tanggal tertentu (diurutkan `date ASC`) untuk charting kurva modal (*Equity Curve*).
  * `async def get_remaining_risk_budget(self, daily_risk_id: int) -> Decimal`:
    * Menghitung sisa budget risiko USDT hari ini: `DailyRiskConfig.risk_amount - SUM(TradeRisk.risk_amount)`.

### 2. `trade_risk_repository.py` (`TradeRiskRepository`)
* Mewarisi `BaseRepository[TradeRisk, TradeRiskCreate, BaseSchema]`.
* **Method Khusus:**
  * `async def get_by_trade_id(self, trade_id: int) -> Optional[TradeRisk]`:
    * Mengambil detail risiko posisi spesifik (`trade_id` sebagai PK).
  * `async def get_total_active_risk_exposure(self, account_id: int) -> Decimal`:
    * Menghitung total risiko USDT yang sedang aktif di pasar saat ini dengan join ke tabel `Trade` yang berstatus `WAITING_ENTRY`, `OPEN`, atau `PARTIAL`.
  * `async def get_total_margin_used(self, account_id: int) -> Decimal`:
    * Menghitung total USDT margin yang sedang terkunci di posisi aktif (`Trade.status.in_(['OPEN', 'PARTIAL'])`).
  * `async def get_trade_risks_by_daily_config(self, daily_risk_id: int) -> List[TradeRisk]`:
    * Mengambil seluruh record alokasi risiko trade yang terikat pada snapshot hari tertentu.

---

## 4. Rincian Unit Test & Test Cases (`test_risk_repositories.py`)

### File Test: `backend/tests/repository/test_risk_repositories.py`

### Daftar Test Cases yang Diuji:
1. **`test_daily_risk_snapshot_create_and_fetch`**:
   * *Aksi:* Buat snapshot tanggal `2026-08-14` saldo 10,000 USDT dengan budget risiko 200 USDT (2%), query via `get_by_date()`.
   * *Assert:* Snapshot ditemukan dan `risk_amount == Decimal("200.00")`.
2. **`test_daily_risk_idempotency_get_or_create`**:
   * *Aksi:* Panggil `get_or_create_daily_snapshot()` dua kali pada tanggal yang sama dengan payload berbeda.
   * *Assert:* Hanya 1 record yang tercipta di database dan record pertama dikembalikan tanpa error.
3. **`test_daily_risk_history_date_range_query`**:
   * *Aksi:* Simpan 5 snapshot harian berurutan, query rentang 3 hari via `get_daily_history()`.
   * *Assert:* Mengembalikan tepat 3 record berurutan secara kronologis.
4. **`test_trade_risk_create_and_get_by_trade_id`**:
   * *Aksi:* Simpan record `TradeRisk` dengan stop distance dan margin, query `get_by_trade_id(trade_id)`.
   * *Assert:* Field terverifikasi dengan tipe data `Decimal` presisi tinggi.
5. **`test_active_risk_exposure_calculation_with_trade_status`**:
   * *Aksi:* Buat 2 trade aktif (status `OPEN` & `WAITING_ENTRY` masing-masing risk $50) dan 1 trade `CLOSED` (risk $50).
   * *Assert:* `get_total_active_risk_exposure()` menghasilkan tepat **$100.00** (mengabaikan trade yang sudah `CLOSED`).
6. **`test_remaining_risk_budget_calculation`**:
   * *Aksi:* Budget harian $200.00, terdapat 2 trade risk masing-masing $40.00 dan $35.00 pada `daily_risk_id` tersebut.
   * *Assert:* `get_remaining_risk_budget()` mengembalikan tepat **$125.00**.
7. **`test_total_margin_used_active_trades`**:
   * *Aksi:* Buat 2 posisi `OPEN` dengan margin masing-masing $300 dan $200, serta 1 posisi `WAITING_ENTRY` margin $150.
   * *Assert:* `get_total_margin_used()` mengembalikan margin posisi yang sudah terisi di pasar (**$500.00**).

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_risk_repositories.py -v
```
