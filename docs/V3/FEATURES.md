# FEATURES.md: SMC QuantEngine

## 1. Core Trading Logic: Smart Money Concepts (SMC)

The SMC QuantEngine implements a sophisticated, fully automated scalping strategy on the 15-minute (15m) timeframe, focusing on Binance USD-M Futures.

### 1.1 Higher Timeframe (HTF) Bias Validation
*   **Description**: Before considering any 15m trade signal, the system establishes a directional bias using the 4-hour (4H) timeframe.
*   **Logic**:
    *   Fetch 4H OHLCV data for the symbol.
    *   Calculate the 50-period Exponential Moving Average (EMA) on the 4H close price.
    *   **Bullish Bias**: A BUY signal on the 15m timeframe is only valid if the current 4H candle's close price is above the 4H EMA 50.
    *   **Bearish Bias**: A SELL signal on the 15m timeframe is only valid if the current 4H candle's close price is below the 4H EMA 50.
*   **User Story**: As a quant trader, I want the bot to only take trades aligned with the higher timeframe trend to increase my probability of success.

### 1.2 Fair Value Gap (FVG) & Order Block (OB) Identification
*   **Description**: The system identifies key SMC structures on the 15m timeframe to pinpoint high-probability entry zones.
*   **Logic**:
    *   **FVG**: Scan the last 3-4 closed 15m candles for a Fair Value Gap, defined as a three-candle pattern where the high of the first candle and the low of the third candle do not overlap, leaving a "gap" in between.
    *   **Order Block (OB)**: Once an FVG is identified, locate the last opposing candle (e.g., a bearish candle before a strong bullish impulse that created an FVG) immediately preceding the impulse move that created the FVG. This candle forms the Order Block.
    *   **Mitigation Check**: Ensure the current price has not yet retraced into the identified Order Block zone. Only "unmitigated" OBs are considered valid for trade entry.
*   **User Story**: As a quant trader, I want the bot to automatically detect SMC patterns like FVGs and Order Blocks to find precise entry points.

### 1.3 Trade Execution & Risk/Reward
*   **Description**: Upon a valid SMC signal, the system executes a trade with predefined risk management parameters.
*   **Logic**:
    *   **Entry Order**: A LIMIT order is placed at the proximal edge of the identified Order Block.
    *   **Stop Loss (SL)**: A STOP_MARKET order is placed slightly beyond the opposite edge of the Order Block, incorporating a small buffer for slippage.
    *   **Take Profit (TP)**: A TAKE_PROFIT_MARKET order is set to target a minimum 1:2 or 1:3 Risk/Reward (R:R) ratio, calculated from the entry price to the SL distance.
*   **User Story**: As a quant trader, I want my trades to be executed automatically with a predefined R:R ratio and precise entry/exit points based on SMC.

## 2. Robust Risk Management

The engine incorporates strict risk controls to protect capital and ensure sustainable trading.

### 2.1 Max Risk Per Trade
*   **Description**: Limits the maximum capital at risk for any single trade.
*   **Logic**: Each trade is sized such that the potential loss, if the Stop Loss is hit, does not exceed 2% of the total account equity.
*   **User Story**: As a quant trader, I want to ensure no single trade can jeopardize more than a small percentage of my total capital.

### 2.2 Dynamic Lot Sizing
*   **Description**: Automatically calculates the appropriate position size based on risk parameters and exchange constraints.
*   **Logic**:
    *   Calculates lot size using the 2% max risk, current account equity, and the distance between the proposed entry price and Stop Loss price.
    *   Validates the calculated lot size against Binance's symbol-specific trading rules, including `pricePrecision`, `minNotional`, `tickSize`, and `stepSize`.
    *   **Rejection**: If the calculated lot size or any derived price (SL/TP) violates Binance's constraints, the trade is rejected, and an alert is generated.
*   **User Story**: As a quant trader, I want the bot to automatically determine the correct position size for each trade, respecting both my risk limits and exchange requirements.

### 2.3 Slippage & Rate Limit Guard
*   **Description**: Ensures resilient interaction with the exchange API, mitigating issues from network latency or rate limits.
*   **Logic**:
    *   **API Errors**: Implements exponential backoff and retry mechanisms for `ccxt.NetworkError` and `ccxt.RateLimitExceeded` exceptions.
    *   **Market Orders**: For emergency market exits (e.g., `/close_all`), the system dynamically recalculates lot size based on real-time market price execution to ensure the order can be filled within acceptable parameters.
*   **User Story**: As a quant trader, I want the bot to handle temporary API issues gracefully and ensure my emergency market orders execute reliably.

## 3. System Interfaces

The SMC QuantEngine provides multiple interfaces for monitoring, control, and real-time updates.

### 3.1 Telegram Bot (`backend/src/bot/`)
*   **Description**: Provides real-time notifications and critical manual override capabilities.
*   **Features**:
    *   **Real-time Notifications**: Sends alerts for signal generation, order execution (entry, TP, SL), position closure, and critical system errors.
    *   **`/close_all` Command**: Immediately liquidates all open positions at market price.
    *   **`/status` Command**: Responds with a summary of current account equity, unrealized PnL, and a list of all open positions.
    *   **Failsafe Alerts**: Dispatches high-priority alerts for critical system failures (e.g., database connection loss, repeated authentication errors).
