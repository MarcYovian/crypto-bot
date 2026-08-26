# REQUIREMENTS.md: SMC QuantEngine

## Functional Requirements

### User-Facing & Control Layer (Telegram Bot & Web API)

#### FR-01: Real-Time Trade Notifications via Telegram
**Requirement**: The system MUST send real-time notifications via Telegram (python-telegram-bot v20+) for all critical trading events: signal generation, order execution confirmation (entry fill, TP hit, SL hit), and position closure.

**Acceptance Criteria**:
- Notification is dispatched within 2 seconds of order state change in the Binance User Data Stream.
- Message includes: symbol, side (BUY/SELL), entry price, position size, SL level, TP level, and timestamp.
- Failed notifications do not block order execution; retry logic uses exponential backoff (max 3 retries, 5s initial delay).

#### FR-02: Emergency Close-All Command
**Requirement**: The Telegram bot MUST provide a `/close_all` command that immediately liquidates all open positions at market price, bypassing normal signal validation.

**Acceptance Criteria**:
- Command is restricted to users with `Admin` role (verified via JWT or hardcoded chat ID).
- All open positions are closed via MARKET orders within 5 seconds of command receipt.
- A confirmation message is sent to Telegram with count of closed positions and total realized PnL.
- If any market order fails, the system retries up to 2 times before alerting the user.

#### FR-03: Status Command
**Requirement**: The Telegram bot MUST respond to `/status` with a concise summary of account state and open positions.

**Acceptance Criteria**:
- Response includes: total account equity, unrealized PnL (in USD and %), number of open positions, and current daily PnL.
- Response is generated within 1 second by querying the PositionManager service.
- If database is unreachable, a fallback message is sent: "Status unavailable. System failsafe may be active."

#### FR-04: Dashboard Overview Endpoint
**Requirement**: The FastAPI backend MUST expose a `GET /v1/overview` endpoint that provides a minimalist, high-level summary for dashboard integration.

**Acceptance Criteria**:
- Response schema includes: `total_equity`, `daily_pnl`, `daily_pnl_percent`, `active_trade_count`, `unrealized_pnl`, `last_updated_at`.
- Response time is < 200 ms (cached for max 5 seconds).
- Endpoint is accessible to both `Admin` and `Trader` roles.
- If no trades exist, `active_trade_count` is 0 and `unrealized_pnl` is 0.

#### FR-05: Dynamic Watchlist Management
**Requirement**: The FastAPI backend MUST provide endpoints to dynamically add or remove trading symbols from the active watchlist without requiring a system restart.

**Acceptance Criteria**:
- `POST /v1/watchlist` accepts a JSON body with `symbol` (e.g., "BTCUSDT") and `action` ("add" or "remove").
- Changes are persisted to the `watchlist` table in PostgreSQL immediately.
- The SMC Scanner picks up changes within the next scan cycle (max 60 seconds).
- Attempting to add a duplicate symbol returns HTTP 409 Conflict; removing a non-existent symbol returns HTTP 404.
- Only `Admin` role can modify the watchlist.

---

### Core Trading & Execution Logic

#### FR-06: Background SMC Scanner Worker
**Requirement**: A background worker (SMC Scanner) MUST periodically iterate through the active watchlist, fetching 4H and 15m OHLCV data from Binance via `ccxt.pro`.

**Acceptance Criteria**:
- Scanner runs every 60 seconds (configurable via environment variable `SCANNER_INTERVAL_SECONDS`).
- For each symbol in the watchlist, the scanner fetches the last 50 candles (4H) and last 20 candles (15m) to ensure sufficient history for EMA and FVG calculations.
- If a symbol fetch fails due to `RateLimitExceeded`, the scanner implements exponential backoff and retries up to 3 times before skipping that symbol.
- Fetch errors are logged with symbol name and error code; critical errors trigger the failsafe mechanism (FR-13).

#### FR-07: Higher Timeframe (HTF) Bias Enforcement
**Requirement**: The algorithm MUST enforce a Higher Timeframe bias. Long (BUY) signals on the 15m timeframe are only valid if the 4H candle close is above its 50-period EMA. Short (SELL) signals are only valid if the 4H close is below its 50 EMA.

