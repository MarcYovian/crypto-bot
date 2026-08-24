# Web Dashboard API Development Roadmap

Roadmap implementasi REST & WebSocket API untuk Web Dashboard UI Crypto Trading Bot berdasarkan spesifikasi OpenAPI 3.1.0 di [`docs/openapi.yaml`](file:///home/rodex/Documents/cell/projects/crypto-bot/docs/openapi.yaml).

---

## 📋 Daftar Rincian Task

| No | Task File | Cakupan Endpoint / Modul | Status |
| :---: | :--- | :--- | :---: |
| **01** | [`01_app_setup_and_auth.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/01_app_setup_and_auth.md) | FastAPI Core Setup, JWT Security, In-Memory Async Cache (`AsyncInMemoryCache`), `/auth/login`, `/auth/refresh`, `/auth/me` | ✅ Done |
| **02** | [`02_analytics_and_dashboard_summary.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/02_analytics_and_dashboard_summary.md) | `/analytics/summary` (Cached TTL 10s), `/analytics/equity-curve` (Cached TTL 60s) | ✅ Done |
| **03** | [`03_trades_and_positions_management.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/03_trades_and_positions_management.md) | `/trades/active`, `/trades/history`, `/trades/{id}`, `/trades/{id}/close` | ✅ Done |
| **04** | [`04_signals_and_manual_execution.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/04_signals_and_manual_execution.md) | `/signals`, `/signals/manual-execute` (Strict 2% Risk Check) | ✅ Done |
| **05** | [`05_watchlist_and_instruments.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/05_watchlist_and_instruments.md) | `/watchlist` (Cached & Invalidate on Toggle), `/instruments` (Cached TTL 30m & Invalidate on Sync) | ✅ Done |
| **06** | [`06_signal_providers_and_strategies.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/06_signal_providers_and_strategies.md) | `/providers` (Cached), `/providers/{id}/analytics` (Cached TTL 30s), `/strategies` (Cached) | ✅ Done |
| **07** | [`07_risk_simulator_sandbox.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/07_risk_simulator_sandbox.md) | `/calculator/simulate` (Live position sizing & liquidation simulation) | ✅ Done |
| **08** | [`08_bot_operations_and_settings.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/08_bot_operations_and_settings.md) | `/bot/status`, `/bot/pause`, `/bot/resume`, `/bot/panic`, `/settings` (Cached), `/credentials` | ✅ Done |
| **09** | [`09_logs_and_reports.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/09_logs_and_reports.md) | `/logs`, `/reports/export/csv` | ✅ Done |
| **10** | [`10_realtime_websocket_stream.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/10_realtime_websocket_stream.md) | `/ws` (Realtime event broker: trades, order fills, PnL, status) | ✅ Done |
| **11** | [`11_app_wiring_main_integration.md`](file:///home/rodex/Documents/cell/projects/crypto-bot/tasks/web_dashboard_api/11_app_wiring_main_integration.md) | Integrasi FastAPI + Telegram Polling + Background Cron di `main.py` | ⏳ Pending |

---

## 🛡️ Standar Pengujian Setiap Task:
1. **Unit & Route Tests**: Setiap router memiliki test file khusus di `backend/tests/api/`.
2. **Type Safety**: `mypy --explicit-package-bases --ignore-missing-imports backend/src/` harus lolos tanpa error.
3. **OpenAPI Spec Compliance**: Request dan Response payload harus 100% konsisten dengan skema di `docs/openapi.yaml`.
