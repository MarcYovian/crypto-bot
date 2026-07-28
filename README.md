# 🤖 Semi-Automated Binance Futures Trading Bot V2

Bot trading Futures Binance semi-otomatis berkinerja tinggi yang menerima sinyal trading dari Telegram, melakukan kalkulasi manajemen risiko harian (Strict 2% Risk Guard), mengeksekusi order via CCXT Pro, dan mengelola posisi secara *real-time* via WebSocket Stream.

---

## 🌟 Fitur Utama

- **Telegram Signal Parser**: Ekstraksi otomatis parameter sinyal (Pair, Side, Entry, SL, TP1-TP3, Leverage) dari pesan Telegram.
- **Interactive Risk Guard & Confirmation**: Konfirmasi manual (Yes/No) via Telegram Inline Keyboard untuk sinyal dengan *confidence score* rendah.
- **Strict 2% Daily Risk & Market Slippage Guard**: Saldo dikunci pada 00:00 WIB. Lot size otomatis dihitung ulang *real-time* saat eksekusi Market Order agar batas kerugian SL tidak pernah melebihi 2.0%.
- **Dual Execution Engine (CCXT Pro)**:
  - Eksekusi `MARKET` jika harga pasar berada dekat target sinyal (dalam toleransi 0.2%).
  - Eksekusi `LIMIT` jika harga pasar bergeser terlalu jauh.
- **Real-time Position State Machine**:
  - Otomatis menggeser SL ke **Break-Even (BEP)** saat **TP1** tersentuh.
  - Otomatis mengaktifkan **Trailing Stop (SL digeser ke TP1)** saat **TP2** tersentuh.
  - Menutup sisa order pendukung dan menghitung performa saat posisi `CLOSED`.
- **Centralized Error Parsing**: Mengubah error Binance API & sistem menjadi pesan Telegram yang informatif, rapi, dan memberikan rekomendasi tindakan.
- **Background Cron Maintenance**:
  - `Daily Risk Snapshot` (00:00 WIB) + Laporan Notifikasi Telegram.
  - `Cleanup Orphan Orders` (Setiap 30 menit).
  - `Failsafe Sync Check` (Setiap 15 menit).

---

## 📁 Struktur Direktori

```text
crypto-bot/
├── backend/
│   ├── config/
│   │   └── settings.py           # Central Pydantic Environment Settings
│   ├── src/
│   │   ├── database/             # SQLAlchemy Async Models & Connection
│   │   ├── repository/           # Repository Pattern (Signal, Trade, Event, Risk)
│   │   ├── services/             # Core Logic (Execution, Position, Risk, Telegram, WS)
│   │   └── utils/                # Error Parser & Helpers
│   ├── tests/                    # Pytest Suite (34 Unit Tests)
│   └── main.py                   # Entry Point App
├── docs/
│   ├── ARCHITECTURE.md           # Dokumentasi Arsitektur Teknis System V2
│   └── TELEGRAM_COMMANDS.md      # Panduan Perintah & Interaksi Telegram Bot
├── requirements.txt              # Production Dependencies
└── README.md                     # Panduan Penggunaan Utama
```

---

## 🚀 Cara Menjalankan Bot

### 1. Prasyarat System
- Python `>= 3.10`
- Virtual Environment (`venv`)

### 2. Setup Environment Variables
Buat file `.env` di root proyek:
```env
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
BINANCE_TESTNET=True

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

DEFAULT_LEVERAGE=20
CONFIDENCE_THRESHOLD=0.70
LOG_LEVEL=INFO
```

### 3. Instalasi Dependensi & Jalankan Bot
```bash
# Aktifkan venv & install dependensi
source venv/bin/activate
pip install -r requirements.txt

# Menjalankan bot
PYTHONPATH=backend python backend/main.py
```

### 4. Running Unit Tests
```bash
PYTHONPATH=backend venv/bin/pytest backend/tests/
```

---

## 📚 Dokumentasi Lanjutan

- [Dokumentasi Arsitektur Teknis (ARCHITECTURE.md)](file:///home/rodex/Documents/cell/projects/crypto-bot/docs/ARCHITECTURE.md)
- [Panduan Perintah & Telegram Bot (TELEGRAM_COMMANDS.md)](file:///home/rodex/Documents/cell/projects/crypto-bot/docs/TELEGRAM_COMMANDS.md)
