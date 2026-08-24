# Task 10: Real-Time WebSocket Streaming Endpoint

## 1. Deskripsi Task
Mengimplementasikan endpoint koneksi WebSocket dua arah (`/api/v1/ws` dan `/ws`) beserta broker pengelola koneksi klien (*WebSocket Connection Manager*) untuk mem-broadcast event siklus perdagangan (posisi baru, order fill, TP/SL hit, trade closed, circuit breaker alert, dan perubahan status bot) secara *real-time* ke browser dashboard secara reaktif tanpa polling.

Implementasi ini menerapkan arsitektur terintegrasi:
* **Event Broker / Connection Manager (`backend/src/api/websocket_manager.py`)**:
  * Mengelola set koneksi klien aktif (`active_connections`).
  * Autentikasi dan otorisasi handshake berbasis token JWT query param (`?token=...`).
  * Penanganan konkurensi asinkron (*thread-safe broadcast dispatching*) dan *graceful disconnect handling*.
  * Struktur payload event terstandarisasi dengan envelope: `{"event": str, "timestamp": str, "data": dict}`.
* **Domain Integration & Event Dispatching**:
  * `PositionManager` & `TradeService`: Memicu broadcast saat event `TRADE_OPENED`, `ORDER_FILLED`, `TP_HIT`, `SL_HIT`, `TRADE_CLOSED` terjadi.
  * `BotService`: Memicu broadcast saat status engine berubah (`BOT_STATUS_CHANGED`, `CIRCUIT_BREAKER_TRIGGERED`).
* **Router Layer (`backend/src/api/routers/websocket.py`)**:
  * Controller WebSocket FastAPI yang menangani siklus hidup handshake, verifikasi token, keep-alive loop (ping/pong), dan pembersihan memori saat koneksi terputus.

---

## 2. File yang Akan Dibuat & Dimodifikasi

### File Baru:
1. `backend/src/api/websocket_manager.py`: Singleton `WebSocketConnectionManager` untuk registrasi klien dan broadcast event real-time.
2. `backend/src/api/routers/websocket.py`: Router FastAPI untuk endpoint WebSocket `/api/v1/ws` dan `/ws`.
3. `backend/tests/api/test_websocket_api.py`: Test suite komprehensif untuk pengujian handshake, autentikasi token, multi-client broadcast, dan graceful disconnect.

### Modifikasi File:
1. `backend/src/services/position_manager.py`: Menambahkan pemanggilan `ws_manager.broadcast()` pada penanganan TP hit, SL hit, dan close trade.
2. `backend/src/services/trade_service.py`: Menambahkan pemanggilan `ws_manager.broadcast()` saat entry order terisi dan posisi dibuka (`TRADE_OPENED`).
3. `backend/src/services/bot_service.py`: Menambahkan pemanggilan `ws_manager.broadcast()` saat pause, resume, atau panic close dipicu.
4. `backend/src/api/routers/__init__.py`: Mengekspor `websocket_router`.
5. `backend/src/api/app.py`: Me-mount `websocket_router`.

---

## 3. Spesifikasi Rinci Endpoint & Protokol Komunikasi

### A. Endpoint `/api/v1/ws` (dan `/ws`)
* **Summary**: Real-time WebSocket event connection.
* **Protocol**: `101 Switching Protocols` (WebSocket).
* **Handshake Authentication**:
  * Query Param: `token: Optional[str]` (Bearer JWT Access Token).
  * Validasi: Decode JWT payload, verifikasi signature, masa berlaku, dan pastikan user aktif (`is_active=True`).
  * Jika token tidak ada / invalid / kedaluwarsa: Koneksi ditutup segera dengan WebSocket close code `1008` (*Policy Violation*).

---

### B. Standard Event Catalog & Envelope Format

Seluruh pesan broadcast dikirim dalam format JSON envelope standar:
```json
{
  "event": "EVENT_TYPE",
  "timestamp": "2026-08-24T15:30:00Z",
  "data": { ... }
}
```

