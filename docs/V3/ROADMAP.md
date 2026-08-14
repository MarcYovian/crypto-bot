# ROADMAP.md: SMC QuantEngine

## Phased Delivery Plan

This roadmap outlines the planned phases for the development and deployment of the SMC QuantEngine. The timeline is an estimate and may be adjusted based on team velocity, unforeseen challenges, and evolving requirements.

Timeline assumes a team of 3 developers. Adjust proportionally for different team sizes.

| Phase | Duration | Goals |
|:---|:---|:---|
| **Phase 1: Foundation & Core Infrastructure** | 4 Weeks | Establish project architecture, set up development environment, implement core data access layer, basic API and Telegram bot frameworks, and initial exchange connectivity. Focus on robust, scalable foundations. |
| **Phase 2: SMC Logic & Execution Engine MVP** | 6 Weeks | Implement the core Smart Money Concepts (SMC) scanning logic, risk management, and the trade execution engine. Achieve end-to-end automated trading for a single symbol in a controlled environment. |
| **Phase 3: Stability, Monitoring & P1 Features** | 4 Weeks | Enhance system stability, implement comprehensive logging and monitoring, and integrate essential P1 features. Prepare the system for broader deployment and initial live trading with strict oversight. |
| **Phase 4: Advanced Features & Optimization** | Ongoing | Develop and integrate P2 advanced features, perform performance optimizations, and scale the system to handle a larger watchlist and more complex scenarios. |

## MVP Feature List

This section details the Minimum Viable Product (MVP) features, categorized by priority for release. Feature codes (FR-XX) refer to the Functional Requirements defined in `PRD.md`.

### P0: Must Have (Initial Launch)

These features are critical for the initial operational launch of the SMC QuantEngine.

*   **Core Infrastructure**
    *   Project structure, configuration management (`backend/config/`).
    *   Database setup (PostgreSQL, SQLAlchemy 2.0 asyncpg) and ORM models (`backend/src/database/`).
    *   Basic repository implementations (`backend/src/repository/`).
    *   `ccxt.pro` integration for market data and order management.
    *   Dockerization for consistent deployment.
*   **SMC Scanning & Signal Generation**
    *   FR-06: Background worker for periodic watchlist iteration.
    *   FR-07: Higher Timeframe (4H EMA 50) bias enforcement.
    *   FR-08: Identification of unmitigated Fair Value Gaps (FVGs) and Order Blocks (OBs) on 15m timeframe.
*   **Risk Management & Position Sizing**
    *   FR-09: Dynamic position sizing based on 2% max equity risk per trade.
    *   FR-10: Validation of calculated position size against Binance symbol constraints (`minNotional`, `tickSize`, `stepSize`).
*   **Order Execution**
    *   FR-11: Placement of LIMIT entry, STOP_MARKET (SL), and TAKE_PROFIT_MARKET (TP) orders for valid signals.
*   **State Synchronization & Failsafe**
    *   FR-12: Real-time WebSocket listener for Binance User Data Stream to synchronize order and position states.
    *   FR-13: Master failsafe mechanism to pause operations and alert on critical errors.
*   **User Interaction & Monitoring (Telegram & FastAPI)**
    *   FR-01: Real-time Telegram notifications for trade events (signals, execution, closure).
    *   FR-02: Telegram `/close_all` command for emergency liquidation.
    *   FR-03: Telegram `/status` command for account summary and open positions.
    *   FR-04: FastAPI `/v1/overview` endpoint for high-level dashboard summary.
    *   FR-05: FastAPI `/v1/watchlist` endpoints for dynamic watchlist management.

### P1: Should Have (Within 1 Month Post-Launch)

These features enhance the system's robustness, usability, and operational transparency shortly after the initial launch.

*   **Enhanced Logging & Alerting**:
    *   Detailed logging for all trade rejections, API errors, and critical system events.
    *   Specific Telegram alerts for non-critical but important events (e.g., watchlist update failures, minor API issues).
*   **Monitoring & Metrics**:
    *   Exposure of key operational metrics (e.g., scanner latency, trade execution time, API call counts, error rates) via Prometheus.
    *   Basic Grafana dashboards for system health and performance.
*   **Order Management Refinements**:
    *   Robust handling of partial order fills and order cancellation logic.
    *   Improved error recovery mechanisms for background workers.
*   **Configuration Management**:
    *   Dynamic update of strategy parameters (e.g., R:R ratio, slippage buffer) via API without restart.

### P2: Nice to Have (Future Development)

These advanced features are planned for later stages, focusing on strategy optimization, enhanced risk control, and operational flexibility.

