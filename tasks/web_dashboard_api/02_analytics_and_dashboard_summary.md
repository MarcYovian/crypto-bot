# Task 02: Analytics & Dashboard Summary Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint metrik performa utama untuk kartu ringkasan dashboard (`/api/v1/analytics/summary`) dan data grafik pertumbuhan saldo modal (*equity curve*) harian (`/api/v1/analytics/equity-curve`).

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/routers/analytics.py`: Router FastAPI untuk endpoint analytics.
* `backend/tests/api/test_analytics_api.py`: Test suite untuk router analytics.

### Modifikasi File:
* `backend/src/api/app.py`: Menambahkan mounting `analytics_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `GET /api/v1/analytics/summary`:
  * **Query Params**: `account_id: Optional[int] = 1`.
  * **Strategi Caching**: Cache key `analytics:summary:{account_id}` dengan **TTL 10 detik**. Mencegah query agregasi berat (`SUM`, `COUNT`, `AVG`) diulang-ulang saat banyak browser membuka dashboard.
  * **Logika**: Mengambil total saldo dari `TradingAccount` / live Binance balance, menghitung Realized PnL hari ini dari `TradeSummary`, Win Rate (% trade profit), total trade (menang/kalah/breakeven), Profit Factor, serta sisa alokasi anggaran risiko harian (*daily risk budget*) dari `DailyRiskConfig`.
  * **Response (200)**: `AnalyticsSummaryDTO`.
* `GET /api/v1/analytics/equity-curve`:
  * **Query Params**: `timeframe: str = "30d"` (`7d`, `30d`, `90d`, `all`).
  * **Strategi Caching**: Cache key `analytics:equity:{timeframe}` dengan **TTL 60 detik**.
  * **Logika**: Mengambil riwayat snapshot saldo harian dari `daily_risk_configs` dan agregasi PnL harian dari `trade_summaries`.
  * **Response (200)**: `List[EquityPointDTO]`.

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Kalkulasi Akurat**: Nilai `win_rate`, `total_balance_usdt`, `daily_realized_pnl`, dan `profit_factor` terhitung dengan benar sesuai data di database.
2. **Kesesuaian Anggaran Risiko**: Nilai `daily_risk_budget` dan `remaining_risk_budget` mencerminkan batas limit 6% / 3x SL secara tepat.
3. **Efisiensi Caching**: Request kedua dalam rentang TTL langsung disajikan dari in-memory cache (< 1ms) tanpa membebani query database.
4. **Filter Waktu Equity Curve**: Endpoint `/equity-curve` mampu memfilter data berdasarkan parameter `7d`, `30d`, `90d`, atau `all`.
5. **Testing**: Seluruh test di `backend/tests/api/test_analytics_api.py` lulus 100%.
