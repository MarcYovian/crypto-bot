# Feature Specifications Document (FEATURES.md)
**Project**: SMC CryptoBot – Professional Binance Futures Trading Dashboard  
**Document**: Frontend Feature Catalog (`FEATURES.md`)  
**Version**: 2.0.0  
**Status**: Approved / In Development  
**Target Platform**: Web Frontend (Next.js 14 / Vite React + TypeScript)  
**Related Documents**: [docs/frontend/PRD.md](file:///home/rodex/Documents/cell/projects/crypto-bot/docs/frontend/PRD.md) | [docs/frontend/REQUIREMENTS.md](file:///home/rodex/Documents/cell/projects/crypto-bot/docs/frontend/REQUIREMENTS.md)  

---

## 1. Daftar Katalog Fitur

| Kode Fitur | Nama Fitur | Modul Terkait | Target Pengguna |
| :---: | :--- | :--- | :---: |
| **FEAT-01** | Autentikasi, Manajemen Sesi & RBAC Security | Auth & Security | Admin, Viewer |
| **FEAT-02** | Ringkasan Portofolio & Grafik Kurva Ekuitas Interaktif | Analytics & Overview | Admin, Viewer |
| **FEAT-03** | Manajemen Posisi Aktif & Take Profit Milestone Tracker | Active Trades | Admin, Viewer |
| **FEAT-04** | Riwayat Closed Trades & Modal Inspeksi Hierarki 5-Level | Trade History | Admin, Viewer |
| **FEAT-05** | Live Telegram Signal Feed & 1-Click Execution Wizard | Signals & Execution | Admin (Exec), Viewer (Read) |
| **FEAT-06** | Watchlist Manager & Sinkronisasi Instrumen Binance | Instruments & Config | Admin (Mutate), Viewer (Read) |
| **FEAT-07** | Risk Simulator & Dynamic Leverage Sandbox | Calculator Sandbox | Admin, Viewer |
| **FEAT-08** | Bot Operations Command, Circuit Breaker & Credential Vault | Bot Operations | Admin (Control), Viewer (Read) |
| **FEAT-09** | System Audit Log Terminal & Generator Laporan CSV | Logs & Reporting | Admin, Viewer |
| **FEAT-10** | Duplex Real-Time WebSocket Streaming & Event Broker | Real-Time Sync | Admin, Viewer |

---

## 2. Spesifikasi Rinci Setiap Fitur

---

### 🔐 FEAT-01: Autentikasi, Manajemen Sesi & RBAC Security

#### 1. Deskripsi Singkat Fitur:
Gerbang keamanan akses dashboard berbasis JSON Web Token (JWT) yang mengelola otentikasi pengguna, isolasi token di memory, pembaruan sesi otomatis (*silent token refresh*) saat access token ($15\text{ menit}$) habis masa berlakunya, pemutusan sesi aman (*auto-logout*), serta pembatasan elemen antarmuka berdasarkan peran pengguna (`ADMIN` vs `VIEWER`).

#### 2. User Stories:
* **US-01.1**: *Sebagai Trader Admin*, saya ingin login menggunakan kredensial saya dan mendapatkan akses penuh ke seluruh kontrol trading dan konfigurasi bot, agar saya dapat mengelola perdagangan dengan aman.
* **US-01.2**: *Sebagai Observer / Viewer*, saya ingin login dengan kredensial viewer dan dapat memantau data posisi serta analitik tanpa bisa mengubah pengaturan bot atau mengeksekusi order, agar portofolio tetap terlindungi dari modifikasi yang tidak diinginkan.
* **US-01.3**: *Sebagai Pengguna Aktif*, saya ingin sesi login saya diperbarui secara otomatis di latar belakang tanpa mengganggu aktivitas saya di layar, agar saya tidak perlu login ulang berulang kali setiap 15 menit.

#### 3. Acceptance Criteria (Kriteria Keberhasilan):
* **AC-01.1 (Login Sukses)**:
  * **Given** pengguna berada di halaman `/login`.
  * **When** pengguna memasukkan username dan password valid lalu mengklik tombol *Sign In*.
  * **Then** sistem memanggil `POST /api/v1/auth/login`, menyimpan `access_token` di memory state dan `refresh_token` di secure storage, lalu me-redirect pengguna ke halaman `/dashboard` serta menampilkan notifikasi selamat datang.
* **AC-01.2 (Kredensial Salah)**:
  * **Given** pengguna memasukkan password salah.
  * **When** pengguna mengklik tombol *Sign In*.
  * **Then** tombol kembali aktif dari loading state, form tidak di-reset total, dan pesan alert merah muncul: *"Invalid username or password"*.
* **AC-01.3 (Silent Token Refresh)**:
  * **Given** access token pengguna telah kedaluwarsa ($> 15\text{ menit}$).
  * **When** pengguna melakukan request REST API (misal: membuka tab Watchlist).
  * **Then** Axios interceptor menangkap HTTP 401, secara otomatis memanggil `POST /api/v1/auth/refresh`, memperbarui access token baru di memory, dan mengulang request watchlist tanpa memunculkan popup error ke pengguna.
* **AC-01.4 (Pembatasan Peran RBAC)**:
  * **Given** pengguna login dengan peran `VIEWER`.
  * **Then** tombol *Execute Signal*, *Panic Close*, *Pause/Resume Bot*, *Sync Instruments*, dan halaman `/settings` disembunyikan atau dinonaktifkan dengan badge tooltip *"Hanya untuk Admin"*.

#### 4. Edge Cases & Error Handling:
* **EC-01.1 (Refresh Token Expired / Blacklisted)**: Jika refresh token ($7\text{ hari}$) telah kedaluwarsa atau di-revoke oleh server, request refresh mengembalikan HTTP 401 $\rightarrow$ State autentikasi dibersihkan, pengguna di-redirect seketika ke `/login`, dan muncul toast: *"Sesi Anda telah kedaluwarsa. Silakan login kembali."*
* **EC-01.2 (Multiple Concurrent Requests saat Token Expired)**: Jika 5 request API ditembakkan bersamaan saat token expired $\rightarrow$ Axios interceptor menggunakan *Promise queue lock* sehingga endpoint `/auth/refresh` hanya dipanggil **tepat 1 kali**, dan kelima request di-replay bersamaan setelah token baru diperoleh.
* **EC-01.3 (Manipulasi LocalStorage Manual)**: Jika user secara ilegal mengedit payload role di client-side menjadi `ADMIN` $\rightarrow$ Setiap mutasi API tetap diverifikasi secara kriptografis oleh backend dan mengembalikan HTTP 403 Forbidden.

---

### 📊 FEAT-02: Ringkasan Portofolio & Grafik Kurva Ekuitas Interaktif

#### 1. Deskripsi Singkat Fitur:
Panel analitik eksekutif di beranda dashboard yang menyajikan 6 kartu metrik performa utama (Total Balance, Free Margin, Daily PnL, Win Rate, Profit Factor, Sisa Daily Risk Budget) serta grafik kurva ekuitas interaktif (*TradingView Lightweight Charts*) dengan selector rentang waktu dan tooltip hover multi-dimensi.

#### 2. User Stories:
* **US-02.1**: *Sebagai Trader Admin*, saya ingin melihat total saldo USDT, margin bebas, dan PnL harian secara real-time saat membuka dashboard, agar saya dapat segera mengetahui kondisi likuiditas dan performa akun hari ini.
* **US-02.2**: *Sebagai Trader*, saya ingin melihat sisa toleransi risiko harian (*Daily Risk Budget Remaining*) sebelum batas Circuit Breaker aktif, agar saya tahu berapa alokasi kerugian yang masih aman untuk trade berikutnya.
* **US-02.3**: *Sebagai Investor*, saya ingin memeriksa grafik kurva pertumbuhan ekuitas dalam rentang 1D, 7D, 30D, dan ALL, agar saya dapat mengevaluasi konsistensi pertumbuhan portofolio secara visual.

#### 3. Acceptance Criteria:
* **AC-02.1 (Penyajian Summary KPI Cards)**:
  * **Given** user berada di dashboard utama.
  * **When** endpoint `GET /api/v1/analytics/summary` selesai di-fetch.
  * **Then** 6 kartu metrik terisi dengan format angka rapi:
    * Total Balance & Free Margin dalam format mata uang `$X,XXX.XX USDT` (Font Monospaced).
    * Daily PnL menampilkan nominal dan persentase dengan warna dinamis (Hijau `#10B981` jika $\ge 0$, Merah `#EF4444` jika $< 0$).
    * Win Rate menampilkan persentase dan total transaksi (misal: `68.5% (45 trades)`).
    * Sisa Budget Risiko Harian menampilkan nominal tersisa sebelum circuit breaker auto-pause aktif.
* **AC-02.2 (Interaktivitas Grafik Ekuitas)**:
  * **Given** user mengklik filter waktu `7D` pada grafik kurva ekuitas.
  * **When** request `GET /api/v1/analytics/equity-curve` selesai.
  * **Then** grafik memplot titik-titik ekuitas 7 hari terakhir secara mulus dengan area gradient hijau/biru gelap, dan tooltip menampilkan detail saat kursor mouse di-hover di atas kanvas grafik.
* **AC-02.3 (Real-Time Invalidation)**:
  * **Given** sebuah trade baru saja ditutup di Binance (`TRADE_CLOSED` event diterima via WebSocket).
  * **Then** widget summary cards dan grafik kurva ekuitas otomatis melakukan refetch dan memperbarui angka dalam waktu $< 50\text{ms}$ tanpa me-reload halaman.

#### 4. Edge Cases & Error Handling:
* **EC-02.1 (Akun Baru / Zero Trade History)**: Jika akun baru belum memiliki histori transaksi tertutup $\rightarrow$ Win Rate menampilkan `0.0% (0 trades)`, Profit Factor menampilkan `0.00`, dan grafik ekuitas menampilkan garis datar setinggi initial balance tanpa crash.
* **EC-02.2 (Extreme Drawdown Alert)**: Jika kerugian hari ini mendekati $> 80\%$ dari batas toleransi harian $\rightarrow$ Kartu *Daily Risk Budget* berkedip kuning/amber memberi peringatan dini sebelum bot ter-pause otomatis.
* **EC-02.3 (Network Timeout saat Fetching Chart)**: Jika koneksi lambat saat load chart $\rightarrow$ Skeleton loading placeholder beranimasi tampil, dan jika timeout muncul tombol *Retry Load Chart*.

---

### ⚡ FEAT-03: Manajemen Posisi Aktif & Take Profit Milestone Tracker

#### 1. Deskripsi Singkat Fitur:
Tabel pemantauan posisi terbuka secara real-time yang memperlihatkan arah posisi, ukuran lot, leverage, harga likuidasi, Stop Loss dinamis (Initial SL, BEP, atau Trailing SL), kalkulasi unrealized PnL live, serta visual progress bar Take Profit 3-tingkat (TP1 50%, TP2 30%, TP3 20%) dan tombol *Manual Market Close*.

#### 2. User Stories:
* **US-03.1**: *Sebagai Trader*, saya ingin melihat seluruh posisi yang sedang aktif berjalan lengkap dengan unrealized PnL yang diperbarui secara live, agar saya selalu mengetahui status floating profit/loss terkini.
* **US-03.2**: *Sebagai Trader*, saya ingin melihat progres pencapaian level TP1, TP2, dan TP3 dalam bentuk progress bar visual, agar saya tahu berapa persen posisi yang telah terealisasi dan apakah Stop Loss telah digeser ke Break-Even (BEP).
* **US-03.3**: *Sebagai Trader Admin*, saya ingin dapat menutup posisi market darurat secara individual melalui satu tombol, agar saya dapat mengamankan profit atau memotong kerugian saat ada berita dadakan.

#### 3. Acceptance Criteria:
* **AC-03.1 (Visualisasi Tabel Posisi Aktif)**:
  * **Given** ada trade berstatus `ACTIVE` atau `PARTIALLY_FILLED`.
  * **Then** tabel menampilkan baris trade dengan kolom Symbol (misal: `BTCUSDT`), Side (`BUY` hijau / `SELL` merah), Entry Price, Mark Price, Position Size, Leverage (`20x Isolated`), SL Price, dan Floating PnL.
* **AC-03.2 (Visualisasi Take Profit Milestones)**:
  * **Given** sebuah trade telah mengenai target harga TP1.
  * **Then** indikator milestone `TP1 (50%)` berubah warna menjadi hijau terang dengan ikon centang, badge status SL berubah menjadi `BEP_SL`, dan volume remaining size berkurang sesuai porsi.
* **AC-03.3 (Eksekusi Manual Market Close)**:
  * **Given** Trader Admin mengklik tombol *Close* pada baris trade aktif.
  * **When** modal konfirmasi muncul dan tombol *Confirm Close* diklik.
  * **Then** sistem memanggil `POST /api/v1/trades/{id}/close`, menampilkan loading spinner pada tombol, dan setelah sukses trade langsung berpindah dari tabel posisi aktif ke riwayat transaksi tertutup.

#### 4. Edge Cases & Error Handling:
* **EC-03.1 (Trade Telah Ditutup oleh Exchange saat User Menekan Tombol Close)**: Jika posisi baru saja tersentuh SL di Binance bersamaan saat user mengklik close manual $\rightarrow$ Server mengembalikan HTTP 400 (*"Trade is already CLOSED"*), frontend menangkap error ini dengan elegan dan menampilkan toast info: *"Posisi telah ditutup oleh sistem (SL Hit)"* lalu merefresh tabel posisi aktif.
* **EC-03.2 (Harga Mark Bergerak Cepat / High Volatility)**: Terapkan throttling render ($100\text{ms}$) pada kalkulasi floating PnL agar tidak menyebabkan browser freeze saat ribuan ticker update masuk per detik.
* **EC-03.3 (Tidak Ada Posisi Terbuka)**: Tampilkan ilustrasi empty state yang elegan: *"Tidak ada posisi aktif saat ini. Bot sedang standby menunggu sinyal valid."*

---

### 📜 FEAT-04: Riwayat Closed Trades & Modal Inspeksi Hierarki 5-Level

#### 1. Deskripsi Singkat Fitur:
Tabel riwayat perdagangan komprehensif yang memuat seluruh transaksi yang telah selesai (`CLOSED` atau `CANCELLED`), dilengkapi kontrol pagination, filter simbol, filter hasil (`WIN`, `LOSS`, `BREAKEVEN`), filter provider sinyal, serta modal inspeksi rincian mendalam 5-level (Overview, Risk Allocation, Order Lifecycle, Executions, dan Financial Summary).

#### 2. User Stories:
* **US-04.1**: *Sebagai Trader / Investor*, saya ingin menelusuri riwayat transaksi masa lalu dengan filter berdasarkan pasangan koin dan hasil trade (Win/Loss), agar saya dapat mengevaluasi performa perdagangan secara terfokus.
* **US-04.2**: *Sebagai Trader Admin / Auditor*, saya ingin mengklik sebuah baris transaksi dan melihat seluruh riwayat pesanan exchange, fill eksekusi parsial, dan rincian komisi hingga tingkat mikro, agar saya memiliki audit trail yang transparan dan dapat dipertanggungjawabkan.

#### 3. Acceptance Criteria:
* **AC-04.1 (Tabel Riwayat Terpaginasi & Filter)**:
  * **Given** user berada di tab Trade History.
  * **When** user memilih filter Result = `WIN` dan Symbol = `BTCUSDT`.
  * **Then** tabel memanggil `GET /api/v1/trades/history?result=WIN&symbol=BTCUSDT&page=1&page_size=10` dan menyajikan data terfilter beserta navigasi pagination yang akurat.
* **AC-04.2 (Modal Inspeksi 5-Level Detail Tree)**:
  * **Given** user mengklik salah satu baris trade pada tabel riwayat.
  * **When** endpoint `GET /api/v1/trades/{id}` selesai dimuat.
  * **Then** modal dialog muncul menyajikan 5 seksi terstruktur:
    1. **Overview**: Tanggal buka/tutup, durasi aktif, close reason (`TP3_HIT`, `SL_HIT`, dll).
    2. **Risk Parameters**: Nominal modal berisiko ($), toleransi stop distance, leverage bracket.
    3. **Order Lifecycle**: Daftar order `ENTRY`, `TP1`, `TP2`, `TP3`, `SL` beserta client & exchange order ID.
    4. **Executions**: Waktu fill aktual, harga fill, komisi exchange, dan fee asset.
    5. **Financial Summary**: Gross PnL, Komisi, Net PnL, ROI %, dan rasio Risk-to-Reward (RR).

#### 4. Edge Cases & Error Handling:
* **EC-04.1 (Trade Dibatalkan Sebelum Entry Terisi / Cancelled)**: Tab Executions dan Financial Summary menampilkan badge `CANCELLED - NO FILLS RECORDED` secara bersih tanpa menyebabkan error kalkulasi pembagian nol (division by zero).
* **EC-04.2 (Navigasi ke Halaman di Luar Total Halaman)**: Jika user mengubah page size sehingga total halaman berkurang $\rightarrow$ Pagination state otomatis me-reset halaman aktif kembali ke halaman 1.
* **EC-04.3 (Trade ID Tidak Ditemukan)**: Jika membuka link modal dengan ID tidak valid $\rightarrow$ Tampilkan pesan error modal: *"Trade #9999 tidak ditemukan"* disertai tombol *Kembali ke Riwayat*.

---

### 🎯 FEAT-05: Live Telegram Signal Feed & 1-Click Execution Wizard

#### 1. Deskripsi Singkat Fitur:
Aliran data sinyal trading real-time yang diekstrak dan di-parsing dari channel Telegram, disajikan dengan kartu status visual (`PARSED`, `EXECUTED`, `REJECTED`, `EXPIRED`, `SKIPPED`), serta modal wizard eksekusi 1-klik yang memvalidasi kepatuhan batas risiko maksimal 2% modal dan geometri harga sebelum order dikirim ke Binance.

#### 2. User Stories:
* **US-05.1**: *Sebagai Trader*, saya ingin melihat sinyal-sinyal trading yang baru saja masuk dari channel Telegram dalam format kartu yang rapi dan terstruktur, agar saya dapat meninjau peluang pasar tanpa membuka aplikasi Telegram.
* **US-05.2**: *Sebagai Trader Admin*, saya ingin mengeksekusi sinyal trading dengan 1 klik melalui wizard yang secara otomatis menghitung lot size dan leverage yang aman sesuai saldo akun saya, agar proses eksekusi berlangsung $< 2\text{ detik}$ tanpa risiko salah hitung.
* **US-05.3**: *Sebagai Risk Manager*, saya ingin sistem menolak dan mengunci tombol eksekusi jika saya memasukkan parameter yang menyebabkan risiko modal melebihi batas 2%, agar akun trading terlindung dari risiko kehancuran (*risk of ruin*).

#### 3. Acceptance Criteria:
* **AC-05.1 (Penyajian Kartu Sinyal Live)**:
  * **Given** ada sinyal baru di-parsing dari Telegram.
  * **Then** kartu sinyal tampil di feed dengan badge provider, simbol koin, arah (`BUY`/`SELL`), rentang entry, SL, target TP1/TP2/TP3, trace ID, dan tombol *Execute Trade* jika berstatus `PARSED`.
* **AC-05.2 (Validasi Wizard & Hard 2% Risk Cap)**:
  * **Given** Trader Admin mengklik *Execute Trade* pada kartu sinyal.
  * **When** modal wizard terbuka dan menampilkan kalkulasi lot size otomatis.
  * **Then** jika parameter menghasilkan risiko $\le 2.0\%$ dari saldo akun $\rightarrow$ Tombol *Confirm & Execute* aktif dengan warna hijau.
  * **Then** jika user sengaja mengubah stop loss menjadi terlalu jauh sehingga risiko menjadi $> 2.0\%$ $\rightarrow$ Tombol *Confirm & Execute* otomatis ter-disable dan muncul peringatan merah: *"Risiko melebihi batas toleransi 2% ($20.00 USDT)"*.
* **AC-05.3 (Validasi Geometri Harga)**:
  * **Given** posisi adalah `BUY`.
  * **When** user mengedit Stop Loss menjadi lebih tinggi dari Entry Price.
  * **Then** form menampilkan error validasi: *"Stop Loss untuk posisi BUY harus berada di bawah harga Entry"*.
* **AC-05.4 (Submisi Sukses)**:
  * **Given** seluruh parameter valid dan tombol *Confirm & Execute* diklik.
  * **When** request `POST /api/v1/signals/manual-execute` berhasil.
  * **Then** modal tertutup, muncul toast sukses, status kartu sinyal berubah menjadi `EXECUTED`, dan posisi baru langsung muncul di tabel posisi aktif.

#### 4. Edge Cases & Error Handling:
* **EC-05.1 (Simbol Sinyal Tidak Ada dalam Watchlist)**: Backend mengembalikan HTTP 400 (*"Symbol is not active in watchlist"*), frontend menangkap error ini dan menampilkan prompt: *"Simbol XRPUSDT belum diaktifkan di Watchlist. Aktifkan sekarang di menu Watchlist?"*
* **EC-05.2 (Simbol Sudah Memiliki Posisi Aktif yang Berjalan)**: Backend mengembalikan HTTP 409 (*"Active trade already exists for symbol"*), frontend menampilkan toast peringatan: *"Sudah ada posisi aktif untuk pasangan ini. Hindari duplikasi posisi!"*
* **EC-05.3 (Sinyal Sudah Kedaluwarsa / Expired)**: Jika harga pasar saat ini sudah jauh melampaui TP1 $\rightarrow$ Kartu sinyal otomatis diberi watermark abu-abu `EXPIRED` dan tombol eksekusi dinonaktifkan.

---

### 👁️ FEAT-06: Watchlist Manager & Sinkronisasi Instrumen Binance

#### 1. Deskripsi Singkat Fitur:
Pusat pengaturan instrumen perdagangan kripto yang memungkinkan admin mengaktifkan atau menonaktifkan pasangan koin trading dengan tombol toggle seketika (*instant write-through*), serta tombol sinkronisasi aturan exchange (tick size, min notional, dan batas leverage bracket) langsung dari Binance.

#### 2. User Stories:
* **US-06.1**: *Sebagai Trader Admin*, saya ingin mengaktifkan koin tertentu (misal: `SOLUSDT`) dan menonaktifkan koin bervolatilitas liar (misal: `MEMEUSDT`) dengan switch toggle, agar bot hanya menerima dan memproses sinyal untuk koin yang saya setujui.
* **US-06.2**: *Sebagai Trader Admin*, saya ingin menyinkronkan seluruh instrumen dan bracket leverage dari Binance dengan 1 klik, agar aturan trading (seperti batas maksimal leverage dan ukuran lot minimum) selalu sesuai dengan aturan terbaru exchange.

#### 3. Acceptance Criteria:
* **AC-06.1 (Tampilan Grid & Search Watchlist)**:
  * **Given** user berada di menu Watchlist.
  * **When** user mengetikkan `"ETH"` pada search bar.
  * **Then** daftar instrumen terfilter secara instan menampilkan seluruh pasangan ETH dengan informasi status aktif, tier risiko, dan max leverage.
* **AC-06.2 (Instant Toggle Switch)**:
  * **Given** instrumen `BTCUSDT` dalam status aktif (`is_active = true`).
  * **When** Admin mengklik switch toggle menjadi non-aktif.
  * **Then** frontend mengirimkan `POST /api/v1/watchlist/toggle` dengan payload `{"symbol": "BTCUSDT", "is_active": false}`, switch berubah abu-abu, dan cache watchlist backend diinvaliasi seketika.
* **AC-06.3 (Sinkronisasi Instrumen dari Binance)**:
  * **Given** Admin mengklik tombol *Sync from Binance*.
  * **When** request `POST /api/v1/instruments/sync` berhasil diproses.
  * **Then** tombol menampilkan animasi loading, diikuti toast rekap sukses: *"Berhasil menyinkronkan data instrumen dan leverage bracket dari Binance."*

#### 4. Edge Cases & Error Handling:
* **EC-06.1 (Koneksi ke Binance Error saat Sync)**: Jika API Binance sedang mengalami maintenance atau rate-limit saat tombol sync diklik $\rightarrow$ Tampilkan alert toast merah: *"Gagal menyinkronkan data dari Binance. Periksa koneksi atau coba beberapa saat lagi."*
* **EC-06.2 (Menonaktifkan Koin yang Sedang Memiliki Posisi Aktif)**: Jika Admin menonaktifkan simbol yang sedang aktif ditradingkan $\rightarrow$ Tampilkan dialog konfirmasi: *"Perhatian: Ada 1 posisi aktif berjalan untuk BTCUSDT. Menonaktifkan koin tidak akan menutup posisi yang sedang berjalan, namun sinyal baru akan diabaikan. Lanjutkan?"*

---

### 🧮 FEAT-07: Risk Simulator & Dynamic Leverage Sandbox

#### 1. Deskripsi Singkat Fitur:
Kalkulator simulasi risiko interaktif bagi trader untuk menguji berbagai skenario posisi trading, mengalkulasi ukuran lot optimal, memvisualisasikan penyesuaian leverage otomatis (*dynamic leverage downscaling*) berdasarkan batas nominal bracket Binance, serta memprediksi harga likuidasi sebelum membuka posisi riil.

#### 2. User Stories:
* **US-07.1**: *Sebagai Trader*, saya ingin menguji skenario entry dan stop loss pada kalkulator simulasi, agar saya mengetahui berapa banyak lot yang aman dibeli dan berapa modal margin yang dibutuhkan.
* **US-07.2**: *Sebagai Trader*, saya ingin melihat apakah leverage yang saya inginkan akan diturunkan secara otomatis oleh exchange (*leverage downscaling*) karena ukuran posisi yang besar, agar saya tidak terkejut saat eksekusi riil.
* **US-07.3**: *Sebagai Trader*, saya ingin melihat estimasi harga likuidasi posisi sebelum trading, agar saya dapat memastikan harga likuidasi berada jauh di luar titik Stop Loss.

#### 3. Acceptance Criteria:
* **AC-07.1 (Input Simulasi Interaktif & Debounce)**:
  * **Given** user berada di tab Risk Simulator.
  * **When** user memasukkan Entry Price, Stop Loss Price, dan menggeser slider Risk % (misal: `2.0%`).
  * **Then** frontend mengirimkan request simulasi ke `POST /api/v1/calculator/simulate` dengan debounce 300ms.
* **AC-07.2 (Panel Output Hasil Simulasi)**:
  * **Given** backend merespons hasil kalkulasi.
  * **Then** panel kanan menampilkan hasil terstruktur:
    * Recommended Position Size (Koin & Notional USDT)
    * Effective Leverage (misal: `20x`)
    * Margin Required (`$112.50 USDT`)
    * Estimated Liquidation Price (Harga likuidasi)
    * Status Margin (Badge Hijau `SAFE` jika margin $\le$ saldo akun, Merah `UNSAFE` jika margin melebihi saldo).
* **AC-07.3 (Peringatan Dynamic Leverage Downscaling)**:
  * **Given** notional posisi melebihi batas tier 1 exchange (misal: $> \$50,000$).
  * **When** backend menurunkan leverage dari `50x` ke `20x`.
  * **Then** frontend menampilkan banner alert kuning: *"Leverage disesuaikan dari 50x ke 20x untuk mematuhi batas maksimal notional bracket Binance."*

#### 4. Edge Cases & Error Handling:
* **EC-07.1 (Jarak Stop Loss Nol / Entry Sama dengan SL)**: Jika user memasukkan harga SL sama persis dengan Entry $\rightarrow$ Form memunculkan validasi error lokal seketika: *"Jarak Stop Loss tidak boleh nol (Stop Distance > 0)"*.
* **EC-07.2 (Saldo Akun Nol atau Negatif)**: Jika saldo akun terisi 0 $\rightarrow$ Hasil kalkulasi menampilkan pesan: *"Saldo akun tidak mencukupi untuk melakukan simulasi posisi"*.
* **EC-07.3 (Inversi Geometri Harga)**: Jika posisi BUY tetapi SL dimasukkan lebih tinggi dari Entry $\rightarrow$ Kalkulator tidak mengirim request ke server dan menampilkan badge peringatan merah: *"Invalid Price Geometry: SL harus lebih rendah dari Entry untuk posisi BUY"*.

---

### 🚨 FEAT-08: Operasional Bot, Circuit Breaker & Credential Vault

#### 1. Deskripsi Singkat Fitur:
Pusat kendali komando status bot trading yang menampilkan hero banner status operasional terintegrasi, tombol Pause dan Resume engine, tombol aksi darurat *PANIC CLOSE ALL* dengan konfirmasi bertahap 2-langkah, serta vault pengelolaan rotasi kunci API Binance dengan fitur handshake connection test.

#### 2. User Stories:
* **US-08.1**: *Sebagai Trader Admin*, saya ingin dapat menjeda (*Pause*) dan mengaktifkan kembali (*Resume*) bot trading kapan saja dengan 1 klik, agar saya dapat menghentikan konsumsi sinyal otomatis saat kondisi pasar sedang tidak menentu.
* **US-08.2**: *Sebagai Trader Admin*, saya ingin memiliki tombol darurat *PANIC CLOSE ALL* untuk menutup semua posisi dan membatalkan semua order sekaligus dalam 1 detik saat terjadi *flash crash* pasar, agar seluruh modal terlindungi seketika.
* **US-08.3**: *Sebagai Trader Admin*, saya ingin menguji validitas API Key dan Secret Key Binance saya sebelum menyimpannya ke database, agar saya yakin bot dapat terhubung ke exchange tanpa kegagalan otentikasi.

#### 3. Acceptance Criteria:
* **AC-08.1 (Hero Status Banner Operasional)**:
  * **Given** user membuka dashboard.
  * **Then** banner atas menampilkan status Engine (`🟢 ACTIVE` atau `🟡 PAUSED`), Status WebSocket Binance (`Connected`), Status Background Scheduler (`7 Jobs Active`), dan Circuit Breaker State (`Normal` atau `🚨 TRIPPED`).
* **AC-08.2 (Pause & Resume Action)**:
  * **Given** bot dalam status `ACTIVE`.
  * **When** Admin mengklik *Pause Bot*.
  * **Then** sistem memanggil `POST /api/v1/bot/pause`, banner berubah menjadi `🟡 PAUSED`, dan toast konfirmasi muncul: *"Trading bot berhasil dijeda. Sinyal baru akan ditolak."*
* **AC-08.3 (Emergency Panic Close All Modal 2-Langkah)**:
  * **Given** Admin mengklik tombol merah *PANIC CLOSE ALL*.
  * **When** modal darurat terbuka.
  * **Then** tombol submit *EXECUTE PANIC CLOSE* terkunci mati hingga Admin mencentang checkbox: `[x] Saya mengerti aksi ini akan menutup seluruh posisi aktif dan membatalkan seluruh order`.
  * **When** checkbox tercentang dan submit diklik $\rightarrow$ Backend mengeksekusi `POST /api/v1/bot/panic` dengan payload `{"confirmation": true}`, seluruh posisi tertutup, dan modal menampilkan rekap: *"Berhasil menutup 4 posisi dan membatalkan 12 order aktif."*
* **AC-08.4 (Credential Handshake Test)**:
  * **Given** Admin memasukkan API Key dan Secret Key baru.
  * **When** Admin mengklik tombol *Test Handshake*.
  * **Then** sistem memanggil `POST /api/v1/credentials`, memverifikasi koneksi ke Binance, dan menampilkan saldo exchange riil sebagai bukti koneksi berhasil sebelum menyimpan.

#### 4. Edge Cases & Error Handling:
* **EC-08.1 (Panic Close Tanpa Posisi Aktif)**: Jika tombol panic close dijalankan saat tidak ada posisi aktif $\rightarrow$ Sistem tetap membatalkan order terbuka yang menggantung dan menampilkan pesan rekap: *"0 posisi ditutup, 3 order dibatalkan."*
* **EC-08.2 (Kredensial API Key Binance Tidak Valid / Expired IP Whitelist)**: Saat test handshake gagal karena IP restriction $\rightarrow$ Tampilkan alert error spesifik dari Binance: *"Exchange Authentication Failed: Invalid API Key or IP restriction error (-2015)"*.
* **EC-08.3 (Circuit Breaker Tripped Otomatis oleh Backend)**: Jika batas kerugian harian terlampaui di backend $\rightarrow$ Event `CIRCUIT_BREAKER_TRIGGERED` diterima via WebSocket, dashboard menampilkan popup banner merah mencolok: *"🚨 DAILY LOSS LIMIT REACHED! Bot otomatis di-PAUSE hingga reset harian."*

---

### 📋 FEAT-09: System Audit Log Terminal & Generator Laporan CSV

#### 1. Deskripsi Singkat Fitur:
Antarmuka penampil audit log sistem bergaya terminal gelap monospaced dengan syntax highlighting berbasis severity log, filter level instan, penelusuran korelasi `trace_id` sinyal, serta form generator unduh laporan riwayat closed trades berformat CSV berstandar RFC 4180.

#### 2. User Stories:
* **US-09.1**: *Sebagai Trader / Developer*, saya ingin memantau log sistem internal secara live dengan filter level error/warning, agar saya dapat mendiagnosis masalah atau memastikan aliran eksekusi sinyal berjalan normal.
* **US-09.2**: *Sebagai Trader / Akuntan*, saya ingin mengunduh laporan transaksi tertutup dalam format CSV untuk rentang tanggal tertentu, agar saya dapat melakukan pembukuan keuangan dan pelaporan pajak perdagangan dengan mudah.

#### 3. Acceptance Criteria:
* **AC-09.1 (Penampil Terminal Audit Log)**:
  * **Given** user membuka menu System Logs.
  * **When** endpoint `GET /api/v1/logs` dimuat.
  * **Then** baris log ditampilkan dalam font monospaced dengan warna dinamis: `DEBUG` (abu-abu), `INFO` (biru), `WARNING` (kuning), `ERROR` (merah).
* **AC-09.2 (Filter Log & Search Trace ID)**:
  * **Given** user memilih filter level `ERROR` dan mengetikkan `trace_id = "sig-101"`.
  * **When** request log dieksekusi.
  * **Then** terminal hanya menampilkan baris log error yang berkorelasi dengan sinyal tersebut.
* **AC-09.3 (Unduh Laporan CSV Transaksi)**:
  * **Given** user memilih rentang tanggal `Start Date: 2026-08-01` dan `End Date: 2026-08-24`.
  * **When** user mengklik tombol *Export CSV Report*.
  * **Then** sistem memanggil `GET /api/v1/reports/export/csv?start_date=...&end_date=...`, browser langsung memulai unduhan file dengan nama `closed_trades_report_20260801_20260824.csv`, dan file memuat kolom: Trade ID, Symbol, Side, Entry Price, Close Price, Net PnL, Commission, ROI %, Result, Close Reason, dan Closed At.

#### 4. Edge Cases & Error Handling:
* **EC-09.1 (Rentang Tanggal Terbalik / Start Date > End Date)**: Jika user memilih Start Date lebih besar dari End Date $\rightarrow$ Datepicker menampilkan validasi error lokal: *"Start Date tidak boleh lebih besar dari End Date"*, dan tombol unduh ter-disable.
* **EC-09.2 (Dataset Laporan Kosong / No Closed Trades in Range)**: Jika tidak ada transaksi pada rentang tanggal tersebut $\rightarrow$ Backend mengembalikan file CSV yang hanya berisi header kolom, frontend tetap mengunduh file tersebut dan menampilkan toast info: *"Tidak ada transaksi tertutup pada periode yang dipilih."*

---

### 🌐 FEAT-10: Duplex Real-Time WebSocket Streaming & Resilient Event Broker

#### 1. Deskripsi Singkat Fitur:
Mesin konektivitas streaming dua arah yang mengelola siklus hidup koneksi WebSocket ke `/api/v1/ws?token=<JWT>`, mengorkestrasi *heartbeat ping/pong* berkala, melakukan rekoneksi otomatis berdaya tahan tinggi (*exponential backoff*), serta mendistribusikan event real-time (order fill, TP/SL hit, trade closed, status bot) ke seluruh komponen UI secara instan.

#### 2. User Stories:
* **US-10.1**: *Sebagai Trader*, saya ingin dashboard saya memperbarui data posisi, saldo, dan alert secara real-time tanpa perlu saya menekan tombol refresh (F5), agar saya tidak ketinggalan momen pergerakan harga atau eksekusi order di pasar.
* **US-10.2**: *Sebagai Trader*, saya ingin sistem secara otomatis menyambung kembali jika koneksi internet saya terputus sejenak, dan memberikan indikator visual yang jelas atas status koneksi, agar saya selalu yakin data di layar adalah data live.

#### 3. Acceptance Criteria:
* **AC-10.1 (Koneksi Handshake Otomatis)**:
  * **Given** user berhasil login dan memiliki token JWT valid.
  * **When** aplikasi web dimuat.
  * **Then** client WebSocket membuka koneksi ke `ws://<host>/api/v1/ws?token=<JWT>`, menerima event `CONNECTED`, dan badge navbar berubah menjadi `🟢 Real-Time Connected`.
* **AC-10.2 (Heartbeat Keep-Alive Protocol)**:
  * **Given** koneksi WebSocket sedang aktif.
  * **Then** client secara otomatis mengirimkan teks `"ping"` setiap 30 detik, dan server membalas dengan JSON `{"event": "PONG", "data": {"status": "alive"}}`.
* **AC-10.3 (Resilient Auto-Reconnect)**:
  * **Given** koneksi internet terputus atau server restart sejenak.
  * **When** event `onclose` atau `onerror` terpicu.
  * **Then** client mengubah badge navbar menjadi `🟡 Reconnecting in Xs...` dan mencoba menyambung ulang dengan interval exponential backoff (1s, 2s, 4s, 8s, 16s, maks 30s) hingga tersambung kembali.
* **AC-10.4 (Event Dispatching & UI Update)**:
  * **Given** event WebSocket `TP_HIT` diterima dari server.
  * **Then** komponen Active Trades mengupdate milestone progress bar TP menjadi hijau seketika, dan toast alert profit muncul di sudut kanan atas layar dalam waktu $< 30\text{ms}$.

#### 4. Edge Cases & Error Handling:
* **EC-10.1 (Token Kedaluwarsa saat Handshake WebSocket)**: Jika token JWT sudah expired saat mencoba membuka WebSocket $\rightarrow$ Server menolak koneksi dengan close code `1008`, frontend menangkap event ini, memicu *silent refresh token* via REST API, lalu membuka kembali koneksi WebSocket dengan token baru.
* **EC-10.2 (Browser Tab Sleep / Background Inactive)**: Jika browser menidurkan tab (background throttling) lalu tab dibuka kembali $\rightarrow$ Client mendeteksi koneksi stale dan melakukan re-sync data instan dengan memicu refetch query cache TanStack Query.
* **EC-10.3 (WebSocket Server Down Berkepanjangan)**: Jika setelah 5x percobaan reconnect WebSocket masih gagal $\rightarrow$ Frontend beralih otomatis ke *REST Polling Fallback Mode* (interval fetch setiap 10 detik) dan badge navbar menampilkan: `🔴 Offline (Polling Active)`.

---

## 3. Matriks Hubungan Fitur, Endpoint API & WebSocket Event

| Kode Fitur | Endpoint REST API Terkait | WebSocket Event yang Dikonsumsi | Komponen UI Utama |
| :---: | :--- | :--- | :--- |
| **FEAT-01** | `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` | - | `LoginForm`, `AuthGuard`, `UserMenuBadge` |
| **FEAT-02** | `GET /analytics/summary`, `GET /analytics/equity-curve` | `TRADE_CLOSED`, `CIRCUIT_BREAKER_TRIGGERED` | `SummaryKPICards`, `EquityCurveChart` |
| **FEAT-03** | `GET /trades/active`, `POST /trades/{id}/close` | `TRADE_OPENED`, `TP_HIT`, `SL_HIT`, `ORDER_FILLED` | `ActiveTradesTable`, `TPMilestoneBar`, `CloseModal` |
| **FEAT-04** | `GET /trades/history`, `GET /trades/{id}` | `TRADE_CLOSED` | `TradeHistoryTable`, `TradeDetailTreeModal` |
| **FEAT-05** | `GET /signals`, `POST /signals/manual-execute` | `TRADE_OPENED`, `ORDER_FILLED` | `SignalFeedList`, `SignalExecutionWizardModal` |
| **FEAT-06** | `GET /watchlist`, `POST /watchlist/toggle`, `POST /instruments/sync`| - | `WatchlistGrid`, `InstrumentSyncButton` |
| **FEAT-07** | `POST /calculator/simulate` | - | `RiskSimulatorForm`, `SimulationResultPanel` |
| **FEAT-08** | `GET /bot/status`, `POST /bot/pause`, `/resume`, `/panic`, `GET /settings`, `POST /credentials` | `BOT_STATUS_CHANGED`, `CIRCUIT_BREAKER_TRIGGERED` | `BotStatusHero`, `PanicCloseModal`, `SettingsForm` |
| **FEAT-09** | `GET /logs`, `GET /reports/export/csv` | `BOT_STATUS_CHANGED`, `CIRCUIT_BREAKER_TRIGGERED` | `AuditLogsTerminal`, `CsvExportDatePicker` |
| **FEAT-10** | `GET /ws` & `/api/v1/ws` (WebSocket) | `CONNECTED`, `PONG`, all trading events | `useWebSocketHook`, `ConnectionStatusBadge` |