**Acceptance Criteria**:
- EMA 50 is calculated on the last 50 closed 4H candles using `pandas-ta.ema()`.
- A BUY signal is rejected if `4h_close <= ema_50`. A SELL signal is rejected if `4h_close >= ema_50`.
- The bias check is logged with symbol, 4H close price, EMA 50 value, and decision (accept/reject).
- If 4H data is missing or insufficient (< 50 candles), the signal is rejected and a warning is logged.

#### FR-08: Fair Value Gap (FVG) & Order Block (OB) Identification
**Requirement**: The SMC logic MUST identify unmitigated Fair Value Gaps (FVGs) within the last 3–4 closed 15m candles and the associated Order Block (OB) that initiated the move.

**Acceptance Criteria**:
- FVG is defined as a gap between candle N and candle N+2 (i.e., candle N+1 does not overlap the gap).
- For a bullish FVG: `candle_n.high < candle_n+2.low`. For a bearish FVG: `candle_n.low > candle_n+2.high`.
- Order Block is the last candle before the impulse move (candle N in the above definition).
- Mitigation check: current price must NOT have retraced into the OB zone. If price is inside the OB, the signal is rejected.
- FVG and OB levels are logged with symbol, FVG range (high/low), OB range, and mitigation status.

#### FR-09: Position Size Calculation (2% Risk Rule)
**Requirement**: The Execution Engine MUST calculate position size to risk a maximum of 2% of total account equity per trade, based on the distance between entry price and stop-loss level.

**Acceptance Criteria**:
- Formula: `position_size_usd = (account_equity * 0.02) / (abs(entry_price - sl_price) / entry_price)`.
- Position size is calculated in USD notional value, then converted to contract quantity using current mark price.
- If calculated position size is < 0.001 contracts (minimum), it is rounded up to 0.001; if it exceeds max position size per symbol (from Binance limits), it is capped.
- Calculation is logged with symbol, account equity, entry price, SL price, and resulting position size.

#### FR-10: Binance Symbol Constraint Validation
**Requirement**: Before placing an order, the calculated position size MUST be validated against Binance's symbol-specific constraints. If validation fails, the trade MUST be rejected and a log/alert generated.

**Acceptance Criteria**:
- Constraints checked: `minNotional` (minimum order value in USDT), `stepSize` (position quantity precision), `tickSize` (price precision).
- If `position_size_usd < minNotional`, trade is rejected with reason "Position size below minimum notional."
- If position quantity cannot be rounded to `stepSize`, trade is rejected with reason "Position size does not meet step size requirement."
- If entry or SL price cannot be rounded to `tickSize`, trade is rejected with reason "Price does not meet tick size requirement."
- All rejections are logged and a Telegram alert is sent to the admin.

#### FR-11: Multi-Leg Order Placement (Entry, SL, TP)
**Requirement**: For a valid signal, the system MUST place a LIMIT entry order at the proximal edge of the Order Block, with an associated STOP_MARKET order for Stop Loss and a TAKE_PROFIT_MARKET order for Take Profit (targeting a minimum 1:2 Risk/Reward Ratio).

**Acceptance Criteria**:
- Entry order is placed as LIMIT at the OB edge price (rounded to `tickSize`).
- SL order is placed as STOP_MARKET slightly beyond the OB (with a 0.5% slippage buffer), rounded to `tickSize`.
- TP order is placed as TAKE_PROFIT_MARKET at a level ensuring minimum 1:2 R:R: `tp_price = entry_price + 2 * (entry_price - sl_price)`.
- All three orders are submitted to Binance within 500 ms of signal confirmation.
- If entry order fails, SL and TP orders are NOT placed. If SL or TP placement fails, a Telegram alert is sent and the entry order is manually cancelled.
- Order IDs and timestamps are logged and persisted to the `orders` table.

#### FR-12: Real-Time WebSocket Order Synchronization
**Requirement**: A dedicated WebSocket listener MUST maintain a real-time connection to the Binance User Data Stream, synchronizing order updates and position changes to the PostgreSQL database to ensure state consistency.

