# Task 15: Trade Execution & Position Manager Services Implementation (Expanded)

## 1. Deskripsi Task
Membangun dan memodernisasi **Jantung Eksekusi & Pemantauan Perdagangan (*Core Trading Orchestrator & State Machine*)**:
* **`TradeService`**: Mengorkestrasi konversi sinyal (`ParsedSignalDTO`) menjadi order bursa live via `BinanceRestClient`, validasi kelayakan risiko, dan persistensi multi-tabel (`Trade`, `TradeRisk`, `Order`).
* **`PositionManager`**: Mesin otomasi siklus perdagangan (*Position Lifecycle State Machine*) yang mendengarkan event fill order untuk melakukan manuver defensif otomatis (**Break-Even Protection saat TP1** dan **Trailing Stop saat TP2**), kalkulasi PnL/komisi komprehensif, serta penutupan trade otomatis (`TradeSummary`).

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/domain/entities/trade.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/domain/entities/trade.py) *(Domain DTOs: OrderFillDTO, TradeExecutionResultDTO)*
* `[MODIFY]` [`backend/src/domain/entities/__init__.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/domain/entities/__init__.py)
* `[NEW]` [`backend/src/domain/exceptions/trade.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/domain/exceptions/trade.py) *(Trade Domain Exceptions)*
* `[MODIFY]` [`backend/src/domain/exceptions/__init__.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/domain/exceptions/__init__.py)
* `[MODIFY]` [`backend/src/services/trade_service.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/services/trade_service.py) *(TradeService)*
* `[MODIFY]` [`backend/src/services/position_manager.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/services/position_manager.py) *(PositionManager)*
* `[NEW]` [`backend/tests/services/test_trade_position_services.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/tests/services/test_trade_position_services.py)

---

## 3. Rincian Arsitektur & Isi Komponen

### 1. Domain Entities & Exceptions
* **`OrderFillDTO`** (`src/domain/entities/trade.py`):
  * `order_id: int`, `exchange_order_id: str`, `client_order_id: str`, `trade_id: int`, `symbol: str`, `side: str`, `purpose: str` (`ENTRY`, `STOP_LOSS`, `TAKE_PROFIT_1`, `TAKE_PROFIT_2`, `TAKE_PROFIT_3`), `fill_price: Decimal`, `fill_qty: Decimal`, `fee: Decimal`, `fee_asset: str`, `status: str`, `realized_pnl: Decimal`, `timestamp: datetime`.
* **`TradeExecutionResultDTO`** (`src/domain/entities/trade.py`):
  * `trade_id: int`, `symbol: str`, `side: str`, `status: str`, `position_size: Decimal`, `entry_price: Decimal`, `sl_order_id: Optional[str]`, `tp_order_ids: List[str]`, `is_success: bool`, `message: str`.
* **Domain Exceptions** (`src/domain/exceptions/trade.py`):
  * `TradeExecutionError`, `TradeNotFoundError`, `InvalidTradeStateError`, `PairAlreadyActiveError`, `SymbolNotWhitelistedError`, `DailyRiskLimitReachedError`.

---

### 2. `TradeService` (`src/services/trade_service.py`)
* **Injeksi Dependensi:**
  * Repositories: `InstrumentRepository`, `WatchlistRepository`, `TradingAccountRepository`, `TradeRepository`, `TradeRiskRepository`, `DailyRiskRepository`, `OrderRepository`, `ExecutionRepository`, `TradeEventRepository`.
  * Services: `RiskCalculatorService`, `PrecisionFilterService`.
  * Clients: `BinanceRestClient`, `TelegramNotifierClient`.
