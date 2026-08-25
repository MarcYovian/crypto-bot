# Task 13: Application Shell, Pro-Terminal Layout, Navigation & E2E Integration

## 1. Deskripsi Task
Membangun shell aplikasi utama (*Application Shell*), tata letak terminal pro multi-panel yang responsif (*Responsive Multi-Panel Layout Grid*), navigasi sidebar terpadu dengan adaptasi tablet & mobile, sistem toaster notifikasi global, *React Error Boundaries* pelindung crash, serta verifikasi integrasi menyeluruh (*End-to-End Integration*) terhadap seluruh 25+ endpoint REST API dan WebSocket backend FastAPI:
1. Membangun komponen **Top Navbar (`src/components/layout/Navbar.tsx`)**:
   * Logo & Judul Branding "SMC CryptoBot".
   * Snippet Status Hero Bot (`🟢 RUNNING` / `🟡 PAUSED`).
   * WebSocket Live Connection Indicator (`ConnectionStatusBadge`).
   * Tampilan Live Total Balance USDT (`$10,450.50`).
   * User Profile Menu & Role Badge (`UserMenuBadge`).
2. Membangun komponen **Navigation Sidebar & Mobile Bottom Bar (`src/components/layout/Sidebar.tsx` & `MobileNav.tsx`)**:
   * Desktop ($> 1280\text{px}$): Sidebar tetap lebar $240\text{px}$ dengan 8 menu navigasi utama.
   * Tablet ($768\text{px} - 1279\text{px}$): Sidebar ter-collapse menjadi ikon rail ($64\text{px}$) dengan tooltip hover nama menu.
   * Mobile ($< 768\text{px}$): Bottom Navigation Bar dengan ikon pintasan cepat ke Overview, Active Trades, Signals, dan Bot Controls.
3. Membangun **React Error Boundary Layer (`src/components/feedback/ErrorBoundary.tsx`)**:
   * Membungkus setiap widget kritis (Summary Cards, Chart, Tabel Posisi, Form Kalkulator) secara terpisah sehingga jika satu komponen mengalami error JavaScript, komponen lain tetap beroperasi normal tanpa memicu *White Screen of Death*.
4. Mengintegrasikan **Global Toast Notifications Provider (`Toaster`)** dan **Audio Alert Dispatcher**:
   * Menampilkan toast pendaran profit hijau saat TP hit, toast merah saat SL hit / panic action, dan toast info biru saat order exchange terisi.
5. Menyiapkan berkas **Main Bootstrap & Provider Tree (`src/App.tsx` & `src/main.tsx`)**:
   * Mounting `QueryClientProvider` (TanStack Query), `BrowserRouter`, `AuthProvider`, `WebSocketProvider`, dan `ToasterProvider`.
6. Pengujian & Verifikasi Integrasi End-to-End (E2E) terhadap backend FastAPI di port `8000`.

---

## 2. File yang Akan Dibuat / Dimodifikasi

### Layout & Shell:
* `frontend/src/components/layout/RootLayout.tsx`: Shell utama pembungkus navbar, sidebar, main viewport, dan mobile navigation.
* `frontend/src/components/layout/Navbar.tsx`: Header navigasi atas dengan status live balance, bot status hero snippet, WS badge, dan user badge.
* `frontend/src/components/layout/Sidebar.tsx`: Sidebar menu navigasi desktop dan collapsible icon rail tablet.
* `frontend/src/components/layout/MobileNav.tsx`: Bottom navigation bar untuk tampilan layar smartphone.
* `frontend/src/components/feedback/ErrorBoundary.tsx`: Fallback UI graceful degradation saat terjadi crash lokal.
* `frontend/src/components/feedback/ToastProvider.tsx`: Wrapper toast notification alert.

### Routing & Wiring:
* `frontend/src/App.tsx`: Router configuration dengan route protection (`AuthGuard`, `RoleGuard`) ke seluruh 8 halaman modul.
* `frontend/src/main.tsx`: Entrypoint aplikasi dengan QueryClient, WebSocket listener initialization, dan Tailwind styles.

### File Dimodifikasi / Root Configuration:
* `docker-compose.yml`: Menambahkan service `frontend` (build: `./frontend`, ports: `3000:80`, depends_on: `crypto-bot`).

### Integration & E2E Tests:
* `frontend/tests/integration/app_routing.test.tsx`: Pengujian navigasi seluruh rute, redirect unauthenticated user ke `/login`, dan proteksi hak akses `VIEWER`.
* `frontend/tests/integration/error_boundary.test.tsx`: Pengujian isolasi crash pada komponen individual.

---

## 3. Peta Navigasi & Rute Aplikasi