**Acceptance Criteria**:
- WebSocket connection is established on system startup and reconnects automatically if disconnected (exponential backoff, max 10 retries).
- Order updates (FILLED, PARTIALLY_FILLED, CANCELED, REJECTED) are received within 100 ms of execution on Binance.
- Position updates (quantity, entry price, unrealized PnL) are written to the `positions` table within 100 ms of receipt.
- If WebSocket is disconnected for > 30 seconds, a failsafe alert is triggered (FR-13).
- A secondary periodic REST API poll (every 5 minutes) reconciles all open positions/orders to detect any missed WebSocket events.

#### FR-13: Master Failsafe Mechanism
**Requirement**: The system MUST implement a master failsafe mechanism. Upon critical, unrecoverable errors, all scanning and trade execution MUST be paused, and a high-priority alert MUST be dispatched via Telegram.

**Acceptance Criteria**:
- Critical errors include: repeated Binance authentication failures (3+ consecutive), database connection loss (> 60 seconds), WebSocket disconnection (> 30 seconds), or unhandled exceptions in core services.
- When failsafe is triggered, a `failsafe_active` flag is set in the database and all background workers are paused.
- A Telegram message is sent immediately: "🚨 FAILSAFE ACTIVATED: [reason]. All trading paused. Manual intervention required."
- The system logs the error with full stack trace and context (symbol, order ID, etc.).
- Failsafe can only be reset by an `Admin` user via a `/reset_failsafe` Telegram command or API endpoint.

---

## Non-Functional Requirements

| Category | Requirement | Measurable Target |
|:---|:---|:---|
| **Performance** | End-to-end signal detection to order placement latency | < 500 ms (P95) |
| | WebSocket order status update propagation to database | < 100 ms (P95) |
| | Dashboard `/v1/overview` endpoint response time | < 200 ms (P95) |
| **Scalability** | Concurrent symbols processed by SMC Scanner | Up to 100 symbols per scan cycle |
| | FastAPI dashboard API throughput | 1,000 requests per minute (RPM) |
| | Concurrent WebSocket connections | 1 primary + 1 backup (failover) |
| **Reliability** | Core trading engine uptime | 99.9% (max 43 minutes downtime per month) |
| | API error handling for `RateLimitExceeded` | Exponential backoff (1s, 2s, 4s, 8s) with max 3 retries |
| | API error handling for `NetworkError` | Exponential backoff with max 5 retries over 30 seconds |
| | Database connection pool recovery time | < 5 seconds after transient failure |
| **Security** | Exchange API key storage | AWS Secrets Manager; never in codebase or logs |
| | JWT token expiration | 24 hours; refresh tokens valid for 30 days |
| | Database network access | Private VPC; no direct public internet access |
| | Telegram bot token storage | AWS Secrets Manager; rotated every 90 days |
| **Data Integrity** | Order state consistency (bot vs. Binance) | Verified within 5 minutes via REST API reconciliation |
| | Trade history audit trail | All trades logged with entry/exit price, size, PnL, timestamp |
| | Position reconciliation frequency | Every 5 minutes (secondary sync) |
| **Observability** | Metrics collection interval | Every 10 seconds (Prometheus scrape) |
| | Log retention period | 90 days in Loki; 1 year in S3 archive |
| | Alert response time | < 1 minute from event to Telegram notification |

---

## Technical Constraints

### Hard Limitations

- **Language & Async Requirement**: All code MUST be written in Python 3.10+ using `asyncio`. Synchronous blocking calls are strictly prohibited in the core trading loop, API handlers, and database operations.
- **Exchange Exclusivity**: The initial version supports Binance USD-M Futures exclusively. Multi-exchange support is out of scope.
- **API Rate Limits**: The system MUST operate within Binance's documented rate limits (1,200 requests per minute for REST API; WebSocket connections are unlimited). Violations result in temporary IP bans.
- **Database**: PostgreSQL 13+ with `asyncpg` driver. No other database engines are supported.
- **Deployment Environment**: AWS ECS on Fargate. On-premises or alternative cloud deployments are not supported in the initial release.
- **Secrets Management**: All sensitive credentials (API keys, database passwords, JWT secrets) MUST be stored in AWS Secrets Manager. Hardcoding secrets in environment files or source code is a critical security violation.
- **Network Latency**: The hosting environment MUST provide a stable, low-latency connection to Binance servers (target < 100 ms round-trip time). High-latency connections may result in order slippage and missed signals.