| Event Type | Pemicu (Trigger) | Contoh Payload `data` |
| :--- | :--- | :--- |
| `TRADE_OPENED` | Trade baru berhasil dibuka (entry filled). | `{"trade_id": 101, "symbol": "BTCUSDT", "side": "BUY", "entry_price": 50000.0, "position_size": 0.02, "leverage": 20, "sl_price": 49000.0}` |
| `ORDER_FILLED` | Limit order, TP, atau SL terisi sebagian/penuh. | `{"trade_id": 101, "symbol": "BTCUSDT", "client_order_id": "TP1_ORD", "order_type": "LIMIT", "filled_qty": 0.01, "price": 51000.0}` |
| `TP_HIT` | Level Take Profit (TP1/TP2/TP3) tercapai. | `{"trade_id": 101, "symbol": "BTCUSDT", "tp_level": "TP1", "price": 51000.0, "realized_pnl": 20.0}` |
| `SL_HIT` | Stop Loss (Direct SL / Trailing SL / BEP) tersentuh. | `{"trade_id": 101, "symbol": "BTCUSDT", "sl_type": "TRAILING_SL", "price": 49500.0, "realized_pnl": -10.0}` |
| `TRADE_CLOSED` | Seluruh porsi trade telah ditutup. | `{"trade_id": 101, "symbol": "BTCUSDT", "net_pnl": 195.0, "roi": 7.8, "result": "WIN", "close_reason": "TP2"}` |
| `CIRCUIT_BREAKER_TRIGGERED` | Circuit breaker aktif karena batas drawdown harian. | `{"reason": "Daily loss limit exceeded", "daily_loss_pct": 6.5, "max_limit_pct": 6.0}` |
| `BOT_STATUS_CHANGED` | Bot di-pause, di-resume, atau panic close dipicu. | `{"is_paused": true, "trading_status": "PAUSED", "action": "EMERGENCY_PANIC"}` |
| `TICKER_UPDATE` | Pembaruan realtime mark price atau ticker instrumen. | `{"symbol": "BTCUSDT", "mark_price": 50125.50}` |

---

## 4. Matriks Pengujian Lengkap (Test Matrix)

Test suite `backend/tests/api/test_websocket_api.py` mencakup:

| Kategori | Nama Test | Deskripsi Skenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **Koneksi & Auth** | `test_ws_connection_authorized_success` | Klien terhubung dengan query param token JWT admin/viewer valid. | Handshake sukses (`101 Switching Protocols`), klien menerima event `CONNECTED` / `HEARTBEAT`. |
| **Koneksi & Auth** | `test_ws_connection_missing_token_rejected` | Klien mencoba koneksi tanpa query parameter `token`. | Handshake ditolak / koneksi ditutup dengan code `1008`. |
| **Koneksi & Auth** | `test_ws_connection_invalid_token_rejected` | Klien mencoba koneksi dengan signature token palsu atau token kadaluwarsa. | Handshake ditolak / koneksi ditutup dengan code `1008`. |
| **Broadcast Event** | `test_ws_broadcast_trade_opened_event` | Memicu event `TRADE_OPENED` melalui `ws_manager.broadcast()`. | Klien menerima payload JSON terstruktur dengan event `TRADE_OPENED` dan detail trade. |
| **Broadcast Event** | `test_ws_broadcast_tp_sl_hit_events` | Memicu event `TP_HIT` dan `SL_HIT`. | Klien menerima kedua event secara sekuensial dengan payload yang tepat. |
| **Broadcast Event** | `test_ws_broadcast_circuit_breaker_event` | Memicu event `CIRCUIT_BREAKER_TRIGGERED` dan `BOT_STATUS_CHANGED`. | Klien menerima notifikasi alert circuit breaker dan update status bot. |
| **Multi-Client** | `test_ws_multi_client_broadcast` | Membuka 3 koneksi WebSocket independen secara simultan, lalu mem-broadcast event. | Seluruh (3) klien menerima salinan pesan yang sama tanpa duplikasi atau keterlambatan. |
| **Disconnect & Cleanup** | `test_ws_client_graceful_disconnect` | Klien menutup koneksi WebSocket secara sengaja. | Connection manager menghapus websocket dari `active_connections` tanpa memory leak atau error logging server. |
| **Ping / Pong** | `test_ws_ping_pong_keepalive` | Klien mengirimkan text `"ping"`. | Server merespons dengan JSON `{"event": "PONG"}`. |

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. **Otorisasi Handshake Ketat**: Hanya klien dengan token JWT valid yang dapat membuka stream; akses tanpa token/token cacat langsung diputus (*code 1008*).
2. **Low-Latency Event Dispatching**: Broadcast event didistribusikan ke seluruh klien aktif dalam hitungan milidetik secara asinkron tanpa memblokir execution thread.
3. **Robust Connection Lifecycle**: Disconnect mendadak, network drop, atau tab browser ditutup ditangani dengan bersih tanpa menimbulkan *stale connection leak*.
4. **Kepatuhan OpenAPI**: Endpoint `/api/v1/ws` dan `/ws` sesuai dengan `docs/openapi.yaml`.
5. **Mypy Static Typing**: 0 errors pada static type checking (`mypy backend/src/`).
6. **Testing**: Seluruh test di `test_websocket_api.py` dan seluruh test backend lulus 100%.
