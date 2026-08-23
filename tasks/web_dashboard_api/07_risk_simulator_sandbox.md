# Task 07: Live Risk & Position Sizing Simulator Sandbox Endpoint

## 1. Deskripsi Task
Mengimplementasikan endpoint interaktif kalkulator simulasi risiko live (`POST /api/v1/calculator/simulate`) yang memungkinkan trader menguji kalkulasi ukuran lot, margin, leverage downscaling, dan harga likuidasi secara instan sebelum melakukan open posisi di pasar.

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/routers/calculator.py`: Router FastAPI untuk simulasi kalkulator risiko.
* `backend/tests/api/test_calculator_api.py`: Test suite untuk router kalkulator.

### Modifikasi File:
* `backend/src/api/app.py`: Menambahkan mounting `calculator_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `POST /api/v1/calculator/simulate`:
  * **Payload**: `RiskSimulationRequest` (`symbol`, `side`, `entry_price`, `sl_price`, `wallet_balance`, `requested_leverage: int = 20`, `risk_percent: float = 2.0`).
  * **Logika**:
    1. Mengambil metadata instrumen (`tick_size`, `step_size`, `min_notional`) dan tier leverage bracket Binance dari database.
    2. Menghitung jarak Stop Loss (`stop_distance = abs(entry_price - sl_price)`).
    3. Menghitung batas rugi absolut: `max_allowed_loss = wallet_balance * (risk_percent / 100)` (misal: $20 untuk saldo $1000).
    4. Menghitung ukuran lot pasti: `position_size = max_allowed_loss / stop_distance`, dibulatkan ke `step_size`.
    5. Menghitung margin yang dibutuhkan: `required_margin = (position_size * entry_price) / effective_leverage`.
    6. Menjalankan algoritma downscaling leverage jika notional position melebihi batas tier bracket.
    7. Menghitung estimasi harga likuidasi untuk mode margin `ISOLATED`.
    8. Memvalidasi bahwa kerugian saat menyentuh SL tidak akan pernah melampaui `max_allowed_loss`.
  * **Response (200)**: `RiskSimulationResponse` (`symbol`, `side`, `max_allowed_loss_usdt`, `calculated_position_size`, `required_margin_usdt`, `effective_leverage`, `is_leverage_downscaled`, `estimated_liquidation_price`, `projected_loss_at_sl_usdt`, `is_safe`).

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Presisi 2.0% Risk**: Untuk saldo $1000 dengan risk 2%, proyeksi kerugian saat SL selalu tepat $20.00 (atau selisih mikroskopis akibat step size).
2. **Estimasi Likuidasi Aman**: Menampilkan estimasi harga likuidasi dan memastikan harga likuidasi berada di luar level Stop Loss.
3. **Deteksi Downscaling**: Jika leverage yang diminta melebihi batas notional tier Binance, API otomatis menurunkan leverage (*downscale*) dan mengaktifkan flag `is_leverage_downscaled = true`.
4. **Testing**: Seluruh test di `backend/tests/api/test_calculator_api.py` lulus 100%.