*   **User Story**: As a trader, I want to receive instant updates on my bot's activity and have an emergency button to close all trades via Telegram.

### 3.2 Web Dashboard API (`backend/src/api/`)
*   **Description**: A FastAPI-based API for real-time monitoring and dynamic watchlist management.
*   **Features**:
    *   **`/v1/overview`**: Provides a minimalist, high-level summary of the trading account (total equity, daily PnL, active trade count).
    *   **`/v1/watchlist`**: Endpoints to dynamically add or remove trading symbols from the scanner's active watchlist without system restart.
*   **User Story**: As a trader, I want a simple API to integrate with my custom dashboard for a quick overview of my trading performance and to manage my watchlist.

### 3.3 Background Workers (`backend/src/worker/`)
*   **Description**: Asynchronous workers responsible for continuous market scanning, data synchronization, and system health checks.
*   **Features**:
    *   **SMC Scanner**: Periodically iterates through the active watchlist, fetches 4H and 15m OHLCV data, applies HTF bias, and identifies FVG/OB setups.
    *   **Failsafe DB Sync**: A dedicated `ccxt.pro` WebSocket listener maintains a real-time connection to Binance User Data Stream, synchronizing order updates and position changes to the database for state consistency.
    *   **Master Failsafe**: Monitors system health; upon critical, unrecoverable errors, it pauses all scanning and trade execution, dispatching a high-priority Telegram alert.
*   **User Story**: As a system operator, I want the bot to continuously monitor markets, keep its internal state synchronized with the exchange, and alert me immediately of any critical issues.

## 4. Data Model (Core Entities)

See `DATABASE.md` for full schema details. The following are the primary entities:

| Table Name | Description | Key Fields |
|:-----------|:------------|:-----------|
| `symbols` | Active watchlist symbols | `symbol_id` (PK), `symbol_name`, `is_active` |
| `signals` | Generated trade signals | `signal_id` (PK), `symbol_id` (FK), `signal_type`, `entry_price`, `stop_loss`, `take_profit`, `status` |
| `trades` | Executed trades | `trade_id` (PK), `signal_id` (FK), `entry_time`, `exit_time`, `pnl`, `status` |
| `orders` | Individual exchange orders | `order_id` (PK), `trade_id` (FK), `exchange_order_id`, `order_type`, `price`, `quantity`, `status` |
| `account_snapshot` | Periodic account balance | `snapshot_id` (PK), `timestamp`, `equity`, `unrealized_pnl`, `balance` |

## 5. API Endpoints

See `API.md` for full API specification. The following are essential endpoints:

### 5.1 `GET /v1/overview`
*   **Description**: Provides a high-level summary of the trading account.
*   **Response Payload**:
    ```json
    {
      "total_equity": 12345.67,
      "daily_pnl_usd": 123.45,
      "daily_pnl_percent": 1.01,
      "active_trades_count": 2,
      "timestamp": "2023-10-27T10:30:00Z"
    }
    ```

### 5.2 `GET /v1/watchlist`
*   **Description**: Retrieves the list of symbols currently being scanned.
*   **Response Payload**:
    ```json
    [
      {"symbol": "BTCUSDT", "is_active": true},
      {"symbol": "ETHUSDT", "is_active": true},
      {"symbol": "SOLUSDT", "is_active": false}
    ]
    ```

### 5.3 `POST /v1/watchlist`
*   **Description**: Adds a new symbol to the active watchlist.
*   **Request Payload**:
    ```json
    {"symbol": "ADAUSDT"}
    ```
*   **Response Payload**:
    ```json
    {"message": "Symbol ADAUSDT added to watchlist."}
    ```

### 5.4 `DELETE /v1/watchlist/{symbol}`
*   **Description**: Removes a symbol from the active watchlist.
*   **Path Parameter**: `symbol` (e.g., `BTCUSDT`)
*   **Response Payload**:
    ```json
    {"message": "Symbol BTCUSDT removed from watchlist."}
    ```

### 5.5 `GET /v1/positions`
*   **Description**: Retrieves a list of all currently open positions.
*   **Response Payload**:
    ```json
    [
      {
        "symbol": "ETHUSDT",
        "side": "LONG",
        "entry_price": 1800.50,
        "current_price": 1810.20,
        "quantity": 0.1,
        "unrealized_pnl_usd": 0.97,
        "leverage": 20
      }
    ]
    ```

## 6. Future Roadmap (Advanced Features)

The following advanced features are planned for future development:

1.  **Dynamic Trailing Stop**: Implementation of an ATR-based trailing Stop Loss using `pandas-ta` to optimize trade exits.
2.  **Drawdown Limiter**: Dynamic risk scaling mechanism that reduces the percentage of capital risked per trade after a predefined number of consecutive losses.
3.  **Funding Rate Guard**: Logic to reject new trades if the funding fee for the symbol is extreme and the next settlement is less than 30 minutes away, to avoid high costs.
4.  **Technical Confluence Validator**: Integration of additional technical indicators (e.g., VWAP, RSI) as confluence factors, requiring their alignment before a trade signal is considered valid.
5.  **Shadow Trading Mode**: A paper trading environment that captures simulated fill prices and records all trade activities to the database, allowing for realistic strategy testing without real capital.