# USERFLOW.md: SMC QuantEngine

## 1. Watchlist Management

This flow describes how an authorized user dynamically manages the list of symbols the SMC Scanner actively monitors for trading opportunities. This is critical for adapting to market conditions and optimizing resource usage.

| No | Actor | Action/Step | System Response | Alternative/Alternative Path/Error Path |
|:---|:---|:---|:---|:---|
| 1 | Admin | Sends `POST /v1/watchlist` request with `{"symbol": "BTCUSDT", "active": true}` to add/activate a symbol. | System validates symbol, updates `watchlist` table in DB, and returns `201 Created` with the new watchlist entry. | **Error**: Invalid symbol format or non-existent symbol on Binance. System returns `400 Bad Request` with error message. |
| 2 | Admin | Sends `DELETE /v1/watchlist/{symbol}` request (e.g., `DELETE /v1/watchlist/BTCUSDT`) to remove/deactivate a symbol. | System validates symbol, marks `active=false` in `watchlist` table (soft delete), and returns `204 No Content`. | **Error**: Symbol not found in watchlist. System returns `404 Not Found`. |
| 3 | SMC Scanner Worker | Periodically queries the `watchlist` table for active symbols. | Worker updates its internal list of symbols to scan. | N/A |

**Trigger**: Admin initiates a request via the FastAPI endpoint.
**Pre-conditions**: Admin is authenticated and authorized. The symbol exists on Binance (for adding).
**Post-conditions**: The `watchlist` database table is updated, and the SMC Scanner worker adjusts its monitoring scope accordingly.

## 2. SMC Signal Generation and Trade Execution

This is the core automated trading loop, from identifying a potential trade setup to placing and managing orders on the exchange.

| No | Actor | Action/Step | System Response | Alternative/Alternative Path/Error Path |
|:---|:---|:---|:---|:---|
| 1 | SMC Scanner Worker | Fetches 4H and 15m OHLCV data for an active symbol from Binance via `ccxt.pro`. | Data is processed and stored temporarily in memory. | **Error**: `NetworkError` or `RateLimitExceeded` from Binance. Worker applies exponential backoff and retries. If persistent, logs critical error and alerts via Telegram. |
| 2 | SMC Scanner Worker | Applies Higher Timeframe (HTF) bias check (4H Close vs. EMA 50). | If HTF bias is not met (e.g., 15m BUY signal but 4H is bearish), the signal is discarded. | N/A |
| 3 | SMC Scanner Worker | Identifies Fair Value Gap (FVG) and Order Block (OB) on the 15m timeframe. | If FVG and OB are found and unmitigated, a potential trade signal is generated. | **Alternative**: No FVG/OB found or already mitigated. Worker continues to next symbol/candle. |
| 4 | SMC Scanner Worker | Passes potential signal to `ExecutionEngine` for risk calculation and order preparation. | `ExecutionEngine` calculates position size based on 2% max risk, entry, and SL. Validates against Binance symbol limits (`minNotional`, `tickSize`, `stepSize`). | **Error**: Position size calculation fails (e.g., risk too high for available equity, invalid SL). Trade is rejected, logged, and Telegram alert sent. |
| 5 | ExecutionEngine | Places a LIMIT entry order, a STOP_MARKET order (SL), and a TAKE_PROFIT_MARKET order (TP) on Binance via `ccxt.pro`. | Binance confirms order placement. Order details (ID, status, etc.) are stored in the `orders` and `trades` tables in the database. Telegram notification sent (FR-01). | **Error**: Binance API rejects order (e.g., insufficient balance, invalid parameters). Order is cancelled, logged, and Telegram alert sent. `NetworkError` or `RateLimitExceeded` handled with retry/backoff. |
| 6 | Binance WebSocket Listener Worker | Receives real-time updates for the placed orders (e.g., `NEW`, `FILLED`, `CANCELED`). | Worker updates the `orders` and `trades` tables in the database to reflect the latest status. | **Error**: WebSocket connection drops. Worker attempts to reconnect with exponential backoff. If persistent, triggers master failsafe (FR-13). |
| 7 | Binance WebSocket Listener Worker | Receives updates for position changes (e.g., entry filled, SL/TP hit, position closed). | Worker updates the `positions` table in the database. Telegram notification sent for entry, SL, or TP events (FR-01). | N/A |

