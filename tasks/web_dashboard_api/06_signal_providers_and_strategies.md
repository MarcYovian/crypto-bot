# Task 06: Signal Providers Leaderboard & Trading Strategies Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint manajemen channel Telegram sumber sinyal (`/api/v1/providers`), leaderboard analitik performa per provider (`/api/v1/providers/{id}/analytics`), dan manajemen strategi alokasi Take Profit (`/api/v1/strategies`).

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/routers/providers.py`: Router FastAPI untuk signal providers & leaderboard performa.
* `backend/src/api/routers/strategies.py`: Router FastAPI untuk strategi trading.
* `backend/tests/api/test_providers_strategies_api.py`: Test suite untuk providers dan strategies.

### Modifikasi File:
* `backend/src/api/app.py`: Menambahkan mounting `providers_router` dan `strategies_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `GET /api/v1/providers`:
  * **Logika**: Mengambil daftar seluruh provider yang terdaftar di tabel `signal_providers` (`id`, `name`, `channel_id`, `is_active`, `confidence_weight`).
  * **Response (200)**: `List[SignalProviderDTO]`.
* `POST /api/v1/providers`:
  * **Payload**: `SignalProviderCreateRequest` (`name`, `channel_id`, `confidence_weight`).
  * **Logika**: Menyimpan channel Telegram sumber sinyal baru ke database.
  * **Response (201)**: `SignalProviderDTO`.
* `GET /api/v1/providers/{id}/analytics`:
  * **Path Param**: `id: int`.
  * **Logika**: Menghitung total sinyal yang diterima, total trade yang dieksekusi, Win Rate, dan Total Realized Net PnL yang dihasilkan oleh provider tersebut.
  * **Response (200)**: `ProviderPerformanceDTO`.
* `GET /api/v1/strategies`:
  * **Logika**: Mengambil daftar konfigurasi strategi alokasi TP di tabel `strategies`.
  * **Response (200)**: `List[StrategyDTO]`.
* `PUT /api/v1/strategies/{id}`:
  * **Path Param**: `id: int`.
  * **Payload**: `StrategyUpdateRequest` (`tp1_percent`, `tp2_percent`, `tp3_percent`, `bep_trigger_level`, `trailing_trigger_level`).
  * **Logika**: Memperbarui rasio TP (memvalidasi total persentase = 100%) dan level trigger BEP/Trailing Stop.
  * **Response (200)**: `StrategyDTO`.

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Pendaftaran Channel Sinyal**: Penambahan channel Telegram baru tersimpan dengan valid dan memiliki bobot keyakinan (*confidence weight*).
2. **Leaderboard Akurat**: Endpoint analitik provider menghitung Win Rate dan total Net PnL per channel dengan presisi.
3. **Validasi Rasio TP**: Endpoint strategi menolak payload jika total rasio TP1 + TP2 + TP3 $\neq 100\%$.
4. **Testing**: Seluruh test di `backend/tests/api/test_providers_strategies_api.py` lulus 100%.