### Architectural Constraints

- **Hexagonal Architecture**: The codebase MUST follow a strict Hexagonal (Ports & Adapters) pattern with clear separation of concerns:
  - **Core Domain**: Services (ExecutionEngine, SMCScanner, PositionManager, RiskCalculator) contain pure business logic with NO external dependencies.
  - **Ports**: Abstract interfaces for database, exchange API, and messaging (Telegram).
  - **Adapters**: Concrete implementations (PostgreSQL repository, CCXT exchange connector, Telegram bot).
- **Single Event Loop**: All asynchronous operations MUST run on a single `asyncio` event loop. No multi-threading or multi-processing for core trading logic.
- **No Blocking I/O**: Database queries, HTTP requests, and WebSocket operations MUST use async drivers (`asyncpg`, `aiohttp`, `ccxt.pro`). Blocking calls will cause order execution delays and potential missed signals.

### Resource Constraints

- **Memory**: Fargate task memory limit is 2 GB. The system MUST maintain a lean in-memory state (e.g., current candle data, open positions). Historical data is stored in PostgreSQL.
- **CPU**: Fargate task CPU limit is 0.5 vCPU. Computationally intensive operations (e.g., indicator calculations) MUST be optimized using vectorized `pandas` operations.
- **Storage**: Fargate tasks are ephemeral; all persistent data MUST be stored in PostgreSQL or S3. Local file storage is not reliable.
- **Network Bandwidth**: Estimated 10–50 MB per day for OHLCV data fetches and order updates. Fargate provides sufficient bandwidth for this scale.

### Budget & Cost Constraints

- **AWS Fargate**: Target monthly cost < $100 (0.5 vCPU, 2 GB memory, 24/7 operation).
- **PostgreSQL RDS**: Target monthly cost < $50 (db.t3.micro, 20 GB storage, automated backups).
- **Data Transfer**: Binance API calls and WebSocket connections are free; AWS data transfer costs are minimal at this scale.
- **Monitoring**: Prometheus and Grafana are self-hosted on Fargate; no additional SaaS costs.

---

## Assumptions

### External Factors

- **Binance API Availability**: The Binance API and WebSocket services are assumed to be available 99.9% of the time. Extended outages (> 1 hour) are treated as critical failures and trigger the failsafe mechanism.
- **User Account Setup**: The user possesses a valid Binance account with:
  - USD-M Futures trading enabled.
  - API keys generated with appropriate permissions (trading, reading account data).
  - Sufficient account balance to support the configured risk per trade (minimum 2% of equity).
- **Network Connectivity**: The hosting environment has a stable, low-latency connection to Binance servers (< 100 ms round-trip time). Intermittent connectivity issues are handled gracefully via exponential backoff.
- **SMC Strategy Viability**: The underlying SMC strategy (FVG + OB + HTF bias) is assumed to be profitable and viable. This specification implements the strategy as designed; strategy optimization and backtesting are out of scope.
- **Market Conditions**: The system is designed for 24/7 operation in crypto markets. Extreme volatility, flash crashes, or black swan events may result in unexpected slippage or order rejections, which are logged and alerted.

### System Assumptions

- **Database Persistence**: PostgreSQL is the single source of truth for all trade history, positions, and configuration. In-memory state is ephemeral and reconstructed from the database on restart.
- **Order Execution Model**: All orders are submitted to Binance and executed on Binance's matching engine. The bot does not maintain a local order book or matching logic.
- **Position Tracking**: Open positions are tracked via the Binance User Data Stream (primary) and reconciled via REST API polls (secondary). The bot does NOT maintain a local position ledger.
- **Time Synchronization**: The system assumes the Fargate host clock is synchronized with NTP (Network Time Protocol). Time drift > 1 second may cause order timestamp validation failures.
- **Telegram Bot Availability**: The Telegram Bot API is assumed to be available 99.9% of the time. Failed notifications do not block order execution; they are retried asynchronously.

---

## Error Codes & Handling

### Exchange API Errors

