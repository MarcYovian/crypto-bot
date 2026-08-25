# 📋 Master Roadmap: Clean Architecture Refactoring (Granular Tasks)

Dokumen ini berisi peta jalan terperinci, pelacak progres, dan rincian seluruh task modular di mana setiap file repository terfokus pada 1 model dengan file test dan test cases spesifik.

---

## 🗂️ Daftar Seluruh Task

### 📦 PHASE 1: Data Access Layer (Repositories)

| Task ID | Nama File Task | Target Repository | Model Database | Target Unit Test | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **01** | [`01_repo_base.md`](./01_repo_base.md) | `base.py` | Generic Base | `tests/repository/test_base_repository.py` | ✅ Completed |
| **02** | [`02_repo_exchange.md`](./02_repo_exchange.md) | `exchange_repository.py` | `Exchange` | `tests/repository/test_exchange_repository.py` | ✅ Completed |
| **03** | [`03_repo_trading_account_and_credential.md`](./03_repo_trading_account_and_credential.md) | `trading_account_repository.py`<br>`trading_credential_repository.py` | `TradingAccount`<br>`TradingCredential` | `tests/repository/test_account_credential_repository.py` | ✅ Completed |
| **04** | [`04_repo_instrument_and_watchlist.md`](./04_repo_instrument_and_watchlist.md) | `instrument_repository.py`<br>`watchlist_repository.py` | `Instrument`<br>`Watchlist` | `tests/repository/test_instrument_watchlist_repository.py` | ✅ Completed |
| **05** | [`05_repo_strategy_provider_risk_profile.md`](./05_repo_strategy_provider_risk_profile.md) | `strategy_repository.py`<br>`signal_provider_repository.py`<br>`risk_profile_repository.py` | `Strategy`<br>`SignalProvider`<br>`RiskProfile` | `tests/repository/test_master_config_repositories.py` | ✅ Completed |
| **06** | [`06_repo_signal.md`](./06_repo_signal.md) | `signal_repository.py` | `TradingSignal` | `tests/repository/test_signal_repository.py` | ✅ Completed |
| **07** | [`07_repo_daily_and_trade_risk.md`](./07_repo_daily_and_trade_risk.md) | `daily_risk_repository.py`<br>`trade_risk_repository.py` | `DailyRiskConfig`<br>`TradeRisk` | `tests/repository/test_risk_repositories.py` | ✅ Completed |
| **08** | [`08_repo_trade.md`](./08_repo_trade.md) | `trade_repository.py` | `Trade` | `tests/repository/test_trade_repository.py` | ✅ Completed |
| **09** | [`09_repo_order_and_execution.md`](./09_repo_order_and_execution.md) | `order_repository.py`<br>`execution_repository.py` | `Order`<br>`Execution` | `tests/repository/test_order_execution_repositories.py` | ✅ Completed |
| **10** | [`10_repo_trade_event_and_summary.md`](./10_repo_trade_event_and_summary.md) | `trade_event_repository.py`<br>`trade_summary_repository.py` | `TradeEvent`<br>`TradeSummary` | `tests/repository/test_event_summary_repositories.py` | ✅ Completed |
| **11** | [`11_repo_bot_setting_and_log.md`](./11_repo_bot_setting_and_log.md) | `bot_setting_repository.py`<br>`bot_log_repository.py` | `BotSetting`<br>`BotLog` | `tests/repository/test_system_repositories.py` | ✅ Completed |

---

### 🌐 PHASE 2: Third-Party Clients (External I/O)

| Task ID | Nama File Task | Target Client Modul | Deskripsi | Target Unit Test | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **12** | [`12_client_binance.md`](./12_client_binance.md) | `src/clients/binance_client.py` | CCXT Async REST & WebSocket stream | `tests/clients/test_binance_client.py` | ✅ Completed |
| **13** | [`13_client_telegram.md`](./13_client_telegram.md) | `src/clients/telegram_client.py` | Bot API notifier & inline keyboard markup | `tests/clients/test_telegram_client.py` | ✅ Completed |

---

### 🧠 PHASE 3: Business Logic & Orchestrator Services

| Task ID | Nama File Task | Target Service Modul | Deskripsi | Target Unit Test | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **14** | [`14_service_signal_parser_and_risk_calculator.md`](./14_service_signal_parser_and_risk_calculator.md) | `signal_parser.py`<br>`risk_calculator.py`<br>`precision_filter.py` | Signal parsing & strict 2.0% risk sizing | `tests/services/test_signal_risk_services.py` | ✅ Completed |
| **15** | [`15_service_trade_and_position_manager.md`](./15_service_trade_and_position_manager.md) | `trade_service.py`<br>`position_manager.py` | Trade execution orchestrator & Position lifecycle state machine | `tests/services/test_trade_position_services.py` | ✅ Completed |
| **16** | [`16_service_scheduler_and_telegram_bot.md`](./16_service_scheduler_and_telegram_bot.md) | `scheduler_service.py`<br>`telegram_service.py` | 7 background cron jobs & 12 Telegram bot interactive commands | `tests/services/test_scheduler_telegram_services.py` | ✅ Completed |

---

### 🚀 PHASE 4: Application Wiring & Verification

| Task ID | Nama File Task | Target Modul | Deskripsi | Target Verification | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **17** | [`17_app_wiring_and_docker_verification.md`](./17_app_wiring_and_docker_verification.md) | `main.py`<br>`docker-compose.yml` | Dependency injection, graceful shutdown, Docker E2E | `tests/test_e2e_integration.py` + Docker check | ✅ Completed |

---

### 🌐 PHASE 5: Web Dashboard REST & WebSocket API
Lihat roadmap rincian backend API di [`tasks/web_dashboard_api/README.md`](./web_dashboard_api/README.md).

---

### 💻 PHASE 6: Web Dashboard UI Frontend SPA
Lihat roadmap rincian frontend UI di [`tasks/frontend/README.md`](./frontend/README.md).

