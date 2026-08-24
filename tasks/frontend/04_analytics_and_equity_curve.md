# Task 04: Executive Analytics Dashboard & Interactive Equity Curve Chart

## 1. Deskripsi Task
Membangun modul analitik portofolio eksekutif yang menyajikan 6 kartu ringkasan KPI finansial real-time dan grafik kurva pertumbuhan ekuitas interaktif (*TradingView Lightweight Charts*) dengan selector rentang waktu:
1. Membangun komponen **Executive KPI Summary Cards (`src/features/dashboard/components/SummaryKPICards.tsx`)** yang mengonsumsi endpoint `GET /api/v1/analytics/summary` (Cached backend TTL 10s):
   * **Total Balance**: Saldo total akun dalam USDT (`$10,450.50 USDT`) dalam font monospaced besar.
   * **Free Margin**: Margin bebas yang tersedia untuk order baru beserta persentase utilisasi.
   * **Daily Realized PnL**: Keuntungan/kerugian terealisasi hari ini dalam nominal ($) dan persentase (%) dengan pewarnaan dinamis (Hijau `#10B981` jika $\ge 0$, Merah `#EF4444` jika $< 0$).
   * **Win Rate (%)**: Rasio kemenangan trading beserta visual mini progress bar dan jumlah total transaksi (`72.5% (40 trades)`).
   * **Profit Factor**: Rasio gross profit terhadap gross loss (`2.85`).
   * **Remaining Daily Risk Budget**: Sisa alokasi risiko harian sebelum Circuit Breaker otomatis mematikan engine (`$154.50 / $200.00`).
2. Membangun komponen **Interactive Equity Curve Chart (`src/features/dashboard/components/EquityCurveChart.tsx`)** yang mengonsumsi `GET /api/v1/analytics/equity-curve` (Cached backend TTL 60s):
   * Visualisasi kurva pertumbuhan ekuitas berbasis kanvas berkinerja tinggi (*TradingView Lightweight Charts* atau *Recharts Area*).
   * Tombol selector rentang waktu: `7d`, `30d`, `90d`, `all` (selaras dengan query parameter OpenAPI).
   * Tooltip interaktif saat kursor mouse di-hover di atas grafik (menampilkan tanggal, waktu, saldo ekuitas, dan perubahan PnL).
3. Mengintegrasikan **TanStack Query Caching & Real-Time Sync**:
   * Auto-refetch dan invalidasi cache seketika saat event WebSocket `TRADE_CLOSED` atau `CIRCUIT_BREAKER_TRIGGERED` diterima.
4. Menyiapkan **Skeleton Loading Placeholders** berdimensi presisi untuk menjamin *Zero Cumulative Layout Shift (CLS < 0.05)*.

---

## 2. File yang Akan Dibuat / Dimodifikasi

### API Endpoints & Types:
* `frontend/src/api/endpoints/analytics.ts`: Fungsi API `getAnalyticsSummaryApi(accountId?: number)` dan `getEquityCurveApi(timeframe?: string)`.
* `frontend/src/types/analytics.ts`: TypeScript interfaces (`AnalyticsSummaryDTO`, `EquityPointDTO`).

### Komponen UI Dashboard:
* `frontend/src/features/dashboard/components/SummaryKPICards.tsx`: Grid 6 kartu KPI finansial dengan styling glassmorphism dan font monospaced.
* `frontend/src/features/dashboard/components/KPICard.tsx`: Komponen kartu atomik dengan icon, title, value, delta percentage, dan badge status.
* `frontend/src/features/dashboard/components/EquityCurveChart.tsx`: Wrapper TradingView Lightweight Charts dengan resize handler dan timeframe picker.
* `frontend/src/features/dashboard/components/DashboardSkeleton.tsx`: Placeholder skeleton loading untuk KPI cards dan chart.
* `frontend/src/features/dashboard/DashboardOverviewPage.tsx`: Halaman utama ringkasan dashboard.

