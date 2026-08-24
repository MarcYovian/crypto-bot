# Dokumentasi API Specification (SMC CryptoBot Dashboard)

Spesifikasi resmi REST & WebSocket API untuk antarmuka **Web Dashboard UI Crypto Trading Bot**. Dokumen OpenAPI 3.1.0 Swagger lengkap tersimpan di [`docs/openapi.yaml`](./openapi.yaml).

---

## 🔐 1. Authentication & Security Scheme

* **Metode**: JSON Web Token (JWT) Bearer Token & Session Auth.
* **Header Format**: `Authorization: Bearer <JWT_ACCESS_TOKEN>`
* **Role**: `ADMIN` (Akses penuh baca/tulis, tombol darurat, ubah setting) dan `VIEWER` (Hanya baca grafik & posisi).

### Endpoints:
| Method | Endpoint | Deskripsi | Request Body | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Login admin untuk mendapatkan token | `{"username": "admin", "password": "..."}` | `{"access_token": "...", "token_type": "bearer", "user": {...}}` |
| `POST` | `/api/v1/auth/refresh` | Refresh access token yang kedaluwarsa | `{"refresh_token": "..."}` | `{"access_token": "...", "token_type": "bearer"}` |
| `GET` | `/api/v1/auth/me` | Ambil profil admin yang sedang login | None | `{"id": 1, "username": "admin", "role": "ADMIN"}` |

---

## 📊 2. Analytics & Dashboard Summary

| Method | Endpoint | Deskripsi | Query Params | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/summary` | Metrik ringkasan kartu dashboard utama | `account_id=1` | `{"total_balance_usdt": 10450.50, "daily_realized_pnl": 45.50, "win_rate": 72.5, "daily_risk_budget": 200.0, "remaining_risk_budget": 154.50, "active_trades_count": 2}` |
| `GET` | `/api/v1/analytics/equity-curve` | Data chart pertumbuhan modal harian | `timeframe=30d` | `[{"timestamp": "...", "balance": 10250.0, "pnl": 25.0}]` |

---

## ⚡ 3. Trades & Live Position Management

| Method | Endpoint | Deskripsi | Query / Body | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/trades/active` | Daftar posisi aktif (`OPEN`, `PARTIAL`, `WAITING_ENTRY`) + Live Unrealized PnL | `account_id=1` | `[{"trade_id": 101, "symbol": "BTCUSDT", "side": "BUY", "status": "OPEN", "entry_price": 50000.0, "current_price": 50600.0, "unrealized_pnl": 12.0, "sl_price": 49000.0, "tp_levels": [...]}]` |
| `GET` | `/api/v1/trades/history` | Riwayat trade lampau terpaginasi | `page=1&page_size=20&result=WIN` | `{"total": 120, "page": 1, "items": [{"id": 45, "symbol": "ETHUSDT", "net_pnl": 75.0, "result": "WIN"}]}` |
| `GET` | `/api/v1/trades/{id}` | Detail lengkap 1 trade (termasuk 5 child entities: orders, executions, events, risk, summary) | Path param: `id` | `{"trade_id": 101, "symbol": "BTCUSDT", "orders": [...], "executions": [...], "events": [...]}` |
| `POST` | `/api/v1/trades/{id}/close` | Tombol manual close posisi via Market order | `{"reason": "UI_MANUAL_CLOSE"}` | `{"success": true, "message": "Position closed successfully."}` |

---

## 📡 4. Telegram Signals & Manual Execution

| Method | Endpoint | Deskripsi | Payload / Params | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/signals` | Feed sinyal yang masuk dari Telegram | `page=1&status=PROCESSED` | `{"total": 50, "items": [{"id": 12, "trace_id": "sig-a1b2", "symbol": "BTCUSDT", "confidence_score": 0.95}]}` |
| `POST` | `/api/v1/signals/manual-execute` | Eksekusi sinyal kustom manual dari UI | `{"symbol": "BTCUSDT", "side": "BUY", "entry_price": 50000.0, "sl_price": 49000.0, "tp_targets": [51000, 52000]}` | `{"is_success": true, "trade_id": 88, "symbol": "BTCUSDT", "position_size": 0.02}` |

---

## 📋 5. Watchlist & Instruments

| Method | Endpoint | Deskripsi | Payload / Params | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/watchlist` | Daftar koin yang diizinkan ditradingkan | None | `[{"symbol": "BTCUSDT", "enabled": true, "max_leverage": 125, "tick_size": 0.1}]` |
| `POST` | `/api/v1/watchlist/toggle` | Toggle aktif/nonaktif trading pair | `{"symbol": "BTCUSDT", "enabled": false}` | `{"symbol": "BTCUSDT", "enabled": false}` |
| `GET` | `/api/v1/instruments` | Daftar seluruh pair Binance Futures + leverage brackets | None | `[{"symbol": "BTCUSDT", "price_precision": 2, "brackets": [...]}]` |
| `POST` | `/api/v1/instruments/sync` | Sinkronisasi metadata pair dari Binance | None | `{"synced_instruments": 280, "synced_brackets": 280}` |