*   **Dynamic Trailing Stop**: ATR-based trailing Stop Loss implementation via `pandas-ta`.
*   **Drawdown Limiter**: Dynamic risk scaling mechanism to reduce risk percentage after consecutive losses.
*   **Funding Rate Guard**: Logic to reject trades if funding fees are extreme and settlement is imminent.
*   **Technical Confluence Validator**: Integration of additional technical indicators (e.g., VWAP, RSI) for signal validation.
*   **Shadow Trading Mode**: A paper trading environment that captures simulated fill prices and stores them in the database for strategy testing.
*   **Advanced Monitoring**: More sophisticated Grafana dashboards, anomaly detection.
*   **Historical Data Backfill**: Tools for backfilling historical market data for analysis.

## Milestones

Key milestones marking significant progress in the SMC QuantEngine development.

| Milestone | Phase | Target Date | Deliverables |
|:---|:---|:---|:---|
| **M1: Core Infrastructure Ready** | Phase 1 | Week 4 | Project structure, database, basic FastAPI/Telegram, `ccxt.pro` data fetching, Docker setup. |
| **M2: SMC Scanner Operational** | Phase 2 | Week 7 | HTF bias, FVG/OB detection, signal generation logic implemented and tested. |
| **M3: Execution Engine Live** | Phase 2 | Week 10 | Position sizing, order placement (LIMIT, SL, TP), WebSocket sync, and master failsafe fully functional. |
| **M4: Production Readiness** | Phase 3 | Week 14 | Comprehensive logging, Prometheus metrics, initial Grafana dashboards, P1 features integrated, full test suite passed. |
| **M5: Advanced Features Kick-off** | Phase 4 | Week 18 | Dynamic Trailing Stop and Drawdown Limiter implemented and undergoing testing. |
| **M6: Full Feature Set** | Phase 4 | TBD | Funding Rate Guard, Technical Confluence Validator, and Shadow Trading Mode implemented. |

## Dependencies

Successful execution of the roadmap relies on several internal and external dependencies.

### External Dependencies

*   **Binance API Keys**: Valid API Key and Secret with Futures trading permissions.
*   **Telegram Bot Token**: A registered Telegram bot token for notifications and commands.
*   **AWS Account**: Access to AWS services (ECS, Fargate, Secrets Manager, RDS for PostgreSQL) for deployment and secure credential management.
*   **PostgreSQL Instance**: A managed PostgreSQL database instance (e.g., AWS RDS) for production data.
*   **Internet Connectivity**: Stable, low-latency internet connection to Binance API endpoints.

### Internal Dependencies

*   `PRD.md`: The Product Requirements Document serves as the primary source of truth for all functional and non-functional requirements.
*   `ARCHITECTURE.md`: Detailed system architecture and design specifications.
*   `API.md`: Comprehensive documentation of all FastAPI endpoints, request/response schemas, and authentication.
*   `DATABASE.md`: Detailed database schema definitions, including tables, relationships, and data types.
*   `TESTING.md`: Test plans, strategies, and coverage requirements for unit, integration, and system tests.
*   **SMC Pattern Design**: Detailed specifications for FVG and Order Block identification logic, including edge cases and parameters.

## Risks & Mitigation

A comprehensive assessment of potential risks and their corresponding mitigation strategies.

| Risk | Impact | Probability | Mitigation |
|:---|:---|:---|:---|
| **Exchange API Downtime or Latency** | High (missed trades, incorrect fills, state desync) | Medium | Implement exponential backoff and retry mechanisms for all API calls. Utilize `ccxt.pro`'s robust error handling. Trigger master failsafe (FR-13) on prolonged or critical API issues. |
| **State Desynchronization (Bot vs. Exchange)** | High (incorrect position sizing, phantom positions, unexpected losses) | Medium | Primary synchronization via real-time WebSocket user data stream (FR-12). Implement periodic reconciliation of open positions/orders via REST API. Provide manual `/close_all` override (FR-02). |
| **Critical Bug in Trading Logic** | High (significant financial losses) | Medium | Mandatory code reviews, comprehensive unit and integration testing (`TESTING.md`). Implement pre-production Shadow Trading Mode (P2). Enforce strict risk limits (FR-09) and master failsafe (FR-13). |
| **Volatility-Induced Slippage** | Medium (reduced profitability, higher losses) | Medium | Use LIMIT orders for entry (FR-11) to control execution price. For emergency market exits, monitor execution price against expected price and alert on high deviation. |
| **Rate Limit Exceeded by Exchange** | Medium (missed opportunities, delayed execution) | High | Leverage `ccxt.pro`'s built-in rate limit management. Optimize scanner iteration to only active watchlist symbols. Implement intelligent request queuing and caching for static data. |
| **Database Corruption or Downtime** | High (loss of trade history, incorrect state, operational halt) | Low | Utilize managed PostgreSQL with high availability (replication, failover). Implement regular database backups. Employ robust ORM usage (SQLAlchemy) and connection pooling. Trigger failsafe (FR-13) on persistent database connection loss. |
| **Scope Creep** | Medium (delayed delivery, resource strain, reduced quality) | Medium | Strict adherence to `PRD.md` and this `ROADMAP.md`. Clear definition of MVP (P0) and deferral of P1/P2 features. Regular stakeholder reviews to manage expectations and prioritize. |