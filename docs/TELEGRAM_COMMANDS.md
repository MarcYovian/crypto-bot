# 📱 Panduan Telegram Bot & Perintah Interaktif

Dokumen ini menjelaskan daftar perintah, format sinyal yang didukung, dan sistem interaksi Telegram Bot pada **Binance Futures Trading Bot V2**.

---

## 1. Daftar Perintah Bot (Telegram Commands)

| Perintah | Deskripsi | Tampilan Output |
| :--- | :--- | :--- |
| `/account` atau `/balance` | Menampilkan informasi akun Binance, total saldo USDT, saldo bebas, dan saldo terpakai. | Saldo Total, Available Margin, Used Margin |
| `/status` atau `/positions` | Menampilkan daftar seluruh posisi trading aktif saat ini yang ada di database & Binance. | Symbol, Side, Status, Entry Target, SL, TP1-TP3 |
| `/summary` atau `/performance` | Menampilkan rekapitulasi performa trading kumulatif (Total Trade, Win Rate, Gross PnL, Komisi, Funding Fee, Net PnL). | Rekapitulasi Keuangan Bersih |
| `/close <SYMBOL>` | Menutup posisi trading secara manual di harga pasar dan membatalkan sisa order pendukung (cth: `/close SOLUSDT`). | Notifikasi Penutupan Manual |

---

## 2. Format Sinyal Telegram yang Didukung

Bot mampu mengekstrak sinyal trading otomatis dari format pesan Telegram berikut:

```text
🤖 AI Agent Detect Chart Pattern

🚨 Symbol: SOLUSDT 🟢 Long
⏱ Timeframe: 1H
📈 Leverage: 20x
🔷 Pattern: Bullish Flag

💰 Entry: 145.50
🛡 SL: 142.00 (-2.40%)
🎯 TP1: 148.00 (+1.71%)
⚡️ TP2: 152.00 (+4.46%)
🔥 TP3: 158.00 (+8.59%)

🧠 Confidence Score (AI): 85%
📝 AI Note: Setup breakout sangat jelas dengan volume tinggi.
```

### Parameter yang Diparsing:
- **Symbol**: `SOLUSDT` (USDT-M Futures Pair)
- **Side**: `🟢 Long` $\rightarrow$ `BUY` | `🔴 Short` $\rightarrow$ `SELL`
- **Entry**: `145.50`
- **SL**: `142.00`
- **TP Prices**: `TP1: 148.00`, `TP2: 152.00`, `TP3: 158.00`
- **Leverage**: `20x`
- **Confidence Score**: `85%`

---

## 3. Sistem Konfirmasi Sinyal (Confidence Threshold Guard)

Jika sinyal yang masuk memiliki **Confidence Score < 70%** (dapat diatur di `CONFIDENCE_THRESHOLD`), bot **TIDAK AKAN langsung mengeksekusi order**, melainkan mengirimkan tombol konfirmasi interaktif ke Telegram:

```text
⚠️ Sinyal Confidence Rendah! (65%)

• Symbol: JUPUSDT
• Side: BUY
• Entry: 0.183772
• SL: 0.177307

Apakah Anda ingin melanjutkan eksekusi trade ini?
[ 🚀 Eksekusi Trade ]  [ ❌ Batalkan ]
```

- Jika Anda menekan **🚀 Eksekusi Trade**, bot akan langsung memproses kalkulasi risiko dan mengirim order ke Binance.
- Jika Anda menekan **❌ Batalkan**, sinyal dibatalkan dan dicatat sebagai `REJECTED` di database.
