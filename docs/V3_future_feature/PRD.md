# PRD: SMC QuantEngine

## Executive Summary & Product Vision

SMC QuantEngine is a high-frequency, fully automated algorithmic trading platform for Binance USD-M Futures. The system leverages a sophisticated, asynchronous Python backend built on a Hexagonal Architecture to execute trading strategies based on Smart Money Concepts (SMC). The core engine is designed for high performance, reliability, and precision, operating 24/7 without manual intervention.

The product vision is to provide a production-grade, institutional-quality trading engine that empowers quantitative traders to deploy, monitor, and manage complex SMC strategies with robust risk controls and real-time operational transparency.

## Problem Statement & Target Users

-   **Problem**: Manual application of SMC trading is labor-intensive, susceptible to emotional decision-making, and difficult to scale across multiple assets. Existing automated solutions often lack the nuanced logic required for SMC, have poor risk management, or are not architected for high-reliability, low-latency production environments.
-   **Target Users**:
    -   **Quantitative Traders**: Professionals seeking to automate and systematize their existing SMC-based strategies.
    -   **Advanced Retail Traders**: Experienced traders transitioning from discretionary to fully algorithmic trading.
    -   **Python Developers**: Technologists in finance requiring a robust, scalable framework for crypto algorithm development.

## System Scope & User Roles

The system is a backend-first trading engine. It autonomously scans a dynamic watchlist, identifies SMC-based trade setups, calculates risk-adjusted position sizes, executes trades via the Binance API, and provides real-time monitoring and control through a FastAPI web API and a Telegram bot.

| Role | System Control | Watchlist Mgmt | Trade Overrides | View PnL/Status |
|:-------|:---------------|:---------------|:----------------|:----------------|
| Admin | Full | Read/Write | Yes | Yes |
| Trader | None | Read-Only | Yes | Yes |

## Functional Requirements

**User-Facing & Control (Telegram/API)**
-   **FR-01**: The system must send real-time notifications via Telegram for trade signal generation, order execution confirmation (entry, TP, SL), and position closure.
-   **FR-02**: The Telegram bot must provide a high-priority `/close_all` command that immediately liquidates all open positions at market price.
-   **FR-03**: The Telegram bot must respond to a `/status` command with a summary of current account equity, unrealized PnL, and a list of all open positions.
-   **FR-04**: The FastAPI backend must expose a `/v1/overview` endpoint that provides a minimalist, high-level summary including total equity, daily PnL, and active trade count for dashboard integration.
-   **FR-05**: The FastAPI backend must provide endpoints (`/v1/watchlist`) to dynamically add or remove trading symbols from the scanner's active watchlist without requiring a system restart.

**Core Trading & System Logic**
-   **FR-06**: A background worker (SMC Scanner) must periodically iterate through the active watchlist, fetching 4H and 15m OHLCV data from Binance.
-   **FR-07**: The algorithm must enforce a Higher Timeframe (HTF) bias. Long (BUY) signals on the 15m timeframe are only valid if the 4H candle close is above its 50-period EMA. Short (SELL) signals are only valid if the 4H close is below its 50 EMA.
-   **FR-08**: The SMC logic must identify unmitigated Fair Value Gaps (FVGs) within the last 3-4 closed 15m candles and the associated Order Block (OB) that initiated the move.
-   **FR-09**: The Execution Engine must calculate position size to risk a maximum of 2% of total account equity per trade. The calculation is based on the distance between the entry price and the stop-loss level.
-   **FR-10**: Before placing an order, the calculated position size must be validated against Binance's symbol-specific constraints (e.g., `minNotional`, `tickSize`, `stepSize`). If validation fails, the trade must be rejected and a log/alert generated.
-   **FR-11**: For a valid signal, the system will place a LIMIT entry order at the proximal edge of the Order Block, with an associated STOP_MARKET order for the Stop Loss and a TAKE_PROFIT_MARKET order for the Take Profit (targeting a minimum 1:2 Risk/Reward Ratio).
-   **FR-12**: A dedicated WebSocket listener must maintain a real-time connection to the Binance User Data Stream, synchronizing order updates and position changes to the PostgreSQL database to ensure state consistency.
-   **FR-13**: The system must implement a master failsafe mechanism. Upon critical, unrecoverable errors (e.g., repeated authentication failures, database connection loss), all scanning and trade execution must be paused, and a high-priority alert must be dispatched via Telegram.

## Non-Functional Requirements