| Error Code | Source | Handling Strategy | User Alert |
|:---|:---|:---|:---|
| `RateLimitExceeded` | CCXT/Binance | Exponential backoff (1s, 2s, 4s, 8s); max 3 retries | None (automatic retry) |
| `NetworkError` | CCXT/Binance | Exponential backoff; max 5 retries over 30s | Telegram alert if > 3 consecutive failures |
| `InvalidOrder` | Binance | Log error; reject trade; alert admin | Telegram: "Trade rejected: [reason]" |
| `InsufficientBalance` | Binance | Reduce position size by 10%; retry once | Telegram: "Insufficient balance. Position size reduced." |
| `OrderNotFound` | Binance | Log error; trigger reconciliation | Telegram: "Order state mismatch detected. Reconciling..." |
| `AuthenticationError` | Binance | Pause trading; trigger failsafe (FR-13) | Telegram: "🚨 Authentication failed. Failsafe activated." |

### Database Errors

| Error Code | Handling Strategy | User Alert |
|:---|:---|:---|
| Connection timeout (> 5s) | Retry with exponential backoff; trigger failsafe if > 3 consecutive failures | Telegram: "Database connection lost. Failsafe activated." |
| Constraint violation (e.g., duplicate order ID) | Log error; skip operation; alert admin | Telegram: "Database constraint violation. Manual review required." |
| Transaction rollback | Retry transaction up to 3 times | None (automatic retry) |
| Query timeout (> 10s) | Cancel query; log error; alert admin | Telegram: "Database query timeout. Check system load." |

### Application Errors

| Error Code | Handling Strategy | User Alert |
|:---|:---|:---|
| Invalid signal (e.g., FVG not found) | Log error; skip symbol; continue scanning | None (logged only) |
| Position size validation failure (FR-10) | Reject trade; log reason; alert admin | Telegram: "Trade rejected: [reason]" |
| Order placement failure | Cancel all related orders; log error; alert admin | Telegram: "Order placement failed. All orders cancelled." |
| Unhandled exception in core service | Log full stack trace; trigger failsafe (FR-13) | Telegram: "🚨 Critical error. Failsafe activated." |

---

## Data Schemas & Entities

### Core Entities (Summary)

See DATABASE.md for complete schema definitions. Key entities include:

- **`watchlist`**: Active symbols being scanned. Columns: `id`, `symbol`, `added_at`, `is_active`.
- **`signals`**: Detected SMC signals. Columns: `id`, `symbol`, `signal_type` (BUY/SELL), `fvg_high`, `fvg_low`, `ob_high`, `ob_low`, `entry_price`, `sl_price`, `tp_price`, `created_at`.
- **`orders`**: Placed orders (entry, SL, TP). Columns: `id`, `order_id` (Binance), `symbol`, `side`, `order_type`, `quantity`, `price`, `status`, `created_at`, `filled_at`.
- **`positions`**: Open positions. Columns: `id`, `symbol`, `quantity`, `entry_price`, `current_price`, `unrealized_pnl`, `opened_at`, `closed_at`.
- **`trades`**: Closed trades (for history & analytics). Columns: `id`, `symbol`, `entry_price`, `exit_price`, `quantity`, `realized_pnl`, `entry_time`, `exit_time`, `duration`.

---

## API Endpoint Specifications

See API.md for complete endpoint definitions. Key endpoints include:

- `GET /v1/overview`: Account summary (equity, PnL, active trades).
- `POST /v1/watchlist`: Add/remove symbols from watchlist.
- `GET /v1/watchlist`: Retrieve current watchlist.
- `GET /v1/positions`: List open positions.
- `GET /v1/trades`: Historical trade list (paginated).
- `POST /v1/orders/close-all`: Emergency close all positions (admin only).

---

## Integration Points & Dependencies

### External Services

- **Binance USD-M Futures API**: REST API for account info, order placement, and historical data. WebSocket User Data Stream for real-time order/position updates.
- **AWS Secrets Manager**: Retrieves API keys, database credentials, and JWT secrets at startup.
- **AWS RDS PostgreSQL**: Persistent data storage for trades, positions, signals, and configuration.
- **Telegram Bot API**: Sends notifications and receives commands.

### Internal Service Dependencies

