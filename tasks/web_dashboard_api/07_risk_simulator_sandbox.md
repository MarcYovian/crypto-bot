# Task 07: Live Risk & Position Sizing Simulator Sandbox Endpoint

## 1. Deskripsi Task
Mengimplementasikan endpoint simulasi dan kalkulator risiko live interaktif (`POST /api/v1/calculator/simulate`) yang memungkinkan trader atau dashboard UI menguji perhitungan ukuran lot (*position sizing*), kebutuhan margin (*required margin*), deteksi *leverage downscaling*, estimasi harga likuidasi (*liquidation price*), dan pembuktian batas risiko kerugian ketat 2.0% (*strict 2% risk cap*) secara instan sebelum melakukan open posisi di pasar sesungguhnya.

Implementasi ini secara ketat menerapkan **Domain-Driven Service-Repository Pattern**:
* **Domain Layer**:
  * DTO: `RiskSimulationRequest`, `RiskSimulationResponse`.
  * Domain Exceptions: `ZeroStopDistanceError`, `MaxRiskExceededError`, `InsufficientMarginRiskError`, `InvalidSignalGeometryError`.
* **Repository Layer**:
  * `InstrumentRepository`: Mengambil metadata presisi instrumen (`tick_size`, `step_size`, `min_notional`, `qty_precision`, `price_precision`) dan tier leverage bracket Binance via `selectinload(Instrument.leverage_brackets)` (**0 N+1 issues**).
* **Domain Service Layer**:
  * `RiskCalculatorService`: Mengeksekusi formula sizing matematis, penyesuaian tier notional bracket, perhitungan harga likuidasi ISOLATED margin, dan validasi safety buffer SL vs Liq Price.
* **Router Layer**:
  * Controller tipis yang mendelegasikan ke `RiskCalculatorService` via Dependency Injection, memvalidasi payload Pydantic, dan mengembalikan response terstruktur.

---

## 2. File yang Akan Dibuat & Dimodifikasi

### File Baru:
1. `backend/src/api/routers/calculator.py`: Router FastAPI untuk endpoint `/api/v1/calculator/simulate`.
2. `backend/tests/api/test_calculator_api.py`: Test suite komprehensif untuk pengujian kalkulator simulasi risiko.

### Modifikasi File:
1. `backend/src/schemas/risk.py` & `backend/src/schemas/__init__.py`: Menambahkan schema:
   * `RiskSimulationRequest`: (`symbol: str`, `side: str`, `entry_price: float`, `sl_price: float`, `wallet_balance: float`, `requested_leverage: int = 20`, `risk_percent: float = 2.0`).
   * `RiskSimulationResponse`: (`symbol: str`, `side: str`, `max_allowed_loss_usdt: float`, `calculated_position_size: float`, `required_margin_usdt: float`, `effective_leverage: int`, `is_leverage_downscaled: bool`, `estimated_liquidation_price: float`, `stop_distance_usdt: float`, `projected_loss_at_sl_usdt: float`, `is_safe: bool`).
2. `backend/src/services/risk_calculator.py`: Menambahkan method `simulate_risk_position()` untuk simulasi komprehensif sandbox.
3. `backend/src/api/deps.py`: Menambahkan dependency provider `get_risk_calculator_service()`.
4. `backend/src/api/routers/__init__.py`: Mengekspor `calculator_router`.
5. `backend/src/api/app.py`: Me-mount `calculator_router`.

---

## 3. Rumus Matematis & Logika Eksekusi

### A. Alur Kalkulasi Matematis

1. **Jarak Stop Loss & Validasi Geometri**:
   $$\text{Stop Distance} = |\text{Entry Price} - \text{SL Price}|$$
   * Untuk `BUY` (Long): Wajib $\text{SL Price} < \text{Entry Price}$.
   * Untuk `SELL` (Short): Wajib $\text{SL Price} > \text{Entry Price}$.
   * Jika $\text{Stop Distance} \le 0$, lempar `ZeroStopDistanceError` (HTTP 400).

