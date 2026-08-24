# User Flow & Interaction Specification (USER_FLOW.md)
**Project**: SMC CryptoBot – Professional Binance Futures Trading Dashboard  
**Document**: Frontend User Flow & Journey Maps (`USER_FLOW.md`)  
**Version**: 2.0.0  
**Status**: Approved / In Development  
**Target Platform**: Web Frontend (Next.js 14 / Vite React + TypeScript)  
**Related Documents**: [docs/frontend/PRD.md](file:///home/rodex/Documents/cell/projects/crypto-bot/docs/frontend/PRD.md) | [docs/frontend/REQUIREMENTS.md](file:///home/rodex/Documents/cell/projects/crypto-bot/docs/frontend/REQUIREMENTS.md) | [docs/frontend/FEATURES.md](file:///home/rodex/Documents/cell/projects/crypto-bot/docs/frontend/FEATURES.md)  

---

## 1. Peta Navigasi & Arsitektur Alur Pengguna

```mermaid
flowchart TD
    Start([User Membuka Aplikasi]) --> AuthCheck{Memiliki Sesi Aktif?}
    
    AuthCheck -- Tidak --> LoginPage[Halaman Login /login]
    LoginPage --> SubmitLogin[Submit Username & Password]
    SubmitLogin -- Valid --> InitSession[Simpan JWT & Inisialisasi WebSocket]
    SubmitLogin -- Invalid --> ShowLoginError[Tampilkan Pesan Error Kredensial]
    
    AuthCheck -- Ya --> InitSession
    InitSession --> DashboardHome[Dashboard Utama /dashboard]

    subgraph NavigationMenu ["Navigasi Utama Dashboard"]
        DashboardHome --> M_Analytics[1. Overview & Equity Curve]
        DashboardHome --> M_Trades[2. Live Active Positions]
        DashboardHome --> M_History[3. Closed Trades History]
        DashboardHome --> M_Signals[4. Live Telegram Signal Feed]
        DashboardHome --> M_Watchlist[5. Watchlist & Instruments]
        DashboardHome --> M_Calculator[6. Risk Simulator Sandbox]
        DashboardHome --> M_Operations[7. Bot Control & Settings]
        DashboardHome --> M_Logs[8. System Logs & CSV Export]
    end
```

---

## 2. Rincian Alur Pengguna (User Flows)

---

### 🔐 FLOW-01: Autentikasi, Inisialisasi Sesi & Silent Token Refresh

Diagram berikut menggambarkan alur login pengguna, inisialisasi koneksi WebSocket real-time, serta mekanisme *silent token refresh* otomatis saat access token kedaluwarsa tanpa memutus aktivitas pengguna.

```mermaid
sequenceDiagram
    autonumber
    actor User as Trader
    participant App as React Frontend
    participant Interceptor as Axios Interceptor
    participant AuthAPI as Backend /api/v1/auth
    participant WS as WebSocket /api/v1/ws

    User->>App: Input Username & Password -> Klik "Sign In"
    App->>AuthAPI: POST /api/v1/auth/login
    alt Kredensial Valid
        AuthAPI-->>App: 200 OK (access_token 15m, refresh_token 7d, role)
        App->>App: Simpan access_token di Memory State & refresh_token di Storage
        App->>WS: Handshake ws://<host>/api/v1/ws?token=<access_token>
        WS-->>App: 101 Switching Protocols (CONNECTED)
        App-->>User: Redirect ke /dashboard (Role Badge: ADMIN / VIEWER)
    else Kredensial Salah
        AuthAPI-->>App: 401 Unauthorized ("Invalid credentials")
        App-->>User: Tampilkan alert error merah pada form
    end

    Note over App,AuthAPI: Skenario: Access Token Kedaluwarsa (> 15 Menit)
    User->>App: Melakukan request API (misal: Buka Tab Watchlist)
    App->>Interceptor: GET /api/v1/watchlist
    Interceptor->>AuthAPI: GET /api/v1/watchlist (Header: Bearer ExpiredToken)
    AuthAPI-->>Interceptor: 401 Unauthorized (Token Expired)
    
    Note over Interceptor,AuthAPI: Silent Refresh Otomatis di Background
    Interceptor->>AuthAPI: POST /api/v1/auth/refresh (Body: refresh_token)
    alt Refresh Token Masih Valid
        AuthAPI-->>Interceptor: 200 OK (New access_token)
        Interceptor->>Interceptor: Perbarui access_token di Memory
        Interceptor->>AuthAPI: Replay GET /api/v1/watchlist (Bearer NewToken)
        AuthAPI-->>App: 200 OK (Data Watchlist)
        App-->>User: Tampilkan data tanpa gangguan sesi
    else Refresh Token Kedaluwarsa / Blacklisted
        AuthAPI-->>Interceptor: 401 Unauthorized
        Interceptor->>App: Bersihkan Sesi (Clear Memory & Storage)
        App-->>User: Redirect ke /login ("Sesi berakhir, silakan login kembali")
    end
```

#### Langkah-Langkah Keputusan & State:
1. **Input Kredensial**: Pengguna memasukkan username dan password. Form memvalidasi bahwa kedua field tidak boleh kosong sebelum tombol aktif.
2. **Handshake WebSocket**: Begitu token access diperoleh, client langsung membuka koneksi stream `/api/v1/ws?token=...` untuk menerima event real-time.
3. **Queue Locking pada Interceptor**: Jika ada 5 request REST simultan yang menerima 401, hanya request pertama yang memanggil `/auth/refresh`, sementara 4 lainnya menunggu di antrian (*Promise queue*) untuk di-replay bersamaan setelah token baru tersedia.

---

### 📊 FLOW-02: Monitoring Harian & Inspeksi Kurva Pertumbuhan Ekuitas

Alur pemantauan kesehatan finansial portofolio, saldo USDT, margin terpakai, dan pemilihan rentang waktu kurva ekuitas.

```mermaid
flowchart TD
    A[User Membuka Tab Overview] --> B[Fetch Data Simultan]
    
    subgraph ParallelFetch ["Parallel Data Fetching"]
        B --> C1[GET /api/v1/analytics/summary]
        B --> C2[GET /api/v1/analytics/equity-curve?timeframe=7D]
        B --> C3[GET /api/v1/bot/status]
    end

    C1 --> D1[Render 6 Kartu KPI: Balance, Margin, PnL, Win Rate, Profit Factor, Risk Budget]
    C2 --> D2[Render Canvas Grafik TradingView Lightweight Charts]
    C3 --> D3[Render Hero Banner Status Bot]

    D1 & D2 & D3 --> E{User Berinteraksi dengan Chart?}
    
    E -- Ubah Rentang Waktu --> F[User Klik 1D / 7D / 30D / ALL]
    F --> G[Fetch GET /api/v1/analytics/equity-curve?timeframe=XX]
    G --> H[Update Canvas Garis Grafik secara Mulus]

    E -- Hover di Atas Grafik --> I[Tampilkan Tooltip: Tanggal, Jam, Saldo USDT, % Perubahan]
    
    E -- Menerima Event WS TRADE_CLOSED --> J[Otomatis Refetch Summary & Chart]
    J --> D1
    J --> D2
```

#### Detail Interaksi:
* **Tooltip Data Multi-Dimensi**: Saat kursor digeser di atas kurva ekuitas, titik data menampilkan saldo ekuitas pada jam tersebut dan nominal perubahan PnL dibandingkan titik sebelumnya.
* **Auto-Sync**: Saat ada trade yang selesai ditutup di exchange, event WebSocket `TRADE_CLOSED` memicu invalidasi query cache TanStack Query sehingga angka PnL harian dan total balance bertambah/berkurang seketika.

---

### ⚡ FLOW-03: Ingesti Sinyal Telegram & Eksekusi Manual 1-Klik

Alur dari penerimaan sinyal Telegram hingga pembukaan posisi Binance Futures dengan validasi proteksi risiko (*Hard 2% Risk Cap*).

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Trader Admin
    participant Feed as Signal Feed Component
    participant Wizard as Execution Wizard Modal
    participant Calc as Risk Validator Engine
    participant API as Backend /api/v1/signals
    participant WS as WebSocket Client

    Note over Feed: Sinyal baru masuk dari Telegram (PARSED)
    Feed-->>Admin: Menampilkan Kartu Sinyal (BTCUSDT BUY, Entry 50000, SL 49000, TP 51000/52000/53000)
    Admin->>Feed: Klik tombol "Execute Trade"
    Feed->>Wizard: Buka Modal Wizard Eksekusi
    Wizard->>Calc: Hitung Lot Size Otomatis (Berdasarkan Balance Akun & Jarak SL)
    Calc-->>Wizard: Recommended Qty = 0.02 BTC, Margin = $50.00, Risk = $20.00 (2.0%)

    alt Parameter Sesuai Aturan (Risiko <= 2.0%)
        Wizard-->>Admin: Tampilkan Preview Risiko (Badge Hijau: "SAFE - 2.0% Risk ($20.00)")
        Note over Wizard: Tombol "Confirm & Execute" AKTIF
        Admin->>Wizard: Klik "Confirm & Execute"
        Wizard->>API: POST /api/v1/signals/manual-execute
        alt Eksekusi Berhasil di Binance
            API-->>Wizard: 200 OK (Trade Execution Result DTO)
            Wizard-->>Admin: Tutup Modal & Tampilkan Toast Sukses Hijau
            WS-->>Feed: Event TRADE_OPENED diterima
            Feed->>Feed: Ubah Status Kartu Sinyal menjadi EXECUTED
            Feed->>Feed: Tambahkan posisi ke Tabel Active Trades
        else Gagal di Binance (misal: Insufficient Balance)
            API-->>Wizard: 400 Bad Request / 500 Error
            Wizard-->>Admin: Tampilkan Pesan Error Merah pada Modal (Form Tetap Terbuka)
        end
    else User Memodifikasi SL Terlalu Jauh (Risiko > 2.0%)
        Admin->>Wizard: Mengubah SL menjadi 47000 (Risiko naik jadi 3.5%)
        Wizard->>Calc: Validasi Ulang Risiko
        Calc-->>Wizard: Risk Amount = $35.00 (> 2.0% Risk Cap)
        Wizard-->>Admin: Tampilkan Alert Merah: "Risiko melebihi batas maksimal 2% ($20.00 USDT)"
        Note over Wizard: Tombol "Confirm & Execute" TERKUNCI MATI (Disabled)
    end
```

#### Validasi Geometri Harga di Level Frontend:
* **Posisi BUY (LONG)**: Wajib $\text{Stop Loss} < \text{Entry Price} < \text{TP1} < \text{TP2} < \text{TP3}$.
* **Posisi SELL (SHORT)**: Wajib $\text{Stop Loss} > \text{Entry Price} > \text{TP1} > \text{TP2} > \text{TP3}$.
* Jika terjadi pelanggaran geometri harga (misal: SL di atas Entry pada posisi BUY), form menampilkan pesan error instan dan tombol submit dikunci.

---

### 🛡️ FLOW-04: Pemantauan Posisi Aktif, TP Scaling & Manual Close

Alur pemantauan posisi live, animasi progres Take Profit bertingkat, dan penutupan pasar manual darurat.

```mermaid
flowchart TD
    A[Tabel Active Trades] --> B{Pembaruan Event dari WebSocket?}
    
    B -- Event TP_HIT (TP1) --> C1[Animasi Milestone TP1 Berubah Hijau]
    C1 --> C2[Badge SL Berubah dari INITIAL_SL ke BEP_SL]
    C2 --> C3[Volume Remaining Qty Berkurang 50%]
    C3 --> C4[Toast Notifikasi Hijau: TP1 Hit + Realized Profit]

    B -- Event TP_HIT (TP2) --> D1[Animasi Milestone TP2 Berubah Hijau]
    D1 --> D2[Badge SL Berubah menjadi TRAILING_SL Level TP1]
    D2 --> D3[Volume Remaining Qty Berkurang 30%]
    D3 --> D4[Toast Notifikasi Hijau: TP2 Hit + Trailing SL Active]

    B -- Event SL_HIT / TP3_HIT --> E1[Event TRADE_CLOSED Diterima]
    E1 --> E2[Hapus Baris Posisi dari Tabel Active Trades]
    E2 --> E3[Pindahkan Data ke Tabel Closed Trades History]
    E3 --> E4[Toast Rekap Hasil: WIN / LOSS]

    B -- User Ingin Tutup Posisi Sendiri --> F[User Klik Tombol Merah 'Close Position']
    F --> G[Buka Modal Konfirmasi: 'Tutup 0.02 BTC pada Harga Pasar?']
    G --> H{User Konfirmasi?}
    H -- Batal --> I[Tutup Modal, Posisi Tetap Berjalan]
    H -- Ya, Tutup --> J[POST /api/v1/trades/{id}/close]
    J --> K[Posisi Ditutup di Binance & Pindah ke Riwayat]
```

---

### 🔍 FLOW-05: Riwayat Closed Trades & Modal Inspeksi 5-Level

Alur penelusuran riwayat transaksi masa lalu dan audit mendalam riwayat eksekusi order exchange.

```mermaid
sequenceDiagram
    autonumber
    actor User as Trader / Auditor
    participant View as Trade History View
    participant Modal as 5-Level Detail Tree Modal
    participant API as Backend /api/v1/trades

    User->>View: Buka Tab "Trade History"
    View->>API: GET /api/v1/trades/history?page=1&page_size=10
    API-->>View: 200 OK (Paginated Trades List & Metadata)
    View-->>User: Tampilkan Tabel Transaksi dengan Filter & Pagination

    User->>View: Klik Salah Satu Baris Trade (misal: Trade #101 BTCUSDT)
    View->>Modal: Buka Modal Dialog (Loading Skeleton)
    Modal->>API: GET /api/v1/trades/101
    API-->>Modal: 200 OK (TradeDetailDTO lengkap dengan risk, orders, executions, summary)
    
    Modal-->>User: Tampilkan 5 Tab Navigasi:
    Note over Modal,User: Tab 1: Overview (Simbol, Side, Durasi, Close Reason)
    Note over Modal,User: Tab 2: Risk Parameters (Alokasi Modal, Stop Distance, Leverage)
    Note over Modal,User: Tab 3: Order Lifecycle (Daftar Order ENTRY, TP1, TP2, TP3, SL)
    Note over Modal,User: Tab 4: Executions (Daftar Fill Riil, Harga, Fee Komisi)
    Note over Modal,User: Tab 5: Financial Summary (Gross PnL, Net PnL, ROI %, RR Terwujud)
    
    User->>Modal: Beralih Antar Tab untuk Memeriksa Detail
    User->>Modal: Klik Tombol "Tutup Modal" (ESC / Tombol Silang)
    Modal-->>View: Modal Tertutup
```

---

### 🧮 FLOW-06: Sandbox Simulasi Risiko & Dynamic Leverage Testing

Alur kalkulator simulasi risiko untuk menguji skenario ukuran posisi dan mendeteksi penyesuaian leverage exchange (*downscaling*) sebelum trading riil.

```mermaid
flowchart TD
    A[User Membuka Tab Risk Simulator] --> B[Form Input Parameter]
    
    B --> C1[Pilih Simbol: BTCUSDT -> Auto-fill Harga Live]
    B --> C2[Pilih Arah: BUY / SELL]
    B --> C3[Input Entry Price & Stop Loss Price]
    B --> C4[Input Modal Balance & Slider Risk %: misal 2.0%]

    C1 & C2 & C3 & C4 --> D[Debounce 300ms -> Validasi Geometri Harga Lokal]
    
    D -- Valid --> E[POST /api/v1/calculator/simulate]
    D -- Invalid SL >= Entry pada BUY --> F[Tampilkan Peringatan Geometri Merah Lokal, Jangan Kirim Request]

    E --> G[Backend Menghitung Formula Risiko & Bracket Binance]
    G --> H[Render Panel Hasil Simulasi:]
    
    subgraph ResultsPanel ["Panel Hasil Simulasi"]
        H --> R1[Recommended Position Size: 0.045 BTC / $2,250 USDT]
        H --> R2[Required Margin: $112.50 USDT]
        H --> R3[Estimated Liquidation Price: $47,850.00]
        H --> R4[Status Keamanan: Badge Hijau SAFE]
    end

    G --> I{Apakah Leverage Mengalami Downscaling?}
    I -- Ya --> J[Tampilkan Alert Kuning: 'Leverage diturunkan dari 50x ke 20x sesuai batasan bracket Binance']
    I -- Tidak --> K[Leverage Tetap pada Angka Rekomendasi Normal]
```

---

### 👁️ FLOW-07: Manajemen Watchlist & Sinkronisasi Instrumen Binance

Alur pengaktifan instrumen perdagangan kripto dan sinkronisasi aturan exchange 1-klik.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Trader Admin
    participant UI as Watchlist Component
    participant API as Backend API

    Admin->>UI: Buka Menu "Watchlist & Instruments"
    UI->>API: GET /api/v1/watchlist
    API-->>UI: 200 OK (Daftar Koin, Status Aktif, Max Leverage)
    UI-->>Admin: Render Grid Kartu Koin & Toggle Switch

    Note over Admin,UI: Skenario 1: Toggle Koin Aktif / Non-Aktif
    Admin->>UI: Klik Toggle pada "SOLUSDT" (Ubah jadi Non-Aktif)
    UI->>UI: Update Optimistic UI (Switch Berubah Abu-abu)
    UI->>API: POST /api/v1/watchlist/toggle (Body: {"symbol": "SOLUSDT", "is_active": false})
    API-->>UI: 200 OK (WatchlistUpdatedDTO)
    UI-->>Admin: Toast Notifikasi: "SOLUSDT dinonaktifkan dari watchlist"

    Note over Admin,UI: Skenario 2: Sinkronisasi Aturan Exchange dari Binance
    Admin->>UI: Klik Tombol "Sync from Binance Exchange"
    UI->>UI: Tombol Berubah Menjadi Loading Spinner (Disabled)
    UI->>API: POST /api/v1/instruments/sync
    API-->>UI: 200 OK (Recap: 35 instrumen disinkronkan)
    UI->>API: GET /api/v1/watchlist (Refetch Data Terbaru)
    API-->>UI: 200 OK
    UI-->>Admin: Toast Sukses Hijau: "Sinkronisasi instrumen Binance berhasil"
```

---

### 🚨 FLOW-08: Operasional Bot, Pause/Resume & 2-Step Panic Close

Alur komando status operasional bot trading dan tindakan darurat penutupan seluruh posisi pasar saat terjadi *flash crash*.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Trader Admin
    participant UI as Bot Control Panel
    participant Modal as Panic Close Modal (2-Step)
    participant API as Backend /api/v1/bot
    participant WS as WebSocket Broker

    Note over Admin,UI: Skenario 1: Pause / Resume Bot Biasa
    Admin->>UI: Klik Tombol "Pause Trading Bot"
    UI->>API: POST /api/v1/bot/pause
    API-->>UI: 200 OK ("Bot paused successfully")
    WS-->>UI: Event BOT_STATUS_CHANGED (is_paused: true)
    UI-->>Admin: Banner Status Berubah Menjadi "🟡 PAUSED"

    Note over Admin,UI: Skenario 2: Tindakan Darurat PANIC CLOSE ALL
    Admin->>UI: Klik Tombol Merah Besar "PANIC CLOSE ALL"
    UI->>Modal: Buka Modal Peringatan Bahaya
    Modal-->>Admin: Tampilkan Peringatan: "Aksi ini menutup SEMUA posisi & batalkan SEMUA order!"
    Note over Modal: Tombol Submit "EXECUTE PANIC" Terkunci Mati (Disabled)
    
    Admin->>Modal: Centang Checkbox [x] "Saya mengonfirmasi tindakan darurat ini"
    Modal-->>Modal: Tombol Submit Menjadi AKTIF (Merah Menyala)
    Admin->>Modal: Klik "EXECUTE PANIC"
    Modal->>API: POST /api/v1/bot/panic (Body: {"confirmation": true})
    API-->>Modal: 200 OK (PanicCloseResponse: 4 trades closed, 12 orders cancelled)
    WS-->>UI: Event CIRCUIT_BREAKER_TRIGGERED & BOT_STATUS_CHANGED
    Modal-->>Admin: Tampilkan Hasil Rekap Eksekusi Darurat
    UI->>UI: Kosongkan Tabel Posisi Aktif & Ubah Status Bot Jadi PAUSED
```

---

### 📋 FLOW-09: Penelusuran Audit Log & Ekspor Laporan CSV

Alur pemantauan log internal berbasis severity dan pengunduhan laporan riwayat transaksi berformat CSV.

```mermaid
flowchart TD
    A[User Membuka Menu System Logs & Reports] --> B{Aksi yang Dipilih?}

    B -- 1. Memantau Log Sistem --> C1[Pilih Filter Level: ALL / INFO / WARNING / ERROR]
    C1 --> C2[Input Pencarian Trace ID: misal 'sig-101']
    C2 --> C3[GET /api/v1/logs?level=ERROR&trace_id=sig-101]
    C3 --> C4[Render Baris Log Monospaced dengan Warna Severity di Terminal]

    B -- 2. Mengunduh Laporan Transaksi CSV --> D1[Pilih Start Date & End Date pada Datepicker]
    D1 --> D2{Validasi: Start Date <= End Date?}
    D2 -- Tidak --> D3[Tampilkan Pesan Error: 'Start date tidak boleh melebihi End date']
    D2 -- Ya --> D4[User Klik Tombol 'Export CSV Report']
    D4 --> D5[GET /api/v1/reports/export/csv?start_date=...&end_date=...]
    D5 --> D6[Browser Menerima File Stream Binary RFC 4180]
    D6 --> D7[File closed_trades_report_YYYYMMDD_YYYYMMDD.csv Otomatis Terunduh]
```

---

### 🌐 FLOW-10: Siklus Hidup WebSocket, Heartbeat & Auto-Reconnect

Alur ketahanan konektivitas streaming dua arah dari koneksi awal, *ping/pong keepalive*, hingga *exponential backoff reconnect* dan *REST polling fallback*.

```mermaid
stateDiagram-v2
    [*] --> Disconnected : Aplikasi Dimuat
    
    Disconnected --> Connecting : Buka ws://<host>/api/v1/ws?token=<JWT>
    Connecting --> Connected : Handshake 101 Sukses (Event CONNECTED Diterima)
    Connecting --> AuthFailed : Token Expired / Invalid (Close Code 1008)
    
    AuthFailed --> Disconnected : Trigger Silent Refresh Token REST API
    
    Connected --> PingPongLoop : Setiap Interval 30 Detik
    state PingPongLoop {
        [*] --> SendPing : Kirim Text "ping"
        SendPing --> AwaitPong : Menunggu Respons
        AwaitPong --> PongReceived : Terima JSON {"event": "PONG"}
        PongReceived --> [*] : Reset Timer 30s
    }

    Connected --> Reconnecting : Koneksi Putus (onclose / onerror)
    
    state Reconnecting {
        [*] --> Attempt1 : Tunggu 1s -> Retry Connect
        Attempt1 --> Attempt2 : Gagal -> Tunggu 2s -> Retry
        Attempt2 --> Attempt3 : Gagal -> Tunggu 4s -> Retry
        Attempt3 --> Attempt4 : Gagal -> Tunggu 8s -> Retry
        Attempt4 --> Attempt5 : Gagal -> Tunggu 16s -> Retry
        Attempt5 --> FallbackPolling : Gagal 5x Berturut-turut
    }

    Reconnecting --> Connected : Reconnect Berhasil -> Refetch Cache State
    
    state FallbackPolling {
        [*] --> RestPoll : Trigger GET /analytics/summary & /trades/active Setiap 10s
        RestPoll --> RestPoll : Lanjutkan Polling Berkala
    }

    FallbackPolling --> Connecting : Jaringan Pulih -> Coba Buka WebSocket Lagi
```

---

## 3. Matriks Error & Recovery Actions

| Kondisi Error / Interupsi | Deteksi oleh Frontend | Tindakan Pemulihan Otomatis (*Recovery Action*) | Umpan Balik Visual ke Pengguna |
| :--- | :--- | :--- | :--- |
| **Token Access Expired** | HTTP 401 dari endpoint REST | Axios interceptor memanggil `/auth/refresh` secara transparan lalu me-replay request. | Tidak ada gangguan (Seamless). |
| **Refresh Token Expired** | HTTP 401 dari endpoint `/auth/refresh` | Hapus sesi dari memory state dan redirect ke `/login`. | Toast: *"Sesi Anda telah kedaluwarsa. Silakan login kembali."* |
| **Koneksi WebSocket Putus** | Event `onclose` pada client WebSocket | Jalankan algoritma *Exponential Backoff Reconnect* (1s..30s). | Badge navbar kuning berkedip: `🟡 Reconnecting in 3s...`. |
| **Server WebSocket Offline** | Gagal rekoneksi 5 kali berturut-turut | Aktifkan *REST Polling Fallback Mode* setiap 10 detik. | Badge navbar merah: `🔴 Offline (Polling Active)`. |
| **Eksekusi Sinyal Gagal (Exchange Margin Error)** | HTTP 400 dari `/signals/manual-execute` | Tangkap pesan error dari Binance, pertahankan form modal terbuka agar user bisa menyesuaikan parameter. | Alert box merah pada modal wizard dengan rincian error Binance. |
| **Tab Browser Masuk Mode Tidur (*Sleep*)** | Event `visibilitychange` (tab kembali aktif) | Evaluasi koneksi WebSocket; jika stale, paksa reconnect dan trigger refetch query cache. | Indikator loading halus sejenak saat data diperbarui. |