- **ExecutionEngine** → RiskCalculator, PositionManager, TradeRepository.
- **SMCScanner** → ExecutionEngine, SignalRepository.
- **PositionManager** → TradeRepository, PositionRepository.
- **FastAPI Routes** → All services (read-only for most endpoints; write for admin endpoints).
- **Telegram Bot Handlers** → PositionManager, ExecutionEngine (for `/close_all` command).

---

## Logging & Observability Requirements

### Log Levels & Categories

- **ERROR**: Critical failures (auth errors, database connection loss, unhandled exceptions). Triggers Telegram alert.
- **WARNING**: Recoverable errors (API rate limit, order rejection, signal validation failure). Logged but no alert unless repeated.
- **INFO**: Normal operations (signal detected, order placed, position closed, scanner cycle completed).
- **DEBUG**: Detailed diagnostic info (candle data, EMA calculations, FVG/OB detection logic). Disabled in production by default.

### Metrics to Collect (Prometheus)

- `trading_signals_total`: Counter of detected signals by symbol and type (BUY/SELL).
- `orders_placed_total`: Counter of placed orders by type (ENTRY, SL, TP).
- `orders_filled_total`: Counter of filled orders.
- `trades_closed_total`: Counter of closed trades.
- `realized_pnl_total`: Gauge of cumulative realized PnL.
- `unrealized_pnl_current`: Gauge of current unrealized PnL.
- `account_equity`: Gauge of current account equity.
- `scanner_cycle_duration_seconds`: Histogram of SMC Scanner cycle time.
- `order_placement_latency_ms`: Histogram of signal-to-order latency.
- `websocket_latency_ms`: Histogram of WebSocket update propagation time.
- `api_errors_total`: Counter of API errors by type (RateLimitExceeded, NetworkError, etc.).
- `failsafe_activations_total`: Counter of failsafe triggers.

---

## Testing & Validation Requirements

### Unit Testing

- **Services**: ExecutionEngine, RiskCalculator, SMCScanner logic (FVG/OB detection, EMA calculation, HTF bias).
- **Repositories**: CRUD operations for trades, positions, signals, watchlist.
- **Utilities**: Price rounding, position size calculation, constraint validation.
- **Target Coverage**: > 80% code coverage for core business logic.

### Integration Testing

- **Database**: Async transaction handling, connection pooling, constraint enforcement.
- **Exchange API**: Order placement, cancellation, position retrieval (using mock CCXT responses).
- **WebSocket**: Order update propagation, reconnection logic, state synchronization.
- **Telegram Bot**: Command parsing, notification delivery, error handling.

### End-to-End Testing

- **Signal-to-Execution Flow**: Detect signal → validate constraints → place orders → verify Binance state → update database.
- **Failsafe Trigger**: Simulate critical errors (auth failure, DB loss) → verify failsafe activation → verify Telegram alert.
- **Watchlist Dynamics**: Add/remove symbols → verify scanner picks up changes within 60 seconds.

### Shadow Trading Mode (Future)

- Paper trading environment that simulates order fills at realistic prices without executing real trades.
- Captures simulated fill prices and PnL to database for strategy validation.

---

## Deployment & Operational Requirements

### Pre-Deployment Checklist

- [ ] All unit tests pass (> 80% coverage).
- [ ] Integration tests pass against staging database.
- [ ] Code review completed by senior developer.
- [ ] Security audit completed (no hardcoded secrets, no SQL injection vulnerabilities).
- [ ] Performance testing completed (latency < 500 ms, throughput > 1,000 RPM).
- [ ] Failsafe mechanism tested and verified.
- [ ] Telegram bot notifications tested.
- [ ] Database backup and recovery procedure documented and tested.

### Operational Runbooks

- **Failsafe Activation**: Procedure to diagnose root cause, resolve issue, and reset failsafe.
- **Database Recovery**: Procedure to restore from backup if data corruption occurs.
- **API Key Rotation**: Procedure to rotate Binance API keys and update AWS Secrets Manager.
- **Emergency Shutdown**: Procedure to gracefully shut down all trading and workers.

---

## Acceptance Criteria Summary

All functional requirements (FR-01 through FR-13) MUST be implemented and verified against their acceptance criteria before production deployment. Non-functional requirements MUST be validated through performance testing and monitoring. Technical constraints MUST be enforced during code review and deployment.