2. **Batas Risiko Kerugian Maksimal (Strict Risk Cap)**:
   $$\text{Max Allowed Loss} = \text{Wallet Balance} \times \left(\frac{\text{Risk Percent}}{100}\right)$$
   *(Contoh: Saldo \$1,000 dengan risk 2.0% $\rightarrow$ batas rugi maksimal tepat \$20.00)*

3. **Ukuran Lot Presisi (*Position Sizing*)**:
   $$\text{Raw Quantity} = \frac{\text{Max Allowed Loss}}{\text{Stop Distance}}$$
   $$\text{Position Size} = \text{PrecisionFilter.round\_quantity}(\text{Raw Quantity}, \text{step\_size}, \text{qty\_precision}, \text{round\_down}=\text{True})$$

4. **Nilai Nosional & Penyesuaian Tier Bracket (*Leverage Downscaling*)**:
   $$\text{Notional Value} = \text{Position Size} \times \text{Entry Price}$$
   * Cocokkan $\text{Notional Value}$ dengan tier bracket Binance (`notional_floor` $\le \text{Notional Value} \le$ `notional_cap`) untuk memperoleh `bracket_max_leverage` dan `MMR` (*Maintenance Margin Ratio*).
   * Hitung *Max Safe Leverage* untuk mencegah likuidasi dini di mode ISOLATED:
     $$\text{SL Distance \%} = \frac{\text{Stop Distance}}{\text{Entry Price}}$$
     $$\text{Max Safe Leverage} = \left\lfloor \frac{1}{\text{SL Distance \%} + \text{MMR}} \right\rfloor$$
     $$\text{Effective Leverage} = \min(\text{Requested Leverage}, \text{Max Safe Leverage}, \text{Bracket Max Leverage})$$
     $$\text{is\_leverage\_downscaled} = (\text{Effective Leverage} < \text{Requested Leverage})$$

5. **Kebutuhan Margin (*Required Margin*)**:
   $$\text{Required Margin} = \frac{\text{Notional Value}}{\text{Effective Leverage}}$$

6. **Estimasi Harga Likuidasi (*Isolated Margin Liquidation Price*)**:
   * **BUY / Long**:
     $$\text{Liq Price} = \text{Entry Price} \times \left(1 - \frac{1}{\text{Effective Leverage}} + \text{MMR}\right)$$
   * **SELL / Short**:
     $$\text{Liq Price} = \text{Entry Price} \times \left(1 + \frac{1}{\text{Effective Leverage}} - \text{MMR}\right)$$

7. **Proyeksi Kerugian Bersih pada Stop Loss**:
   $$\text{Projected Loss} = \text{Position Size} \times \text{Stop Distance}$$
   *(Terjamin $\le \text{Max Allowed Loss}$)*

8. **Indikator Keamanan Setup (`is_safe`)**:
   Posisi dinyatakan aman (`is_safe = true`) jika:
   * **BUY**: $\text{Liq Price} < \text{SL Price}$ (Stop Loss berada di atas harga likuidasi sehingga posisi ter-cut loss sebelum likuidasi).
   * **SELL**: $\text{Liq Price} > \text{SL Price}$ (Stop Loss berada di bawah harga likuidasi).
   * $\text{Required Margin} \le \text{Wallet Balance}$.
   * $\text{Notional Value} \ge \text{Min Notional}$.

---

## 4. Spesifikasi Endpoint

### `POST /api/v1/calculator/simulate`
* **Summary**: Live Risk & Position Sizing Simulator Sandbox.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Request Body (`RiskSimulationRequest`)**:
  ```json
  {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "entry_price": 50000.0,
    "sl_price": 49000.0,
    "wallet_balance": 1000.0,
    "requested_leverage": 20,
    "risk_percent": 2.0
  }
  ```
* **Response Body (`RiskSimulationResponse`, 200 OK)**:
  ```json
  {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "max_allowed_loss_usdt": 20.0,
    "calculated_position_size": 0.02,
    "required_margin_usdt": 50.0,
    "effective_leverage": 20,
    "is_leverage_downscaled": false,
    "estimated_liquidation_price": 48250.0,
    "stop_distance_usdt": 1000.0,
    "projected_loss_at_sl_usdt": 20.0,
    "is_safe": true
  }
  ```