### Unit & Visual Tests:
* `frontend/tests/features/summary_kpi_cards.test.tsx`: Pengujian formatting angka mata uang, pewarnaan dinamis profit/loss, dan kalkulasi risk budget.
* `frontend/tests/features/equity_curve_chart.test.tsx`: Pengujian pergantian rentang waktu (`7d`, `30d`, `all`) dan handling data kosong.

---

## 3. Rincian Endpoint API yang Diintegrasikan

### 1. `GET /api/v1/analytics/summary`
* **Query Parameters**: `account_id` (default: 1).
* **Response (200 OK)**:
  ```json
  {
    "total_balance_usdt": 10450.50,
    "free_margin_usdt": 9800.20,
    "daily_realized_pnl": 45.50,
    "daily_pnl_percent": 0.45,
    "daily_risk_budget": 200.00,
    "remaining_risk_budget": 154.50,
    "win_rate": 72.5,
    "total_trades_count": 40,
    "winning_trades_count": 29,
    "losing_trades_count": 11,
    "profit_factor": 2.85,
    "active_trades_count": 2
  }
  ```

### 2. `GET /api/v1/analytics/equity-curve`
* **Query Parameters**: `timeframe` (`7d` | `30d` | `90d` | `all`, default: `30d`).
* **Response (200 OK)**:
  ```json
  [
    {"timestamp": "2026-08-01T00:00:00Z", "balance": 10000.00, "pnl": 0.00},
    {"timestamp": "2026-08-02T14:30:00Z", "balance": 10250.00, "pnl": 250.00}
  ]
  ```

---

## 4. Rincian Interaksi & Fitur Visual

### 4.1 Daily Risk Budget Circuit Breaker Alert
* Jika sisa budget risiko $\le 20\%$ dari total alokasi harian:
  * Kartu *Remaining Risk Budget* menampilkan border pendaran kuning/amber (`border-amber-500/50 animate-pulse`).
  * Muncul tooltip peringatan: *"Peringatan: Alokasi risiko harian hampir habis. Engine akan otomatis menjeda perdagangan jika batas harian terlampaui."*

### 4.2 Chart Responsiveness & Theming
* Grafik mendeteksi perubahan ukuran jendela browser (*ResizeObserver*) dan me-render ulang kanvas secara otomatis.
* Warna gradien kurva ekuitas: Area atas berwarna biru neon cerah (`#38BDF8`) dengan fill gradient transparan ke bawah (`rgba(56, 189, 248, 0.05)`).

---

## 5. Edge Cases & Error Handling
1. **Akun Baru / Zero Trade History**: Jika `total_trades_count === 0`, kartu Win Rate menampilkan `0.0% (0 trades)`, Profit Factor menampilkan `0.00`, dan grafik ekuitas merender garis horizontal setinggi saldo awal tanpa error.
2. **Koneksi Jaringan Lambat**: Skeleton loader tampil selama fetching data berlangsung; jika terjadi timeout, muncul tombol *Retry Fetch Analytics*.
3. **Pembaruan Real-Time saat Trade Tutup**: Event WS `TRADE_CLOSED` secara otomatis memicu `queryClient.invalidateQueries({ queryKey: ['analytics'] })` sehingga nilai PnL dan saldo langsung ter-update tanpa flicker layar.

---

## 6. Kriteria Keberhasilan (Acceptance Criteria)
1. 6 kartu metrik terisi angka monospaced yang presisi sesuai respon API `/analytics/summary`.
2. Daily PnL berubah warna hijau neon saat profit dan merah mawar saat loss.
3. Grafik TradingView merender data historis ekuitas dengan mulus pada rentang waktu `7d`, `30d`, `90d`, dan `all`.
4. Tooltip hover grafik menampilkan timestamp, balance, dan pnl perubahan dengan akurat.
5. Seluruh unit test di `frontend/tests/features/summary_kpi_cards.test.tsx` dan `frontend/tests/features/equity_curve_chart.test.tsx` lulus 100%.