* **Method Khusus:**
  1. `async def execute_signal(self, signal_dto: ParsedSignalDTO, account_id: int = 1, auto_tp_sl: bool = True) -> TradeExecutionResultDTO`:
     * **Step 1**: Validasi simbol ada di database dan aktif di Watchlist (`WatchlistRepository.is_symbol_enabled`).
     * **Step 2**: Cek apakah pair tersebut sudah memiliki trade terbuka (`TradeRepository.get_active_trade_by_symbol`). Mencegah over-trading/duplikasi posisi.
     * **Step 3**: Ambil limit risiko harian (`DailyRiskRepository.get_or_create_today`).
     * **Step 4**: Ambil saldo modal wallet real-time dari Binance (`BinanceRestClient.fetch_balance`).
     * **Step 5**: Hitung lot sizing strictly 2.0% risk & alokasi TP via `RiskCalculatorService.calculate_position_size`.
     * **Step 6**: Set leverage & margin mode di Binance (`BinanceRestClient.set_leverage` & `set_margin_mode`).
     * **Step 7**: Buat record `Trade` baru di database (status `WAITING_ENTRY`), catat `TradeRisk`.
     * **Step 8**: Kirim Entry Order ke Binance (`BinanceRestClient.create_entry_order`). Simpan record `Order` (purpose `ENTRY`).
     * **Step 9**: Jika `auto_tp_sl=True` & entry market: pasang Stop Loss Order (`STOP_MARKET`) dan Take Profit Orders (`LIMIT reduceOnly=True`) di Binance, catat ke tabel `orders`.
     * **Step 10**: Catat jejak audit `TradeEvent` (`ENTRY_PLACED`).
     * **Step 11**: Kirim notifikasi Telegram (`TelegramNotifierClient.send_trade_opened_alert`).
  2. `async def close_trade_manually(self, trade_id: int, reason: str = "MANUAL_CLOSE") -> bool`:
     * Membatalkan semua sisa order di Binance.
     * Mengirim Market Order penutupan sisa kuantitas.
     * Mendelegasikan finalisasi ringkasan performa ke `PositionManager.finalize_trade_closure`.

---

### 3. `PositionManager` (`src/services/position_manager.py`)
* **Injeksi Dependensi:**
  * Repositories: `TradeRepository`, `OrderRepository`, `ExecutionRepository`, `TradeEventRepository`, `TradeSummaryRepository`, `DailyRiskRepository`.
  * Clients: `BinanceRestClient`, `TelegramNotifierClient`.
* **Method Khusus & State Transitions:**
  1. `async def handle_order_fill(self, fill: OrderFillDTO) -> None`:
     * **Case A: Order Purpose == `ENTRY`**:
       * Ubah status Trade menjadi `OPEN`.
       * Update `entry_price` dan `position_size`.
       * Simpan record `Execution`, catat event `ENTRY_FILLED`.
     * **Case B: Order Purpose == `TAKE_PROFIT_1`**:
       * Kurangi `remaining_qty` trade. Simpan record `Execution`.
       * **🛡️ BEP Manuver**: Batalkan Stop Loss lama di Binance & DB, pasang Stop Loss baru di harga `avg_entry_price` (**Break-Even**).
       * Update kolom `is_bep_active=True`, `sl_price=avg_entry_price`.
       * Catat events `TP1_HIT` dan `SL_MOVED_TO_BEP`.
       * Kirim notifikasi Telegram `send_take_profit_alert` (info BEP aktif).
     * **Case C: Order Purpose == `TAKE_PROFIT_2`**:
       * Kurangi `remaining_qty` trade. Simpan record `Execution`.
       * **📈 Trailing Manuver**: Batalkan SL lama di Binance & DB, pasang SL baru di harga `TP1`.
       * Update kolom `is_trailing_active=True`, `sl_price=tp1_price`.
       * Catat events `TP2_HIT` dan `TRAILING_SL_UPDATED`.
       * Kirim notifikasi Telegram `send_take_profit_alert` (info Trailing aktif).
     * **Case D: Order Purpose == `TAKE_PROFIT_3` / Last TP**:
       * Finalisasi penutupan trade: panggil `finalize_trade_closure(trade_id, close_reason="TP3_HIT", result="WIN")`.
     * **Case E: Order Purpose == `STOP_LOSS`**:
       * Finalisasi penutupan trade: panggil `finalize_trade_closure(trade_id, close_reason="SL_HIT")`.
  2. `async def finalize_trade_closure(self, trade_id: int, close_reason: str, manual_pnl: Optional[Decimal] = None) -> TradeSummary`:
     * Batalkan seluruh sisa order terbuka di Binance (`BinanceRestClient.cancel_all_orders`).
     * Batalkan seluruh open orders di DB (`OrderRepository.cancel_all_open_orders_for_trade`).
     * Hitung total realized PnL, total komisi fee, dan funding dari tabel `executions`.
     * Tentukan hasil performa: `WIN` (Net PnL > 0), `LOSS` (Net PnL < 0), atau `BREAKEVEN` (Net PnL == 0).
     * Buat dan simpan record `TradeSummary`.
     * Ubah status Trade menjadi `CLOSED`, update `remaining_qty=0`, `closed_at=datetime.now()`.
     * Catat event `MANUAL_CLOSE` / `SL_MOVED_TO_BEP` / `TP1_HIT`.
     * Kirim notifikasi Telegram penutupan trade dan realisasi PnL.

