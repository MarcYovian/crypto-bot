# Task 14: Signal Parser & Risk Calculator Services Implementation (Expanded)

## 1. Deskripsi Task
Membangun dan memodernisasi lapisan **Business Logic Domain & Services** untuk pemrosesan sinyal mentah Telegram (`SignalParserService`), mesin kalkulasi alokasi risiko & lot sizing (`RiskCalculatorService`), serta filter presisi desimal bursa (`PrecisionFilterService`). Seluruh kalkulasi menggunakan presisi `Decimal` untuk menjamin kepatuhan aturan **Strict 2.0% Risk per Trade** dan pencegahan *slippage / floating loss* berlebih.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/domain/entities/signal.py`](../backend/src/domain/entities/signal.py) *(Domain DTOs: ParsedSignalDTO, SignalTargetDTO)*
* `[NEW]` [`backend/src/domain/entities/risk.py`](../backend/src/domain/entities/risk.py) *(Domain DTOs: RiskCalculationResultDTO, TPAllocationDTO)*
* `[NEW]` [`backend/src/domain/entities/__init__.py`](../backend/src/domain/entities/__init__.py)
* `[NEW]` [`backend/src/domain/exceptions/signal.py`](../backend/src/domain/exceptions/signal.py) *(Signal Domain Exceptions)*
* `[NEW]` [`backend/src/domain/exceptions/risk.py`](../backend/src/domain/exceptions/risk.py) *(Risk Domain Exceptions)*
* `[MODIFY]` [`backend/src/domain/exceptions/__init__.py`](../backend/src/domain/exceptions/__init__.py)
* `[NEW]` [`backend/src/services/precision_filter.py`](../backend/src/services/precision_filter.py) *(PrecisionFilterService)*
* `[MODIFY]` [`backend/src/services/signal_parser.py`](../backend/src/services/signal_parser.py) *(SignalParserService)*
* `[MODIFY]` [`backend/src/services/risk_calculator.py`](../backend/src/services/risk_calculator.py) *(RiskCalculatorService)*
* `[NEW]` [`backend/tests/services/test_signal_risk_services.py`](../backend/tests/services/test_signal_risk_services.py)

---

## 3. Rincian Arsitektur & Isi Komponen

### 1. Domain Entities & Exceptions
* **`ParsedSignalDTO`** (`src/domain/entities/signal.py`):
  * `raw_text: str`, `symbol: str`, `side: str` (`BUY`/`SELL`), `order_type: str` (`MARKET`/`LIMIT`), `entry_min: Decimal`, `entry_max: Decimal`, `entry_targets: List[Decimal]`, `sl_price: Decimal`, `tp_targets: List[Decimal]`, `leverage: Optional[int]`, `confidence_score: float`, `is_valid: bool`.
* **`RiskCalculationResultDTO`** (`src/domain/entities/risk.py`):
  * `risk_amount: Decimal`, `stop_distance: Decimal`, `position_size: Decimal`, `required_margin: Decimal`, `risk_percent: Decimal`, `risk_reward_ratios: List[Decimal]`, `tp_allocations: List[TPAllocationDTO]`, `is_valid: bool`.
* **Domain Exceptions**:
  * `SignalParseError`, `InvalidSignalDataError` (`src/domain/exceptions/signal.py`)
  * `RiskCalculationError`, `ZeroStopDistanceError`, `MaxRiskExceededError`, `InsufficientMarginRiskError` (`src/domain/exceptions/risk.py`)

---

### 2. `PrecisionFilterService` (`src/services/precision_filter.py`)
* Helper deterministik pembulatan presisi desimal tanpa floating-point imprecision:
  1. `round_price(price: Decimal, tick_size: Decimal, price_precision: int) -> Decimal`:
     * Membulatkan harga sesuai kelipatan `tick_size` dan presisi desimal.
  2. `round_quantity(qty: Decimal, step_size: Decimal, qty_precision: int, round_down: bool = True) -> Decimal`:
     * Membulatkan kuantitas lot **selalu ke bawah (floor)** untuk mencegah error *Insufficient Margin* dari exchange.
  3. `validate_min_notional(price: Decimal, qty: Decimal, min_notional: Decimal) -> bool`:
     * Memastikan `(price * qty) >= min_notional` (misal >= 5.0 USDT).
  4. `clamp_leverage(requested_leverage: int, max_leverage: int = 125, min_leverage: int = 1) -> int`:
     * Membatasi leverage dalam rentang aman instrumen.

---

### 3. `SignalParserService` (`src/services/signal_parser.py`)
* Mesin Regex adaptif multi-format:
  1. **Format Binance Killers / Crypto VIP / Universal**:
     * Ekstraksi Symbol: `#BTC/USDT`, `BTCUSDT`, `ETH-USDT.P` ➔ normalisasi ke `BTCUSDT`.
     * Ekstraksi Side: `LONG / BUY` ➔ `BUY`, `SHORT / SELL` ➔ `SELL`.
     * Ekstraksi Entry Range / Zone: `Entry: 60000 - 60500` atau `Entry: 60200`.
     * Ekstraksi Stop Loss: `SL: 59000` / `Stop: 59000`.
     * Ekstraksi Multi-TP: `TP1: 61000`, `TP2: 62000`, `TP3: 63000` ➔ `[Decimal('61000'), Decimal('62000'), Decimal('63000')]`.
     * Ekstraksi Leverage: `Leverage: Cross 20x` ➔ `20`.
  2. `parse(raw_text: str) -> ParsedSignalDTO`:
     * Parsing teks, validasi logika (misal: untuk BUY, SL harus < Entry; untuk SELL, SL harus > Entry), menghitung `confidence_score`.

