# 🔌 WebSocket Real-Time Streaming Specification

## Overview
FastAPI backend menyediakan endpoint WebSocket untuk streaming event real-time ke client (Web Dashboard, monitoring tool, dsb). Endpoint ini broadcast updates seperti pembukaan/penutupan trade, order fill, eksekusi TP/SL, perubahan status bot, dan sinyal darurat (panic close).

---

## Endpoint Details

* **Primary Endpoint:** `/api/v1/ws?token={JWT_ACCESS_TOKEN}`
* **Alternative Endpoint:** `/ws?token={JWT_ACCESS_TOKEN}`
* **Protocol:** `ws://` (Local/Insecure) atau `wss://` (Production/SSL)
* **Authentication:** Wajib menyertakan query parameter `token` berupa JWT access token yang valid. Handshake akan ditolak dengan status code `1008 (Policy Violation)` jika token tidak valid atau kadaluarsa.

---

## Connection Lifecycle & Keep-Alive

1. **Handshake & Auth:**
   Client mengirim request WebSocket dengan token di query parameter.
2. **Initial Event (`CONNECTED`):**
   Setelah handshake berhasil diterima server:
   ```json
   {
     "event": "CONNECTED",
     "timestamp": "2026-09-12T15:04:05.123456Z",
     "data": {
       "message": "WebSocket streaming connected successfully",
       "user": "admin"
     }
   }
   ```
3. **Heartbeat (Ping/Pong):**
   * Client mengirim teks: `"ping"`
   * Server merespons event:
     ```json
     {
       "event": "PONG",
       "timestamp": "2026-09-12T15:04:10.123456Z",
       "data": { "status": "alive" }
     }
     ```

---

## Broadcast Event Schema

Setiap event memiliki struktur envelope standar:
```json
{
  "event": "<EVENT_NAME>",
  "timestamp": "<ISO-8601 UTC Timestamp>",
  "data": { ... }
}
```

### 1. `TRADE_OPENED`
Ditembakkan saat trade baru berhasil dibuka di exchange:
```json
{
  "event": "TRADE_OPENED",
  "timestamp": "2026-09-12T15:00:00.000000Z",
  "data": {
    "trade_id": "tr-12345678",
    "symbol": "BTC/USDT",
    "side": "BUY",
    "entry_price": 60000.0,
    "position_size": 0.05,
    "leverage": 10,
    "strategy": "SMC-OB-FVG",
    "status": "OPEN"
  }
}
```

### 2. `ORDER_FILLED`
Ditembakkan saat order limit/market terisi (*fill*) oleh exchange:
```json
{
  "event": "ORDER_FILLED",
  "timestamp": "2026-09-12T15:00:01.000000Z",
  "data": {
    "order_id": "ord-87654321",
    "trade_id": "tr-12345678",
    "order_type": "ENTRY",
    "fill_price": 60000.0,
    "filled_amount": 0.05
  }
}
```

### 3. `TP_HIT` & `SL_HIT`
Ditembakkan saat harga menyentuh target Take Profit atau Stop Loss:
```json
{
  "event": "TP_HIT",
  "timestamp": "2026-09-12T15:15:00.000000Z",
  "data": {
    "trade_id": "tr-12345678",
    "tp_level": 1,
    "execution_price": 61200.0,
    "realized_pnl": 60.0
  }
}
```

### 4. `TRADE_CLOSED`
Ditembakkan saat posisi trade ditutup sepenuhnya:
```json
{
  "event": "TRADE_CLOSED",
  "timestamp": "2026-09-12T15:30:00.000000Z",
  "data": {
    "trade_id": "tr-12345678",
    "close_reason": "ALL_TP_HIT",
    "net_pnl": 120.50,
    "exit_price": 62400.0
  }
}
```

### 5. `BOT_STATUS_CHANGED`
Ditembakkan saat bot di-pause, di-resume, atau status koneksi berubah:
```json
{
  "event": "BOT_STATUS_CHANGED",
  "timestamp": "2026-09-12T15:35:00.000000Z",
  "data": {
    "status": "PAUSED",
    "changed_by": "admin",
    "reason": "Market high volatility"
  }
}
```

### 6. `CIRCUIT_BREAKER_TRIGGERED`
Ditembakkan saat batas risiko harian (*daily max loss budget*) tercapai dan sistem menghentikan trading otomatis:
```json
{
  "event": "CIRCUIT_BREAKER_TRIGGERED",
  "timestamp": "2026-09-12T15:40:00.000000Z",
  "data": {
    "daily_drawdown": -5.2,
    "max_allowed_loss": -5.0,
    "action": "AUTO_PAUSE_BOT"
  }
}
```