---

## 📢 6. Signal Providers (Channel Telegram)

| Method | Endpoint | Deskripsi | Payload / Params | Response Sukses (200 / 201) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/providers` | Daftar channel Telegram sumber sinyal | None | `[{"id": 1, "name": "VIP Signals", "channel_id": "-100123", "is_active": true}]` |
| `POST` | `/api/v1/providers` | Daftarkan channel Telegram baru | `{"name": "VIP Alpha", "channel_id": "-100999", "confidence_weight": 1.0}` | `{"id": 2, "name": "VIP Alpha", "is_active": true}` |
| `GET` | `/api/v1/providers/{id}/analytics` | Leaderboard performa channel (Win Rate & Net PnL) | Path param: `id` | `{"provider_id": 1, "total_signals": 50, "win_rate": 75.0, "total_net_pnl_usdt": 450.25}` |

---

## 🧠 7. Strategies Management

| Method | Endpoint | Deskripsi | Payload / Params | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/strategies` | Daftar konfigurasi strategi Take Profit | None | `[{"id": 1, "name": "3-Stage TP", "bep_trigger_level": 1, "trailing_trigger_level": 2}]` |
| `PUT` | `/api/v1/strategies/{id}` | Update rasio TP dan trailing step | `{"tp1_percent": 50.0, "tp2_percent": 30.0, "tp3_percent": 20.0}` | `{"id": 1, "name": "3-Stage TP", "is_active": true}` |

---

## 🧮 8. Live Risk Calculator Sandbox

| Method | Endpoint | Deskripsi | Payload | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/calculator/simulate` | Simulasi hitung lot risiko 2% sebelum open posisi | `{"symbol": "BTCUSDT", "side": "BUY", "entry_price": 50000.0, "sl_price": 49000.0, "wallet_balance": 1000.0}` | `{"max_allowed_loss_usdt": 20.0, "calculated_position_size": 0.02, "required_margin_usdt": 50.0, "estimated_liquidation_price": 47500.0, "is_safe": true}` |

---

## 🎛️ 9. Bot Operations & Circuit Breaker

| Method | Endpoint | Deskripsi | Payload | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/bot/status` | Status live bot, WebSocket, dan scheduler | None | `{"is_running": true, "is_paused": false, "trading_status": "ACTIVE", "binance_ws_connected": true}` |
| `POST` | `/api/v1/bot/pause` | Pause trading bot secara manual | None | `{"success": true, "message": "Bot paused"}` |
| `POST` | `/api/v1/bot/resume` | Resume trading bot | None | `{"success": true, "message": "Bot resumed"}` |
| `POST` | `/api/v1/bot/panic` | **PANIC CLOSE ALL** (Tutup semua posisi & batalkan order) | `{"confirmation": true}` | `{"success": true, "closed_trades_count": 2, "canceled_orders_count": 4}` |

---

## ⚙️ 10. Settings & Binance Key Rotation

| Method | Endpoint | Deskripsi | Payload | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/settings` | Ambil pengaturan bot & profil risiko | None | `{"default_leverage": 20, "risk_percent_per_trade": 2.0, "max_daily_loss_percent": 6.0}` |
| `PUT` | `/api/v1/settings` | Simpan pembaruan setting ke database | `{"default_leverage": 15, "max_daily_loss_percent": 6.0}` | `{"default_leverage": 15, ...}` |
| `POST` | `/api/v1/settings/credentials` | Tambah/rotasi Binance API Key dengan uji handshake | `{"api_key": "...", "secret_key": "...", "environment": "TESTNET"}` | `{"success": true, "wallet_balance_usdt": 1000.0}` |

---

## 📜 11. System Logs & Audit Trail

| Method | Endpoint | Deskripsi | Query Params | Response Sukses (200) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/logs` | Ambil log sistem | `level=INFO&trace_id=sig-a1b2&limit=100` | `[{"id": 1, "level": "INFO", "module": "EXECUTION_ENGINE", "message": "...", "trace_id": "sig-a1b2"}]` |

---

## 🔴 12. Real-Time WebSocket Streaming (`/api/v1/ws`)

* **Koneksi**: `ws://localhost:8000/api/v1/ws?token=<JWT_TOKEN>`
* **Fungsi**: Push event secara real-time ke UI browser tanpa perlu polling atau refresh halaman.
* **Event Payloads**:
  * `TRADE_OPENED`: Posisi baru berhasil dieksekusi.
  * `ORDER_FILLED`: Order entry, SL, atau TP terisi di bursa Binance.
  * `TP_HIT`: Take profit tersentuh (termasuk status SL geser ke BEP / Trailing).
  * `SL_HIT`: Stop loss tersentuh.
  * `TRADE_CLOSED`: Posisi ditutup penuh.
  * `CIRCUIT_BREAKER_TRIGGERED`: Alert darurat auto-pause jika limit rugi harian tercapai.
  * `TICKER_UPDATE`: Update harga live untuk menghitung *Unrealized PnL* secara real-time.