**Trigger**: The `SMC Scanner Worker`'s periodic execution cycle.
**Pre-conditions**: An active symbol exists in the watchlist. Binance API connection is stable. Account has sufficient equity.
**Post-conditions**: A trade signal is either discarded, or a set of linked orders (Entry, SL, TP) is placed on Binance, and the database reflects the current state of orders and positions. Telegram notifications are sent for key events.

## 3. Monitoring and Emergency Override

This flow details how an Admin or Trader can monitor the system's status and execute an emergency override to close all open positions.

| No | Actor | Action/Step | System Response | Alternative/Alternative Path/Error Path |
|:---|:---|:---|:---|:---|
| 1 | Admin/Trader | Sends `/status` command to the Telegram bot. | Telegram bot queries `PositionManager` and `RiskCalculator` services. Returns a summary of current account equity, unrealized PnL, and a list of open positions via Telegram (FR-03). | **Error**: Database connection issue. Bot returns an error message and logs the issue. |
| 2 | Admin/Trader | Accesses `GET /v1/overview` endpoint via a web dashboard. | FastAPI endpoint queries `PositionManager` and `RiskCalculator` services. Returns a minimalist JSON summary including total equity, daily PnL, and active trade count (FR-04). | **Error**: Service dependency (e.g., DB) unavailable. API returns `500 Internal Server Error`. |
| 3 | Admin | Sends `/close_all` command to the Telegram bot. | Telegram bot validates Admin role. `ExecutionEngine` is instructed to retrieve all open positions from the database. | **Error**: User is not an Admin. Bot responds with "Unauthorized" message. |
| 4 | ExecutionEngine | For each open position, places a MARKET order on Binance to close the position. | Binance confirms order placement. `ExecutionEngine` updates `orders` and `positions` tables in DB. Telegram notification sent for each closed position. | **Error**: Binance API error during market order placement. `ExecutionEngine` logs error, retries with backoff, and alerts Admin if persistent. |
| 5 | Binance WebSocket Listener Worker | Receives real-time updates for the closing market orders. | Worker updates the `orders` and `positions` tables in the database to reflect the closed positions. | N/A |

**Trigger**: Admin/Trader explicitly requests status or initiates an emergency override.
**Pre-conditions**: Telegram bot is running and connected. Admin/Trader is authenticated.
**Post-conditions**: System status is provided, or all open positions are closed on Binance, and the database is updated accordingly.

## 4. System Failsafe Activation

This flow describes the system's response to critical, unrecoverable errors to prevent further erroneous trading.

| No | Actor | Action/Step | System Response | Alternative/Alternative Path/Error Path |
|:---|:---|:---|:---|:---|
| 1 | Any System Component (e.g., `ccxt.pro` adapter, `repository` layer) | Detects a critical, unrecoverable error (e.g., repeated Binance authentication failure, persistent database connection loss, repeated `NetworkError` after retries). | The component triggers the `FailsafeManager` service. | **Alternative**: Transient error (e.g., single `RateLimitExceeded`). Component handles with retry/backoff without triggering failsafe. |
| 2 | FailsafeManager | Receives critical error signal. | `FailsafeManager` sets a global system flag to `PAUSED_CRITICAL`. It instructs `SMC Scanner Worker` and `ExecutionEngine` to cease all new trade activities and order placements. | N/A |
| 3 | FailsafeManager | Dispatches a high-priority alert via Telegram to all configured Admin users. | Telegram message includes error details, timestamp, and instructions for manual intervention. | **Error**: Telegram API failure. FailsafeManager logs the failure and continues with other failsafe actions. |
| 4 | FailsafeManager | Logs the critical event with maximum severity. | Event is recorded in system logs (e.g., sent to Loki). | N/A |
| 5 | Admin | Receives Telegram alert. | Admin investigates the root cause and takes corrective action (e.g., updating API keys, restoring DB connection). | N/A |
| 6 | Admin | Manually restarts or resets the system after resolving the issue. | System re-initializes, clears the `PAUSED_CRITICAL` flag, and resumes normal operations. | N/A |

**Trigger**: Detection of a persistent, critical system error by any core component.
**Pre-conditions**: Failsafe mechanism is active and configured.
**Post-conditions**: All automated trading activities are paused, a high-priority alert is sent to Admin, and the critical event is logged. The system awaits manual intervention to resume.