| Rute Path | Nama Halaman | Komponen Fitur Utama | Proteksi Role |
| :--- | :--- | :--- | :---: |
| `/login` | Login Screen | `LoginPage` | Public |
| `/dashboard` | Executive Overview | `SummaryKPICards`, `EquityCurveChart` | `ADMIN`, `VIEWER` |
| `/trades/active` | Live Active Positions | `ActiveTradesTable`, `TPMilestoneBar` | `ADMIN`, `VIEWER` (Close: Admin) |
| `/trades/history`| Closed Trade History | `TradeHistoryTable`, `TradeDetailModal` | `ADMIN`, `VIEWER` |
| `/signals` | Live Telegram Feed | `SignalFeedList`, `SignalExecutionWizardModal` | `ADMIN`, `VIEWER` (Exec: Admin) |
| `/watchlist` | Watchlist & Instruments| `WatchlistGrid`, `InstrumentBracketModal` | `ADMIN`, `VIEWER` (Toggle/Sync: Admin) |
| `/calculator` | Risk Simulator Sandbox | `RiskSimulatorForm`, `SimulationResultCard` | `ADMIN`, `VIEWER` |
| `/bot-settings`| Bot Ops & Credentials | `BotStatusHero`, `PanicCloseModal`, `BotSettingsForm` | `ADMIN` Only |
| `/logs-reports`| Audit Logs & Reports | `AuditLogsTerminal`, `CsvExportCard` | `ADMIN`, `VIEWER` |

---

## 4. Rincian Layout Grid & Breakpoints

```
+-----------------------------------------------------------------------------------------------+
| TOP NAVBAR: [Logo SMC Bot] [🟢 ACTIVE] [🟢 WS Live] [💰 $10,450.50 USDT] [👤 Admin (ADMIN)]    |
+-------------------+---------------------------------------------------------------------------+
| SIDEBAR (240px)   | MAIN VIEWPORT (Pro-Trading Dark Canvas #080B10)                           |
|                   |                                                                           |
| 📊 Overview       | +-----------------------------------------------------------------------+ |
| ⚡ Active Trades  | | 6 KPI SUMMARY CARDS (Balance, Margin, Daily PnL, WinRate, Risk Budget)| |
| 📜 Trade History  | +-----------------------------------------------------------------------+ |
| 🎯 Signal Feed    | +-----------------------------------+ +---------------------------------+ |
| 👁️ Watchlist      | | EQUITY CURVE CHART (TradingView)  | | ACTIVE POSITIONS TABLE          | |
| 🧮 Risk Simulator | | (7D / 30D / 90D / ALL Filter)     | | (Price Flash & TP Milestones)   | |
| 🚨 Bot Operations | +-----------------------------------+ +---------------------------------+ |
| 📋 Logs & Reports | +-----------------------------------------------------------------------+ |
|                   | | RECENT SIGNALS & QUICK EXECUTION WIZARD CARDS                         | |
| [<< Collapse]     | +-----------------------------------------------------------------------+ |
+-------------------+---------------------------------------------------------------------------+
```

---

## 5. Edge Cases & Resilience
1. **Komponen Pihak Ketiga Crash (misal: Library Canvas Chart Error)**: `ErrorBoundary` lokal menangkap error dan menampilkan tombol *Retry Component* tanpa merusak halaman tabel posisi aktif atau navbar.
2. **Koneksi Jaringan Lambat / Flapping**: Shell aplikasi mempertahankan state form input pengguna saat terjadi auto-reconnect WebSocket di latar belakang.
3. **Perubahan Ukuran Layar Dinamis**: Responsive resize handler memastikan grafik dan tabel langsung menyesuaikan layout tanpa scrollbar yang rusak (*Zero Horizontal Overflow*).

---

## 6. Kriteria Keberhasilan (Acceptance Criteria)
1. Shell aplikasi ter-render sempurna dengan top navbar, sidebar desktop, icon rail tablet, dan bottom bar mobile.
2. Seluruh 8 rute halaman dapat diakses mulus dengan proteksi `AuthGuard` dan `RoleGuard`.
3. Error Boundary lokal berhasil mengisolasi error komponen tanpa menyebabkan white screen.
4. Toast alert dan audio chime terpicu secara tepat saat event transaksi diterima via WebSocket.
5. Build production (`npm run build`) berhasil tanpa error dengan ukuran initial bundle $< 250\text{ KB}$ (gzipped).
6. Seluruh test integrasi di `frontend/tests/integration/app_routing.test.tsx` dan `frontend/tests/integration/error_boundary.test.tsx` lulus 100%.
7. Service `frontend` berhasil dibuild dan berjalan dalam container Docker (`docker compose up --build`), melayani port `3000:80` dan berkomunikasi dengan backend `crypto-bot:8000`.
