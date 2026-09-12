# 📈 Smart Money Concepts (SMC) & Trading Engine Logic

## Overview
Engine trading backend ini mengimplementasikan metodologi **Smart Money Concepts (SMC)** untuk perdagangan otomatis dan semi-otomatis di pasar Binance Futures. Dokumen ini merangkum aturan logika bisnis, struktur pasar, dan manajemen risiko yang diimplementasikan di layer domain.

---

## 1. Konsep Inti SMC

1. **Market Structure & Order Blocks (OB):**
   * **Bullish Order Block:** Candle *down-close* (bearish) terakhir sebelum terjadinya dorongan naik agresif yang memecahkan struktur pasar (*Break of Structure / BOS*). Berfungsi sebagai area entry *Long*.
   * **Bearish Order Block:** Candle *up-close* (bullish) terakhir sebelum terjadinya dorongan turun agresif yang memecahkan struktur pasar. Berfungsi sebagai area entry *Short*.
2. **Fair Value Gap (FVG) / Inefficiency:**
   * Ketidakseimbangan harga antara 3 candle berurutan di mana terdapat celah (*gap*) harga antara candle ke-1 dan candle ke-3.
   * Digunakan sebagai zona konfirmasi *entry* saat harga melakukan retest (mitigasi).
3. **Liquidity Sweep & Inducement:**
   * Pengambilan likuiditas (*Stop Hunt*) pada level swing high (Buy-side Liquidity / BSL) atau swing low (Sell-side Liquidity / SSL) sebelum pembalikan arah harga yang valid.

---

## 2. Alur Eksekusi Sinyal (Signal Pipeline)

```
[Telegram Sinyal / Scanner]
          │
          ▼
[SignalParserDomainService]
  • Ekstraksi Pair, Side, Entry Price/Zone, SL, TP1, TP2, TP3
  • Alokasi trace_id unik (sig-xxxx)
          │
          ▼
[RiskCalculatorDomainService]
  • Validasi Modal & Daily Risk Budget
  • Hitung Position Size (Max risk per trade, default 1-2%)
  • Hitung Dynamic Leverage & Estimasi Liquidation Price
  • Normalisasi Binance Symbol Filter (minNotional, stepSize, tickSize)
          │
          ▼
[BinanceExecutionGateway]
  • Pasang Bracket Orders (Entry Limit/Market, OCO/TPs, SL)
          │
          ▼
[TradeStateMachine]
  • Transisi State: PENDING -> OPEN -> PARTIALLY_FILLED -> CLOSED / CANCELLED
```

---

## 3. Manajemen Risiko & Proteksi Modal

1. **Risk Per Trade:**
   * Formula alokasi ukuran posisi:
     $$\text{Position Size} = \frac{\text{Account Equity} \times \text{Risk Percentage}}{|\text{Entry Price} - \text{Stop Loss Price}|}$$
   * Ukuran tidak boleh melebihi margin tersedia atau batas *notional value* exchange.
2. **Daily Risk Budget & Circuit Breaker:**
   * Sistem mencatat snapshot modal harian pada 00:00 UTC/WIB.
   * Jika akumulasi kerugian harian melampaui batas maksimum (*Daily Max Drawdown*, misal 5%), sistem secara otomatis mengaktifkan **Circuit Breaker**:
     - Menghentikan eksekusi sinyal baru (*Auto Pause*).
     - Mengirim notifikasi darurat via Telegram dan event WebSocket `CIRCUIT_BREAKER_TRIGGERED`.
3. **Break-Even Point (BEP) & Trailing Stop:**
   * Ketika TP1 tercapai, Stop Loss order otomatis dipindahkan ke harga entry (+ biaya komisi) untuk mengamankan posisi (*Risk-Free Trade*).
4. **Panic Liquidation (`/bot/panic`):**
   * Endpoint darurat untuk langsung membatalkan semua order gantung dan menutup semua posisi aktif di market price secara serentak.
