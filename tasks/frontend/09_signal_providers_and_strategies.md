# Task 09: Signal Providers Management & Strategy Configuration Panel

## 1. Deskripsi Task
Membangun modul manajemen channel penyedia sinyal Telegram (*Signal Providers*) dan konfigurasi parameter strategi take profit / trailing stop (*Strategy Configuration*):
1. Membangun komponen **Signal Providers List & Creation (`src/features/strategies/components/SignalProvidersPanel.tsx`)** yang mengonsumsi endpoint `GET /api/v1/providers` dan `POST /api/v1/providers`:
   * Grid kartu provider yang menampilkan nama channel, Telegram Channel ID (`-100123456789`), bobot keyakinan (*confidence weight* misal `1.0`), dan status aktif.
   * Modal dialog **Add Provider Channel**: Form input nama channel, ID channel, bobot keyakinan, dan validasi format channel ID.
2. Membangun komponen **Provider Analytics Modal (`src/features/strategies/components/ProviderAnalyticsModal.tsx`)** yang mengonsumsi endpoint `GET /api/v1/providers/{id}/analytics`:
   * Menampilkan metrik performa historis provider: Total Sinyal Diterima, Transaksi yang Dieksekusi, Rasio Kemenangan (*Win Rate %*), dan Total Net PnL (USDT).
3. Membangun komponen **Strategy Configuration Form (`src/features/strategies/components/StrategyConfigPanel.tsx`)** yang mengonsumsi `GET /api/v1/strategies` dan `PUT /api/v1/strategies/{id}`:
   * Pengaturan rasio alokasi Take Profit bertingkat: Slider / Number Input untuk `TP1 (%)`, `TP2 (%)`, dan `TP3 (%)`.
   * **Validasi Jumlah Persentase 100%**: Memastikan $\text{TP1} + \text{TP2} + \text{TP3} = 100\%$ (default: 50% / 30% / 20%). Jika total $\ne 100\%$, tombol simpan terkunci dan muncul alert merah: *"Total alokasi TP harus tepat 100%"*.
   * Pemilihan level trigger Break-Even Price (BEP): Level TP mana yang memicu penggeseran Stop Loss ke harga Entry (default: Level 1).
   * Pemilihan level trigger Trailing Stop: Level TP mana yang mengaktifkan trailing stop dinamis (default: Level 2).
4. Proteksi RBAC: Modifikasi pengaturan strategi dan penambahan provider hanya dapat dilakukan oleh role `ADMIN`.

---

## 2. File yang Akan Dibuat / Dimodifikasi

### API Endpoints & Types:
* `frontend/src/api/endpoints/providers.ts`: Fungsi API `getProvidersApi()`, `createProviderApi(payload: SignalProviderCreateRequestDTO)`, `getProviderAnalyticsApi(id: number)`.
* `frontend/src/api/endpoints/strategies.ts`: Fungsi API `getStrategiesApi()`, `updateStrategyApi(id: number, payload: StrategyUpdateRequestDTO)`.
* `frontend/src/types/providers.ts`: TypeScript interfaces (`SignalProviderDTO`, `SignalProviderCreateRequestDTO`, `ProviderPerformanceDTO`).
* `frontend/src/types/strategies.ts`: TypeScript interfaces (`StrategyDTO`, `StrategyUpdateRequestDTO`, `TPAllocationDTO`).

### Komponen UI Provider & Strategi:
* `frontend/src/features/strategies/StrategiesPage.tsx`: Halaman utama strategi dan signal providers.
* `frontend/src/features/strategies/components/SignalProvidersPanel.tsx`: Panel grid kartu signal providers.
* `frontend/src/features/strategies/components/AddProviderModal.tsx`: Modal form pendaftaran channel Telegram baru.
* `frontend/src/features/strategies/components/ProviderAnalyticsModal.tsx`: Modal statistik performa dan win rate provider.
* `frontend/src/features/strategies/components/StrategyConfigPanel.tsx`: Form slider konfigurasi alokasi TP1/TP2/TP3 dan trigger BEP/Trailing.

### Unit & Integration Tests:
* `frontend/tests/features/strategy_config.test.tsx`: Pengujian validasi penjumlahan 100% alokasi TP, update trigger BEP/Trailing, dan submisi API.
* `frontend/tests/features/provider_panel.test.tsx`: Pengujian pendaftaran channel baru dan render performa analitik provider.

---

## 3. Rincian Endpoint API yang Diintegrasikan

### 1. `GET /api/v1/providers` & `POST /api/v1/providers`
* **GET Response (200 OK)**:
  ```json
  [
    {
      "id": 1,
      "name": "Crypto VIP Signals",
      "channel_id": "-100123456789",
      "is_active": true,
      "confidence_weight": 1.0
    }
  ]
  ```
* **POST Request Body**:
  ```json
  {
    "name": "SMC Alpha Signals",
    "channel_id": "-100987654321",
    "confidence_weight": 1.2
  }
  ```

### 2. `GET /api/v1/providers/{id}/analytics`
* **Response (200 OK)**:
  ```json
  {
    "provider_id": 1,
    "provider_name": "Crypto VIP Signals",
    "total_signals": 50,
    "executed_trades": 45,
    "win_rate": 75.0,
    "total_net_pnl_usdt": 450.25
  }
  ```

### 3. `GET /api/v1/strategies` & `PUT /api/v1/strategies/{id}`
* **GET Response (200 OK)**:
  ```json
  [
    {
      "id": 1,
      "name": "Standard 3-Stage TP",
      "tp_allocations": [
        {"tp_level": 1, "percentage": 50.0},
        {"tp_level": 2, "percentage": 30.0},
        {"tp_level": 3, "percentage": 20.0}
      ],
      "bep_trigger_level": 1,
      "trailing_trigger_level": 2,
      "is_active": true
    }
  ]
  ```
* **PUT Request Body** (`StrategyUpdateRequest`):
  ```json
  {
    "tp1_percent": 50.0,
    "tp2_percent": 30.0,
    "tp3_percent": 20.0,
    "bep_trigger_level": 1,
    "trailing_trigger_level": 2
  }
  ```

---

## 4. Edge Cases & Error Handling
1. **Total Alokasi TP Kurang atau Lebih dari 100%**: Form slider menghitung total $\text{sum} = \text{tp1} + \text{tp2} + \text{tp3}$ secara real-time. Jika total $\ne 100.0$, form menampilkan badge merah *"Total: 95.0% (Kurang 5.0%)"* dan men-disable tombol submit.
2. **Channel ID Duplikat**: Jika backend mengembalikan HTTP 409 Conflict saat menambahkan channel, form menampilkan error: *"Channel ID ini sudah terdaftar di sistem."*
3. **Provider Tanpa Riwayat Trade**: Jika provider baru belum memiliki histori eksekusi $\rightarrow$ Modal analitik menampilkan `0 signals`, `0 trades`, dan `Win Rate 0.0%` tanpa error rendering.

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. Grid Signal Providers menampilkan seluruh channel terdaftar lengkap dengan status aktif dan bobot kepercayaan.
2. Admin dapat menambahkan channel Telegram baru melalui modal dialog dan data langsung muncul di grid.
3. Modal analitik provider menyajikan rekap metrik win rate dan net PnL secara akurat.
4. Form konfigurasi strategi memvalidasi secara ketat aturan total alokasi TP 100% dan berhasil menyimpan pembaruan via `PUT /api/v1/strategies/{id}`.
5. Seluruh unit test di `frontend/tests/features/strategy_config.test.tsx` dan `frontend/tests/features/provider_panel.test.tsx` lulus 100%.