| Category | Requirement | Target |
|:--------------|:-------------------------------------------------------------------------|:--------------------------------------|
| **Performance** | End-to-end signal detection to order placement latency. | < 500 ms |
| | WebSocket order status update propagation to database. | < 100 ms |
| **Scalability** | Concurrent symbols processed by the SMC Scanner. | Up to 100 symbols |
| | API requests handled by the FastAPI dashboard service. | 1,000 RPM |
| **Reliability** | Uptime for the core trading engine and workers. | 99.9% |
| | API Error Handling for `RateLimitExceeded` and `NetworkError`. | Exponential backoff and retry mechanism |
| **Security** | Storage of exchange API keys and other secrets. | AWS Secrets Manager; not in codebase |
| | Network Access Control. | No direct public internet access to DB |

## Technology Stack & Rationale

| Component | Technology | Rationale |
|:---------------------|:-----------------------------------------|:-----------------------------------------------------------------------|
| Language | Python 3.10+ | Superior `asyncio` support for I/O-bound tasks; rich data science ecosystem. |
| Web Framework | FastAPI | High-performance ASGI framework with built-in data validation and docs. |
| Database | PostgreSQL | Proven reliability and performance for transactional financial data. |
| ORM / DB Driver | SQLAlchemy 2.0 / `asyncpg` | Industry-standard async ORM providing robust, type-safe database access. |
| Exchange Connector | `ccxt.pro` | Unified, high-performance async library with built-in WebSocket support. |
| Data Analysis | `pandas`, `pandas-ta` | Efficient for time-series manipulation and technical indicator calculation. |
| Task Scheduling | APScheduler | Lightweight, powerful in-process scheduler for recurring background jobs. |
| Containerization | Docker | Ensures consistent, portable deployments across environments. |
| Hosting | AWS ECS on Fargate | Serverless container orchestration for scalable, resilient microservices. |
| Secrets Management | AWS Secrets Manager | Securely manages and rotates sensitive credentials, avoiding hardcoding. |
| Monitoring & Logging | Prometheus, Grafana, Loki | Industry-standard stack for metrics, visualization, and log aggregation. |

## Success Metrics & KPIs

| Metric | KPI | Target Value |
|:------------------------|:--------------------------------------|:------------------|
| **Profitability** | Sharpe Ratio (risk-adjusted return) | > 1.5 (3-mo avg) |
| **Risk Management** | Maximum Account Drawdown | < 20% |
| **Performance** | P95 Signal-to-Execution Latency | < 500ms |
| **Reliability** | Core Engine Uptime | 99.9% |
| **Strategy Efficacy** | Trade Win Rate (with >= 1:2 R:R) | > 40% |

## Risk Analysis & Mitigation

| Risk | Impact | Mitigation Strategy |
|:--------------------------------------------|:-------|:----------------------------------------------------------------------------------------------------------------|
| Exchange API Downtime or Latency | High | Implement exponential backoff for all API calls. Utilize `ccxt`'s built-in error handling. Failsafe pause on repeated failures. |
| State Desynchronization (Bot vs. Exchange) | High | Primary sync via real-time WebSocket user stream. Secondary periodic REST API poll to reconcile all open positions/orders. |
| Critical Bug in Trading Logic | High | Mandatory code reviews for all logic changes. Rigorous unit/integration tests. Pre-production deployment in Shadow Trading Mode. |
| Volatility-Induced Slippage | Medium | Use LIMIT orders for entries to control price. For emergency market exits, monitor execution price against expected price and alert on high deviation. |

## Constraints & Assumptions

-   **Constraints**:
    -   The initial version will exclusively support Binance USD-M Futures.
    -   The system must operate strictly within Binance's documented API rate limits.
    -   The entire backend codebase must be asynchronous, leveraging the `asyncio` library.
-   **Assumptions**:
    -   The user possesses a valid Binance account with API keys configured for Futures trading.
    -   The underlying SMC strategy is presumed to be viable. This document specifies implementation, not strategy design.
    -   The hosting environment provides a stable, low-latency network connection to Binance servers.

## Out of Scope

-   A graphical user interface (GUI) or frontend web application. This PRD covers the backend API only.
-   Integration with any exchange other than Binance USD-M Futures.
-   A historical backtesting engine.
-   Machine learning models for strategy optimization or parameter tuning.
-   The following advanced features, which are deferred to a future release:
    -   Dynamic ATR-based Trailing Stop Loss
    -   Dynamic Risk Scaling (Drawdown Limiter)
    -   Funding Rate Arbitrage/Avoidance Logic
    -   Advanced Technical Confluence Validator (e.g., RSI/VWAP checks)
    -   Shadow Trading Mode (Paper Trading)