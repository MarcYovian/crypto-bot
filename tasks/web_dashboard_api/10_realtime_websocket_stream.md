# Task 10: Real-Time WebSocket Streaming Endpoint

## 1. Deskripsi Task
Mengimplementasikan koneksi WebSocket dua arah (`/api/v1/ws`) beserta broker pengelola koneksi klien (*Connection Manager*) untuk mem-broadcast event perdagangan (open posisi, order fill, TP/SL hit, circuit breaker alert) secara *real-time* ke browser dashboard tanpa perlu me-refresh halaman.

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/websocket_manager.py`: Class `WebSocketConnectionManager` untuk mengelola active connections, otorisasi token query param, dan broadcast JSON event ke seluruh klien yang terhubung.
* `backend/src/api/routers/websocket.py`: Router FastAPI untuk endpoint WebSocket `/api/v1/ws`.
* `backend/tests/api/test_websocket_api.py`: Test suite untuk koneksi, broadcast event, dan disconnect handling WebSocket.

### Modifikasi File:
* `backend/src/services/position_manager.py`: Mengintegrasikan trigger broadcast event ke `WebSocketConnectionManager` saat status trade diperbarui (misal: TP1 hit, SL hit, close trade).
* `backend/src/services/trade_service.py`: Mengintegrasikan trigger broadcast event saat sinyal baru dieksekusi menjadi trade aktif.
* `backend/src/api/app.py`: Menambahkan mounting `websocket_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `GET /api/v1/ws`:
  * **Query Params**: `token: str` (JWT Access Token untuk otorisasi koneksi).
  * **Protokol**: `101 Switching Protocols` (WebSocket).
  * **Struktur Broadcast Payload (JSON)**:
    ```json
    {
      "event": "TRADE_OPENED | ORDER_FILLED | TP_HIT | SL_HIT | TRADE_CLOSED | CIRCUIT_BREAKER_TRIGGERED",
      "timestamp": "2026-08-23T22:30:00Z",
      "data": {
        "trade_id": 101,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "price": 50000.0,
        "unrealized_pnl": 15.5
      }
    }
    ```

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Otorisasi Koneksi**: Klien dengan token JWT valid berhasil terhubung; koneksi tanpa token ditolak.
2. **Real-time Event Dispatching**: Saat sebuah trade dieksekusi atau order terisi di `PositionManager`, pesan broadcast langsung terkirim ke seluruh koneksi WebSocket yang aktif dalam < 50ms.
3. **Graceful Disconnection**: Disconnect klien (misal: tab browser ditutup) ditangani dengan bersih tanpa menyebabkan memory leak atau error server.
4. **Testing**: Seluruh test di `backend/tests/api/test_websocket_api.py` lulus 100%.
