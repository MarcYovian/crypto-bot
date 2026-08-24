# Task 10: Trade Event & Summary Repositories Implementation (Expanded)

## 1. Deskripsi Task
Membangun repository terpisah untuk model **Audit Timeline Perdagangan** (`TradeEvent` / `trade_events` table) dan **Laporan Rekapitulasi Performa & Metrik Finansial** (`TradeSummary` / `trade_summaries` table) yang bertugas mencatat rekam jejak posisi (*position milestones*), menyajikan histori audit, serta melakukan agregasi metrik performa (Win Rate, Total Net PnL, Profit Factor, Total Fees, dan Average R:R).

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/trade_event_repository.py`](../backend/src/repository/trade_event_repository.py) *(Model: TradeEvent)*
* `[NEW]` [`backend/src/repository/trade_summary_repository.py`](../backend/src/repository/trade_summary_repository.py) *(Model: TradeSummary)*
* `[NEW]` [`backend/tests/repository/test_event_summary_repositories.py`](../backend/tests/repository/test_event_summary_repositories.py)

---

## 3. Rincian Isi Repositories

### 1. `trade_event_repository.py` (`TradeEventRepository`)
* Mewarisi `BaseRepository[TradeEvent, TradeEventCreate, BaseSchema]`.
* **Method Khusus:**
  * `async def log_event(self, trade_id: int, event_type: str, payload: Optional[Union[str, dict]] = None, created_at: Optional[datetime] = None) -> TradeEvent`:
    * Helper cepat untuk mencatat milestone audit: `ENTRY_PLACED`, `ENTRY_FILLED`, `TP1_HIT`, `TP2_HIT`, `TP3_HIT`, `SL_MOVED_TO_BEP`, `TRAILING_SL_UPDATED`, `TRADE_CLOSED`, `MANUAL_INTERVENTION`.
    * Otomatis melakukan serialisasi `json.dumps()` jika payload berupa dictionary Python.
  * `async def get_events_by_trade(self, trade_id: int) -> List[TradeEvent]`:
    * Mengambil seluruh timeline event dari suatu trade terurut kronologis (`created_at ASC, id ASC`) menggunakan index `idx_trade_events_trade_time`.
  * `async def get_latest_event_by_trade(self, trade_id: int) -> Optional[TradeEvent]`:
    * Mengambil event terakhir untuk mengecek status milestone terkini dari suatu posisi aktif.
  * `async def get_events_by_type(self, event_type: str, limit: int = 50) -> List[TradeEvent]`:
    * Mengambil daftar event berdasarkan tipe tertentu untuk keperluan monitoring sistem.

### 2. `trade_summary_repository.py` (`TradeSummaryRepository`)
* Mewarisi `BaseRepository[TradeSummary, TradeSummaryCreate, BaseSchema]`.
* **Method Khusus:**
  * `async def get_by_trade_id(self, trade_id: int) -> Optional[TradeSummary]`:
    * Mengambil data rekapitulasi performa spesifik suatu trade (`trade_id` sebagai PK).
  * `async def get_performance_summary(self, account_id: Optional[int] = None, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, Any]`:
    * Menghitung metrik performa lengkap menggunakan agregasi SQL:
      * `total_trades`: Total trade selesai.
      * `winning_trades`: Jumlah trade dengan `result == 'WIN'`.
      * `losing_trades`: Jumlah trade dengan `result == 'LOSS'`.
      * `breakeven_trades`: Jumlah trade dengan `result == 'BEP'`.
      * `win_rate`: Persentase kemenangan `(winning_trades / total_trades) * 100`.
      * `total_gross_pnl`: Akumulasi keuntungan/kerugian kotor.
      * `total_net_pnl`: Akumulasi PnL bersih setelah dikurangi komisi dan funding fee.
      * `total_commission`: Total fee komisi bursa.
      * `total_funding`: Total funding fee yang dibayar/diterima.
      * `avg_rr`: Rata-rata Risk-to-Reward ratio yang dicapai.
      * `profit_factor`: Rasio `Total Keuntungan Kotor / Total Kerugian Kotor`.
  * `async def get_best_and_worst_trade(self, account_id: Optional[int] = None) -> Dict[str, Optional[TradeSummary]]`:
    * Mengambil 1 trade paling menguntungkan (*Best Win*) dan 1 trade dengan kerugian terbesar (*Worst Loss*).
  * `async def get_recent_summaries(self, account_id: Optional[int] = None, limit: int = 20) -> List[TradeSummary]`:
    * Mengambil rekap performa trade terbaru terurut `closed_at DESC`.

---

## 4. Rincian Unit Test & Test Cases (`test_event_summary_repositories.py`)

### File Test: `backend/tests/repository/test_event_summary_repositories.py`

### Daftar Test Cases yang Diuji:
1. **`test_trade_event_log_and_order_flow`**:
   * *Aksi:* Log 3 event berurutan (`ENTRY_FILLED`, `TP1_HIT`, `SL_MOVED_TO_BEP`), query `get_events_by_trade()`.
   * *Assert:* 3 event tersimpan dan dikembalikan dengan urutan kronologis yang benar (`created_at ASC`).
2. **`test_trade_event_json_payload_and_latest_lookup`**:
   * *Aksi:* Log event dengan payload dictionary `{"price": 61000.0, "tp_level": 1}`, lalu query `get_latest_event_by_trade()`.
   * *Assert:* Event terakhir terdeteksi dan payload ter-deserialisasi dengan benar.
3. **`test_trade_summary_create_and_get_by_trade`**:
   * *Aksi:* Simpan ringkasan trade dengan net PnL +45.00 USDT, ROI 22.5%, result "WIN", close_reason "TP2".
   * *Assert:* Summary tersimpan dan terhubung ke `trade_id`.
4. **`test_performance_summary_comprehensive_metrics`**:
   * *Aksi:* Simpan 4 rekapitulasi trade:
     * Trade 1: WIN, Gross +100, Fee 2, Net +98, RR 2.0
     * Trade 2: WIN, Gross +50, Fee 1, Net +49, RR 1.0
     * Trade 3: LOSS, Gross -40, Fee 1, Net -41, RR -1.0
     * Trade 4: BEP, Gross 0, Fee 1, Net -1, RR 0.0
   * *Assert:*
     * `total_trades == 4`
     * `winning_trades == 2`, `losing_trades == 1`, `breakeven_trades == 1`
     * `win_rate == 50.0%`
     * `total_net_pnl == Decimal("105.00")`
     * `total_commission == Decimal("5.00")`
     * `profit_factor == 3.75` (150 / 40)
5. **`test_performance_summary_date_filtering`**:
   * *Aksi:* Simpan trade kemarin dan trade hari ini, panggil `get_performance_summary()` dengan filter `start_date = hari ini`.
   * *Assert:* Hanya trade hari ini yang dihitung ke dalam metrik.
6. **`test_trade_summary_best_and_worst_trades`**:
   * *Aksi:* Simpan beberapa trade dengan PnL bervariasi (+100, +20, -50, -10). Panggil `get_best_and_worst_trade()`.
   * *Assert:* Best trade teridentifikasi (+100) dan Worst trade teridentifikasi (-50).

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_event_summary_repositories.py -v
```