---

## 5. Matriks Pengujian Lengkap (Test Matrix)

Test suite `backend/tests/api/test_calculator_api.py` mencakup:

| Kategori | Nama Test | Deskripsi Skenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **Positif** | `test_simulate_risk_buy_position_success` | Simulasi posisi BUY normal BTCUSDT ($50k entry, $49k SL, $1000 balance, risk 2%). | `200 OK`, `max_allowed_loss=20.0`, `position_size=0.02`, `margin=50.0`, `is_safe=True`. |
| **Positif** | `test_simulate_risk_sell_position_success` | Simulasi posisi SELL normal ETHUSDT ($3000 entry, $3100 SL, $2000 balance, risk 2%). | `200 OK`, `max_allowed_loss=40.0`, `projected_loss <= 40.0`, `is_safe=True`. |
| **Positif** | `test_simulate_risk_leverage_downscaling_bracket` | Simulasi dengan leverage 50x pada posisi yang memiliki batas aman 20x. | `200 OK`, `effective_leverage=20`, `is_leverage_downscaled=True`. |
| **Positif** | `test_simulate_risk_custom_risk_percent` | Simulasi dengan risk 1.0% atau 3.0%. | `200 OK`, `max_allowed_loss` terhitung proporsional. |
| **Negatif & Edge** | `test_simulate_risk_zero_stop_distance` | Entry price sama dengan SL price ($50,000 vs $50,000). | `400 Bad Request` (`ZeroStopDistanceError`). |
| **Negatif & Edge** | `test_simulate_risk_invalid_geometry_buy` | Posisi BUY tetapi SL lebih tinggi dari Entry ($50,000 vs $51,000). | `400 Bad Request` (`InvalidSignalGeometryError`). |
| **Negatif & Edge** | `test_simulate_risk_invalid_geometry_sell` | Posisi SELL tetapi SL lebih rendah dari Entry ($3,000 vs $2,900). | `400 Bad Request` (`InvalidSignalGeometryError`). |
| **Negatif & Edge** | `test_simulate_risk_insufficient_margin_unsafe` | Saldo terlalu kecil untuk membuka minimum notional sehingga margin melampaui saldo. | `200 OK`, `is_safe=False` (peringatan margin tidak cukup). |
| **Negatif & Edge** | `test_simulate_risk_negative_or_zero_balance` | Saldo wallet $\le 0$. | `422 Unprocessable Entity` atau `400 Bad Request`. |
| **Security & Auth** | `test_calculator_unauthorized_rejection` | Request tanpa token Bearer JWT. | `401 Unauthorized`. |
| **Security & Auth** | `test_calculator_accessible_by_viewer_and_admin` | Request menggunakan token `VIEWER` dan `ADMIN`. | Keduanya berhasil `200 OK` (simulasi dapat diakses semua pengguna terautentikasi). |

---

## 6. Kriteria Keberhasilan (Acceptance Criteria)
1. **Presisi 2.0% Risk**: Untuk saldo \$1,000 dengan risk 2.0%, proyeksi kerugian saat SL selalu tepat \$20.00 (atau selisih mikroskopis akibat lot `step_size`).
2. **Estimasi Likuidasi Aman**: Menampilkan estimasi harga likuidasi dan memverifikasi flag `is_safe` secara akurat berdasarkan relasi SL vs Liq Price.
3. **Deteksi Downscaling**: Jika leverage yang diminta melebihi batas notional tier Binance atau batas aman jarak SL, API otomatis menurunkan leverage (*downscale*) dan mengaktifkan flag `is_leverage_downscaled = true`.
4. **Kepatuhan OpenAPI**: Endpoint `POST /api/v1/calculator/simulate` 100% konsisten dengan `docs/openapi.yaml`.
5. **Mypy Static Typing**: 0 errors pada static type checking (`mypy backend/src/`).
6. **Testing**: Seluruh test di `test_calculator_api.py` dan seluruh test backend lulus 100%.
