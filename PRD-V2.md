# **Rekomendasi Tech Stack & Strategi Database Web Dashboard Trading Bot**

Dokumen ini memuat panduan pemilihan teknologi (*tech stack*) untuk membuat Web Dashboard Trading Bot, serta arsitektur database lengkap yang mendukung pencatatan komisi, funding fee, dan Profit/Loss bersih (*Net PnL*).

## **1\. Rekomendasi Tech Stack (Teknologi yang Digunakan)**

Untuk membangun web dashboard yang *fast*, *real-time*, dan berpenampilan modern (*dark mode*), berikut adalah kombinasi teknologi yang paling efisien:

┌─────────────────────────────────────────────────────────────┐  
│                      FRONTEND (WEB)                         │  
│  Next.js (React) \+ Tailwind CSS \+ Shadcn/UI \+ Recharts       │  
└──────────────────────────────┬──────────────────────────────┘  
                               │ WebSocket / REST API  
┌──────────────────────────────▼──────────────────────────────┐  
│                    BACKEND API (PYTHON)                     │  
│               FastAPI \+ Uvicorn \+ WebSockets                │  
└──────────────────────────────┬──────────────────────────────┘  
                               │ Direct DB Access / WAL Mode  
┌──────────────────────────────▼──────────────────────────────┐  
│                    DATABASE & BOT CORE                      │  
│            SQLite (\`trading\_bot.db\`) \+ Python Bot           │  
└──────────────────────────────┘

### **A. Frontend (Tampilan Aplikasi Web)**

* **Framework:** Next.js (React)  
* **Styling & Component:** Tailwind CSS \+ Shadcn/UI  
* **Grafik & Visualisasi:** Recharts atau Lightweight Charts (by TradingView)  
* **Icon Set:** Lucide React (lucide-react)

### **B. Backend API (Server Web & Real-Time Data)**

* **Framework:** FastAPI (Python)  
* **Server Runner:** Uvicorn (ASGI Server)

### **C. Komunikasi Real-time**

* **WebSockets (FastAPI WebSockets):** Mengalirkan pergerakan harga live dan update status posisi aktif ke dashboard browser tanpa refresh.

## **2\. Strategi Arsitektur Database (SQLite \+ WAL Mode)**

Anda **TIDAK PERLU** menggunakan database server terpisah seperti PostgreSQL di awal. File SQLite trading\_bot.db yang sama bisa diproses oleh bot dan FastAPI Web secara bersamaan dengan mengaktifkan mode **WAL (Write-Ahead Logging)**.

Eksekusi perintah ini sekali saat inisialisasi database:

PRAGMA journal\_mode=WAL;

## **3\. Skema Database Terbaru (Support Fee & Net PnL)**

Agar dashboard dapat menampilkan laporan keuangan yang presisi (termasuk potongan fee dan riwayat partial close), gunakan skema tabel berikut:

\-- 1\. TABEL POSISI AKTIF (Satu baris per koin yang sedang jalan)  
CREATE TABLE IF NOT EXISTS active\_trades (  
    id INTEGER PRIMARY KEY AUTOINCREMENT,  
    symbol TEXT NOT NULL,  
    side TEXT NOT NULL,                   \-- 'BUY' (LONG) atau 'SELL' (SHORT)  
    entry\_price REAL NOT NULL,  
    sl\_price REAL NOT NULL,  
    tp1\_price REAL NOT NULL,  
    tp2\_price REAL NOT NULL,  
    tp3\_price REAL,  
    initial\_qty REAL NOT NULL,            \-- Total kuantitas koin saat entry pertama  
    remaining\_qty REAL NOT NULL,          \-- Sisa kuantitas koin yang belum di-TP  
    tp\_stage INTEGER DEFAULT 0,           \-- 0: Entry, 1: TP1 Hit, 2: TP2 Hit, 3: Completed  
    accumulated\_realized\_pnl REAL DEFAULT 0.0, \-- Akumulasi profit sementara dari TP1 & TP2 (gross)  
    accumulated\_commission REAL DEFAULT 0.0,   \-- Akumulasi komisi yang sudah terpotong  
    accumulated\_funding REAL DEFAULT 0.0,      \-- Akumulasi funding fee yang sudah dibayar/diterima  
    is\_active INTEGER DEFAULT 1,          \-- 1: Aktif, 0: Selesai  
    created\_at TIMESTAMP DEFAULT CURRENT\_TIMESTAMP,  
    updated\_at TIMESTAMP DEFAULT CURRENT\_TIMESTAMP  
);

\-- 2\. TABEL JURNAL PERFORMA (Satu baris per sinyal yang tertutup 100%)  
CREATE TABLE IF NOT EXISTS trade\_history (  
    id INTEGER PRIMARY KEY AUTOINCREMENT,  
    symbol TEXT NOT NULL,  
    side TEXT NOT NULL,  
    entry\_price REAL NOT NULL,  
    close\_price REAL NOT NULL,            \-- Harga penutupan terakhir (TP3 / SL BEP / Manual)  
    gross\_pnl\_usd REAL NOT NULL,          \-- Profit/Loss kotor (sebelum fee)  
    total\_commission\_usd REAL NOT NULL,   \-- Total komisi transaksi (Entry \+ Exit)  
    total\_funding\_usd REAL NOT NULL,      \-- Total biaya funding fee selama posisi hold  
    net\_pnl\_usd REAL NOT NULL,            \-- Profit Bersih (Gross \- Commission \+ Funding)  
    net\_pnl\_percent REAL NOT NULL,        \-- Persentase profit bersih dari margin modal  
    close\_reason TEXT NOT NULL,           \-- 'FULL\_TP', 'TP2\_BEP\_SL', 'TP1\_BEP\_SL', 'SL\_HIT', 'MANUAL\_CLOSE'  
    duration\_minutes INTEGER,             \-- Total durasi posisi terbuka  
    closed\_at TIMESTAMP DEFAULT CURRENT\_TIMESTAMP  
);

\-- 3\. TABEL EVENT & PARSIAL CLOSE (Log rinci tiap kali TP1/TP2/SL tersentuh)  
CREATE TABLE IF NOT EXISTS trade\_events (  
    id INTEGER PRIMARY KEY AUTOINCREMENT,  
    trade\_id INTEGER NOT NULL,            \-- Relasi ke active\_trades.id  
    event\_type TEXT NOT NULL,             \-- 'ENTRY', 'TP1\_HIT', 'TP2\_HIT', 'TP3\_HIT', 'SL\_HIT'  
    price REAL NOT NULL,  
    qty REAL NOT NULL,  
    realized\_pnl\_usd REAL DEFAULT 0.0,  
    commission\_usd REAL DEFAULT 0.0,  
    created\_at TIMESTAMP DEFAULT CURRENT\_TIMESTAMP,  
    FOREIGN KEY (trade\_id) REFERENCES active\_trades(id)  
);

\-- 4\. TABEL WATCHLIST & SCANNER MARKET (Untuk Menu Watchlist)  
CREATE TABLE IF NOT EXISTS watchlist\_scanner (  
    symbol TEXT PRIMARY KEY,  
    price REAL,  
    change\_24h REAL,  
    ma50\_distance\_pct REAL,  
    rsi\_14 REAL,  
    status\_signal TEXT,                   \-- 'UPTREND', 'DOWNTREND', 'FLAT'  
    updated\_at TIMESTAMP DEFAULT CURRENT\_TIMESTAMP  
);

## **4\. Alur Pembaruan Data dari Bot ke Database**

1. **Saat Entry Pertama Kali:**  
   * Bot membuat baris baru di active\_trades (initial\_qty \= remaining\_qty).  
   * Bot mencatat event entry ke trade\_events (event\_type \= 'ENTRY').  
2. **Saat Menyentuh TP1 / TP2 (Partial Exit):**  
   * Bot memperbarui remaining\_qty, accumulated\_realized\_pnl, accumulated\_commission, dan tp\_stage di active\_trades.  
   * Bot menambahkan log ke trade\_events (misal event\_type \= 'TP1\_HIT').  
   * **Belum ada baris baru di trade\_history.**  
3. **Saat Posisi Tutup 100% (TP3 / SL BEP / Manual Close):**  
   * Bot menghitung net\_pnl\_usd akhir:  
     ![][image1]  
   * Bot memasukkan **1 baris lengkap** ke trade\_history.  
   * Bot mengubah is\_active \= 0 pada baris di active\_trades.

[image1]: <data:image/png;base64,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>