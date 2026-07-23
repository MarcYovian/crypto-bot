# Product Requirement Document (PRD)

# Semi-Automated Binance Futures Trading Bot

Version: 1.0

---

# 1. Product Overview & Objective

## Background

Trading secara manual dari sinyal Telegram memiliki beberapa kendala:

* Respon terhadap sinyal sering terlambat.
* Perhitungan lot size berdasarkan risk management sering tidak konsisten.
* Entry, Stop Loss, dan Take Profit rentan terjadi human error.
* Sulit melakukan audit performa trading karena tidak memiliki histori yang terstruktur.

Produk ini bertujuan membangun sistem **Semi-Automated Binance Futures Trading Bot** yang menerima sinyal dari Telegram, melakukan validasi, menghitung ukuran posisi berdasarkan manajemen risiko harian, mengeksekusi order ke Binance Futures, memonitor posisi secara real-time, dan memberikan notifikasi selama siklus trading berlangsung.

## Objectives

* Mengotomatisasi proses eksekusi trading dari Telegram ke Binance Futures.
* Menjamin setiap trade mengikuti risk management harian.
* Mengurangi human error saat entry dan pengelolaan posisi.
* Menyediakan histori trading yang lengkap dan mudah diaudit.
* Memberikan notifikasi real-time kepada pengguna.

---

# 2. Target User & Primary Use Cases

## Target User

* Trader Futures Binance.
* Pengguna yang menerima sinyal trading melalui Telegram.
* Pengguna yang ingin mempertahankan kontrol terhadap keputusan trading berisiko rendah (low confidence).

## Primary Use Cases

### UC-01

Menerima sinyal dari Telegram dan membuka posisi secara otomatis.

### UC-02

Meminta konfirmasi apabila confidence signal berada di bawah threshold.

### UC-03

Menghitung lot size berdasarkan fixed daily risk.

### UC-04

Mengelola posisi secara otomatis (TP, SL, BEP).

### UC-05

Melihat histori dan performa trading.

---

# 3. User Stories & Acceptance Criteria

## US-01

**As a trader, I want the bot to parse Telegram signals automatically, so that I don't need to input trading parameters manually.**

### Acceptance Criteria

* Bot membaca pesan Telegram.
* Signal berhasil diparsing.
* Signal disimpan ke database.
* Format yang salah ditolak.

---

## US-02

**As a trader, I want low-confidence signals to require confirmation, so that I can decide whether to execute them manually.**

### Acceptance Criteria

* Confidence dibandingkan dengan threshold.
* Jika di bawah threshold:

  * Bot mengirim konfirmasi Telegram.
  * User dapat memilih Yes atau No.
* Jika Yes → proses dilanjutkan.
* Jika No → signal dibatalkan.

---

## US-03

**As a trader, I want every trade opened on the same day to use the same risk amount, so that my risk management stays consistent.**

### Acceptance Criteria

* Pukul 00.00 WIB bot mengambil saldo Futures.
* Risk Amount dihitung sekali.
* Seluruh trade hari tersebut menggunakan risk yang sama.
* Risk tidak berubah walaupun balance berubah selama hari berjalan.

---

## US-04

**As a trader, I want position size to be calculated automatically, so that every trade follows my risk management.**

### Acceptance Criteria

* Menggunakan Daily Risk Snapshot.
* Menggunakan Entry Price.
* Menggunakan Stop Loss.
* Mengikuti LOT_SIZE Binance.

---

## US-05

**As a trader, I want the bot to manage TP and SL automatically, so that I don't need to monitor charts continuously.**

### Acceptance Criteria

* Entry berhasil.
* TP dan SL otomatis dipasang.
* TP1 menggeser SL ke BEP.
* TP2 dapat mengaktifkan Trailing Stop (opsional).
* TP3 atau SL menutup posisi.

---

## US-06

**As a trader, I want every important trading event to be logged, so that I can audit every trade later.**

### Acceptance Criteria

* Entry dicatat.
* TP dicatat.
* SL dicatat.
* Manual Close dicatat.
* Funding dicatat.

---

# 4. Functional Requirements

## FR-01 Signal Receiver

* Terhubung ke Telegram Bot API.
* Parsing format signal.
* Validasi format.
* Menyimpan signal ke database.

---

## FR-02 Signal Validation

* Duplicate Trade Check.
* Confidence Check.
* Confirmation apabila confidence di bawah threshold.

---

## FR-03 Daily Risk Snapshot

Setiap pukul **00.00 WIB**:

* Mengambil saldo Futures Binance.
* Menghitung:

  * Balance
  * Risk %
  * Risk Amount
* Menyimpan snapshot harian.

Seluruh trade pada tanggal tersebut wajib menggunakan snapshot yang sama.

---

## FR-04 Risk Calculator

Menghitung:

* Stop Distance
* Risk Amount
* Position Size
* Margin
* Leverage

Menyesuaikan dengan filter Binance:

* LOT_SIZE
* STEP_SIZE
* MIN_QTY
* MIN_NOTIONAL

---

## FR-05 Trade Manager

Membuat data trade.

Status:

* WAITING_ENTRY
* OPEN
* PARTIAL
* CLOSED
* CANCELLED

---

## FR-06 Binance Order Manager

* Set Leverage.
* Set Margin Isolated.
* Entry Order.
* TP1.
* TP2.
* TP3.
* Stop Loss.
* Cancel Order.
* Manual Close.

---

## FR-07 Execution Manager

Menerima User Data Stream Binance.

Update:

* Filled Qty
* Average Entry
* Remaining Qty
* Commission
* Realized PNL

---

## FR-08 Position Manager

Mengelola:

* TP1
* TP2
* TP3
* Stop Loss
* Break Even
* Trailing Stop (opsional)

---

## FR-09 Notification Manager

Mengirim Telegram Notification saat:

* Signal diterima.
* Signal membutuhkan konfirmasi.
* Entry berhasil.
* TP1.
* TP2.
* TP3.
* SL.
* Manual Close.
* Trade selesai.
* Error.

---

## FR-10 Trade Summary

Saat trade selesai menghitung:

* Gross PNL
* Net PNL
* Commission
* Funding
* ROI
* RR
* Duration

---

## FR-11 Audit Logging

Menyimpan:

* Trade Event
* Execution
* Bot Log

---

## FR-12 Watchlist

Digunakan hanya sebagai:

* Daftar pantau coin.
* Shortcut menu Telegram.

Watchlist **tidak mempengaruhi** proses trading.

---

# 5. Non-Functional Requirements

## Performance

* Parsing signal < 1 detik.
* Order dikirim < 2 detik setelah validasi.
* WebSocket latency seminimal mungkin.

---

## Reliability

* Database menjadi source of truth.
* Bot mampu recovery setelah restart.
* Tidak membuat duplicate trade.

---

## Security

* API Key Binance terenkripsi.
* Secret tidak disimpan di log.
* Hanya Telegram User yang diizinkan dapat memberikan command.

---

## Database

* SQLite.
* Foreign Key aktif.
* Menggunakan transaction saat proses entry.

---

## Maintainability

* Modular Service.
* Repository Pattern.
* Mudah ditambahkan strategy baru.

---

# 6. Key User Flow / System Flow

## A. Daily Initialization

1. Jam 00.00 WIB.
2. Ambil saldo Binance Futures.
3. Hitung Daily Risk.
4. Simpan Daily Risk Snapshot.

---

## B. Signal Processing

1. Signal masuk Telegram.
2. Parsing.
3. Simpan ke `trading_signals`.
4. Duplicate Check.
5. Confidence Check.
6. Jika confidence rendah:

   * Kirim konfirmasi Telegram.
   * User memilih Yes / No.
7. Jika disetujui lanjut.

---

## C. Trade Preparation

1. Ambil Daily Risk Snapshot.
2. Hitung Position Size.
3. Simpan `trade_risk`.
4. Buat `trade`.
5. Set Leverage.
6. Set Margin Mode.

---

## D. Trade Execution

1. Kirim Entry Order.
2. Tunggu Fill.
3. Simpan Execution.
4. Hitung Average Entry.
5. Pasang TP1.
6. Pasang TP2.
7. Pasang TP3.
8. Pasang Stop Loss.

---

## E. Position Monitoring

Menggunakan Binance User Data Stream.

Jika:

* TP1 → Geser SL ke BEP.
* TP2 → Opsional aktifkan Trailing Stop.
* TP3 → Close.
* SL → Close.
* Manual Close → Close.

---

## F. Trade Closing

1. Hitung Summary.
2. Simpan Trade Summary.
3. Update Status.
4. Kirim Telegram Notification.

---

# 7. Success Metrics (KPIs)

## Trading

* 100% trade mengikuti Daily Risk.
* 0 duplicate trade.
* 100% signal berhasil diparsing.

---

## Reliability

* ≥99% order berhasil dikirim.
* ≥99% sinkron dengan status Binance.

---

## Performance

* Parsing < 1 detik.
* Entry < 2 detik.
* Telegram Notification < 2 detik setelah event.

---

## Audit

* 100% trade memiliki:

  * Signal
  * Trade
  * Order
  * Execution
  * Summary
  * Event

---

# 8. Out of Scope

Fitur berikut tidak termasuk pada rilis pertama:

* Market Scanner.
* AI Signal Generator.
* Auto Symbol Filtering.
* Multi Exchange.
* Spot Trading.
* Grid Trading.
* DCA Trading.
* Copy Trading.
* Multi Account Binance.
* Backtesting Engine.
* Paper Trading.
* Portfolio Analytics Dashboard.
* Web Dashboard.
* Mobile Application.
* Watchlist sebagai filter trading.
* Maximum Open Position Limit.
* Dynamic Risk berdasarkan perubahan balance intraday.