---

### 4. `RiskCalculatorService` (`src/services/risk_calculator.py`)
* Kalkulasi ketat risiko modal:
  1. `calculate_position_size(wallet_balance: Decimal, risk_percent: Decimal, entry_price: Decimal, sl_price: Decimal, leverage: int, tick_size: Decimal = Decimal('0.1'), step_size: Decimal = Decimal('0.001'), price_precision: int = 2, qty_precision: int = 3, min_notional: Decimal = Decimal('5.0'), max_risk_amount: Optional[Decimal] = None) -> RiskCalculationResultDTO`:
     * `stop_distance = abs(entry_price - sl_price)`
     * `risk_amount = wallet_balance * (risk_percent / 100)`
     * `raw_qty = risk_amount / stop_distance`
     * `position_size = PrecisionFilter.round_quantity(raw_qty, step_size, qty_precision, round_down=True)`
     * `required_margin = (position_size * entry_price) / leverage`
  2. `calculate_tp_allocations(total_qty: Decimal, tp_targets: List[Decimal], entry_price: Decimal, step_size: Decimal = Decimal('0.001'), qty_precision: int = 3, ratios: Optional[List[Decimal]] = None) -> List[TPAllocationDTO]`:
     * Alokasi porsi lot parsial per level TP (Default: TP1=50%, TP2=30%, TP3=20%) dengan penyesuaian sisa lot di TP terakhir agar total lot pas 100%.

---

## 4. Rincian Unit Test & Test Cases (`test_signal_risk_services.py`)

### File Test: `backend/tests/services/test_signal_risk_services.py`

### Daftar Test Cases yang Diuji:
1. **`test_parser_various_telegram_signal_formats`**:
   * *Aksi:* Uji 5 ragam teks sinyal: Binance Killers, Fed Russian Insiders, format sederhana baris, dan format dengan emoji.
   * *Assert:* Semua field terekstraksi presisi (`symbol="BTCUSDT"`, `side="BUY"`, `sl_price`, `tp_targets`) dengan `is_valid == True`.
2. **`test_parser_invalid_signal_logical_checks`**:
   * *Aksi:* Uji sinyal BUY dengan SL di atas Entry price, atau teks acak non-sinyal.
   * *Assert:* `is_valid == False` atau melempar `InvalidSignalDataError`.
3. **`test_risk_calculator_strict_loss_guarantee`**:
   * *Aksi:* Modal 10,000 USDT, Risk 2% (200 USDT), Entry 60,000, SL 58,000 (Stop distance 2,000).
   * *Assert:* `position_size == Decimal("0.1")`, potensi kerugian tepat 200 USDT.
4. **`test_risk_calculator_zero_or_negative_distance_validation`**:
   * *Aksi:* Entry sama dengan SL (`stop_distance == 0`).
   * *Assert:* Melempar `ZeroStopDistanceError`.
5. **`test_risk_calculator_tp_allocations_and_rounding`**:
   * *Aksi:* Total lot `0.100` dibagi ke 3 TP (50%, 30%, 20%).
   * *Assert:* TP1 = 0.050, TP2 = 0.030, TP3 = 0.020 (total tepat 0.100).
6. **`test_precision_filter_lot_and_tick_floor_rounding`**:
   * *Aksi:* Uji `round_quantity(0.1239, step_size=0.001, precision=3)` dan `round_price(60000.18, tick_size=0.1, precision=1)`.
   * *Assert:* Lot dibulatkan ke bawah menjadi `0.123`, harga dibulatkan menjadi `60000.1`.
7. **`test_precision_filter_min_notional_validation`**:
   * *Aksi:* Evaluasi notional order di bawah 5 USDT vs di atas 5 USDT.
   * *Assert:* Mengembalikan `False` jika `< 5.0` dan `True` jika `>= 5.0`.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/services/test_signal_risk_services.py -v
```