---

## 4. Rincian Unit Test & Test Cases (`test_trade_position_services.py`)

### File Test: `backend/tests/services/test_trade_position_services.py`

### Daftar Test Cases yang Diuji:
1. **`test_trade_service_execute_signal_full_success`**:
   * *Aksi:* Eksekusi `ParsedSignalDTO` BUY BTCUSDT.
   * *Assert:* Trade tersimpan (`WAITING_ENTRY`), order Entry/SL/TP terpasang di mock exchange dan DB, event `ENTRY_PLACED` tercatat.
2. **`test_trade_service_reject_unwhitelisted_symbol`**:
   * *Aksi:* Eksekusi simbol yang tidak ada di Watchlist / dinonaktifkan.
   * *Assert:* Melempar `SymbolNotWhitelistedError` atau `is_success == False`.
3. **`test_trade_service_reject_when_pair_already_active`**:
   * *Aksi:* Eksekusi sinyal baru pada pair yang sudah memiliki trade berstatus `OPEN`.
   * *Assert:* Melempar `PairAlreadyActiveError`.
4. **`test_position_manager_handle_entry_fill_opens_trade`**:
   * *Aksi:* Kirim `OrderFillDTO` untuk order Entry.
   * *Assert:* Trade status berubah dari `WAITING_ENTRY` ke `OPEN`, event `ENTRY_FILLED` tercatat.
5. **`test_position_manager_handle_tp1_fill_moves_sl_to_bep`**:
   * *Aksi:* Simulasikan TP1 terisi (FILLED).
   * *Assert:* SL lama dibatalkan di exchange, SL baru dipasang di harga entry (BEP), `is_bep_active == True`, event `SL_MOVED_TO_BEP` tersimpan.
6. **`test_position_manager_handle_tp2_fill_updates_trailing_sl`**:
   * *Aksi:* Simulasikan TP2 terisi (FILLED).
   * *Assert:* SL lama dibatalkan, SL baru dipasang di level harga TP1, `is_trailing_active == True`, event `TRAILING_SL_UPDATED` tersimpan.
7. **`test_position_manager_handle_sl_fill_finalizes_summary_loss`**:
   * *Aksi:* Simulasikan SL terisi (FILLED).
   * *Assert:* Semua sisa order dibatalkan, `TradeSummary` tersimpan dengan result `LOSS`, Trade status menjadi `CLOSED`.
8. **`test_trade_service_close_trade_manually`**:
   * *Aksi:* Panggil `close_trade_manually()` untuk posisi aktif.
   * *Assert:* Sisa order dibatalkan, market close dikirim, trade status `CLOSED`.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/services/test_trade_position_services.py -v
```
