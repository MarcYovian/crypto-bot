# TESTING.md: SMC QuantEngine

## 1. Overall Test Strategy

The testing strategy for SMC QuantEngine is built upon a "Shift-Left" approach, emphasizing early and continuous testing throughout the development lifecycle. Given the critical nature of an algorithmic trading platform, reliability, accuracy, and resilience are paramount. Our strategy combines automated testing at multiple layers with manual verification for complex scenarios, ensuring the system behaves as expected under various market conditions and edge cases.

Key principles:
*   **Test-Driven Development (TDD) / Behavior-Driven Development (BDD)**: Encourage writing tests before or alongside code to define expected behavior and drive implementation.
*   **Layered Testing**: Implement a comprehensive suite of unit, integration, and end-to-end tests to cover all components and their interactions.
*   **Asynchronous Focus**: All tests involving asynchronous components will leverage `pytest-asyncio` to ensure proper handling of `async/await` patterns.
*   **Mocking External Dependencies**: Isolate core logic from external services (Binance API, Telegram API) using mocks to ensure fast, reliable, and deterministic tests.
*   **Real-World Simulation**: Utilize a "Shadow Trading Mode" (once implemented) for realistic, non-production testing of new features and strategy adjustments.

## 2. Test Types

### 2.1. Unit Tests

Unit tests focus on individual functions, methods, or small classes in isolation. They verify the correctness of the smallest testable parts of the application.

*   **Scope**: `services` (e.g., `ExecutionEngine`, `SMCScanner`, `PositionManager`, `RiskCalculator`), `repository` methods, utility functions, data models.
*   **Purpose**: Validate business logic, calculations, data transformations, and error handling within a single component.
*   **Isolation**: External dependencies (database, external APIs, other services) are typically mocked.

### 2.2. Integration Tests

Integration tests verify the interactions between different components or layers of the application. They ensure that modules work correctly when combined.

*   **Scope**:
    *   `api` endpoints interacting with `services`.
    *   `bot` handlers interacting with `services`.
    *   `worker` components interacting with `services` and `repository`.
    *   `services` interacting with `repository` (testing actual database calls).
    *   `repository` methods interacting with the PostgreSQL database.
*   **Purpose**: Confirm data flow, contract adherence between layers, and correct behavior of combined units.
*   **Dependencies**: May use a dedicated test database (e.g., `pytest-postgresql` for a temporary instance) and mock external APIs (`ccxt.pro`, Telegram).

### 2.3. End-to-End (E2E) Tests

E2E tests simulate real user scenarios, covering the entire application flow from input to output. They validate the system's behavior from a user's perspective.

*   **Scope**:
    *   Full trading lifecycle: Watchlist update -> SMC scan -> Signal generation -> Order placement -> Order fill simulation -> Position management -> Notification.
    *   Telegram command execution: `/status`, `/close_all` and subsequent system actions.
    *   FastAPI dashboard interaction: `/v1/overview`, `/v1/watchlist` updates and data retrieval.
*   **Purpose**: Verify the complete system functionality, including external integrations (mocked or sandboxed).
*   **Dependencies**: Requires a fully running (but potentially mocked external services) environment.

### 2.4. Performance Tests

Performance tests evaluate the system's responsiveness, stability, and scalability under various loads.

*   **Scope**: Critical paths such as signal detection to order placement latency, WebSocket update propagation, and API endpoint response times.
*   **Purpose**: Ensure compliance with Non-Functional Requirements (NFRs) like `< 500 ms` signal-to-execution latency and `< 100 ms` WebSocket update propagation.
*   **Tools**: `locust`, custom `asyncio` benchmarks.

### 2.5. Resilience and Chaos Tests

These tests evaluate how the system behaves under adverse conditions, such as network failures, API errors, or database outages.

*   **Scope**: `ccxt.pro` error handling (`NetworkError`, `RateLimitExceeded`), database connection loss, critical service failures.
*   **Purpose**: Verify the effectiveness of exponential backoff, retry mechanisms, and the master failsafe mechanism (FR-13).
*   **Methodology**: Introduce controlled failures into mocked external services or network layers.

### 2.6. Security Tests

See [SECURITY.md]. This document would detail penetration testing, vulnerability scanning, and access control verification.

## 3. Test Cases by Feature Area

### 3.1. SMC Scanner & Strategy Logic (`backend/src/services/smc_scanner.py`)

#### 3.1.1. Unit Tests
*   **HTF Bias Calculation**:
    *   Given 4H OHLCV data, verify correct EMA 50 calculation.
    *   Test `is_bullish_bias` and `is_bearish_bias` methods return `True`/`False` based on 4H close vs. EMA 50.
*   **FVG Identification**:
    *   Provide various 15m candle patterns (e.g., strong impulse, consolidation) and verify correct FVG detection (last 3-4 candles).
    *   Test cases for no FVG present.
*   **Order Block (OB) Identification**:
    *   Given an FVG, verify the correct identification of the last opposing candle before the impulse as the OB.
    *   Test cases for ambiguous OB scenarios.
*   **Mitigation Check**:
    *   Given an identified OB, verify `is_unmitigated` returns `True` if current price has not entered the OB zone.
    *   Test cases where price has partially or fully mitigated the OB.
*   **Risk/Reward Ratio Calculation**:
    *   Given entry, SL, and TP prices, verify correct R:R calculation (e.g., 1:2, 1:3).

#### 3.1.2. Integration Tests
*   **SMC Scan Workflow**:
    *   Mock `ccxt.pro` to return specific OHLCV data for 4H and 15m.
    *   Verify `SMCScanner.scan_symbol` correctly identifies a trade setup (HTF bias, FVG, OB, unmitigated) and generates a signal.
    *   Test scenarios where one or more SMC conditions are not met, ensuring no signal is generated.

### 3.2. Risk Management (`backend/src/services/risk_calculator.py`)

#### 3.2.1. Unit Tests
*   **Lot Size Calculation**:
    *   Given total equity, max risk (2%), entry price, and SL price, verify correct lot size calculation.
    *   Test with varying distances between entry and SL.
    *   Test edge cases: very small SL (large lot size), very large SL (small lot size).
*   **Binance Constraint Validation**:
    *   Mock Binance `fetch_symbol_info` to return specific `minNotional`, `tickSize`, `stepSize`.
    *   Test `validate_position_size` ensures calculated lot size adheres to these constraints.
    *   Verify trade rejection if `minNotional` is not met.
    *   Verify lot size adjustment to `stepSize` and price adjustment to `tickSize`.
*   **Max Risk Enforcement**:
    *   Test that `calculate_lot_size` never exceeds the configured max risk percentage (2% of equity).

### 3.3. Execution Engine (`backend/src/services/execution_engine.py`)

#### 3.3.1. Integration Tests
*   **Order Placement (Mocked `ccxt.pro`)**:
    *   Mock `ccxt.pro.create_order` to simulate successful order placement.
    *   Verify `ExecutionEngine.place_trade` correctly constructs and sends LIMIT entry, STOP_MARKET, and TAKE_PROFIT_MARKET orders.
    *   Test error handling for `ccxt.pro` exceptions (e.g., `InsufficientFunds`, `InvalidOrder`).
*   **Binance Constraint Handling**:
    *   Test `place_trade` calls `RiskCalculator.validate_position_size` and rejects trade if validation fails (FR-10).
*   **Emergency Close (`/close_all`)**:
    *   Mock `ccxt.pro.create_market_sell_order` for all open positions.
    *   Verify `ExecutionEngine.close_all_positions` correctly iterates and liquidates all positions.

### 3.4. Data Access Layer (`backend/src/repository/`, `backend/src/database/`)

#### 3.4.1. Integration Tests (using a temporary PostgreSQL instance)
*   **CRUD Operations**:
    *   Test `TradeRepository`: `create_trade`, `get_trade_by_id`, `update_trade_status`, `get_open_positions`.
    *   Test `SignalRepository`: `create_signal`, `get_pending_signals`.
    *   Test `WatchlistRepository`: `add_symbol`, `remove_symbol`, `get_active_symbols`.
*   **Concurrency**:
    *   Simulate concurrent writes/reads to the database to ensure data integrity and handle race conditions (e.g., multiple workers trying to update the same trade).
*   **Error Handling**:
    *   Test database connection failures and `asyncpg` exceptions.

### 3.5. Telegram Bot (`backend/src/bot/`)

#### 3.5.1. Integration Tests (Mocked Telegram API)
*   **`/status` Command**:
    *   Mock `telegram.Bot.send_message`.
    *   Simulate `/status` command and verify the bot calls `PositionManager.get_account_summary` and sends a correctly formatted message (FR-03).
*   **`/close_all` Command**:
    *   Mock `telegram.Bot.send_message` and `ExecutionEngine.close_all_positions`.
    *   Simulate `/close_all` command and verify the bot triggers the emergency close and sends confirmation (FR-02).
*   **Notifications (FR-01)**:
    *   Mock `telegram.Bot.send_message`.
    *   Trigger various events (signal generated, order filled, SL hit, TP hit) and verify correct notification content and timing.
    *   Test retry logic for failed notifications.

### 3.6. Web Dashboard API (`backend/src/api/`)

#### 3.6.1. Integration Tests (using `httpx` client)
*   **`/v1/overview` Endpoint**:
    *   Make a GET request to `/v1/overview`.
    *   Mock `PositionManager.get_account_summary`.
    *   Verify the response structure and data match the expected minimalist overview (FR-04).
*   **`/v1/watchlist` Endpoints**:
    *   **POST**: Send a request to add a symbol. Verify `201 Created` and database update. Test invalid symbol input (`400 Bad Request`).
    *   **DELETE**: Send a request to remove a symbol. Verify `204 No Content` and database update. Test non-existent symbol (`404 Not Found`).
    *   **GET**: Retrieve the active watchlist. Verify correct list of symbols.
*   **Error Handling**:
    *   Test API endpoints for various error conditions (e.g., internal server errors, validation errors) and verify appropriate HTTP status codes and error messages.

### 3.7. Background Workers (`backend/src/worker/`)

#### 3.7.1. Integration Tests
*   **SMC Scanner Worker**:
    *   Simulate the `APScheduler` trigger for the SMC Scanner.
    *   Verify it iterates through the active watchlist, calls `SMCScanner.scan_symbol`, and processes signals.
*   **Failsafe DB Sync Worker**:
    *   Simulate the `APScheduler` trigger for the Failsafe DB Sync.
    *   Mock `ccxt.pro` to return current open orders/positions.
    *   Verify the worker reconciles the database state with the exchange state (FR-12).
*   **Critical Failsafe (FR-13)**:
    *   Introduce mocked critical errors (e.g., repeated `ccxt.pro` authentication failures, database connection loss).
    *   Verify the worker pauses scanning/execution and dispatches a high-priority alert via Telegram.

## 4. Test Coverage Targets

Achieving high test coverage is crucial for a reliable trading system.

| Test Type | Target Coverage |
|:----------|:----------------|
| Unit Tests | > 90% of core business logic (`services`, `repository`, `utils`) |
| Integration Tests | > 80% of API endpoints, bot commands, and inter-service communication paths |
| End-to-End Tests | > 90% of critical user flows (e.g., trade lifecycle, emergency close) |
| Performance Tests | All critical paths identified in NFRs |
| Resilience Tests | All identified failure scenarios for external dependencies |

## 5. Testing Tools and Frameworks

*   **Python Test Runner**: `pytest`
    *   **Asynchronous Testing**: `pytest-asyncio` for running `async` test functions.
    *   **Mocking**: `pytest-mock` (wrapper around `unittest.mock`) for patching external dependencies (e.g., `ccxt.pro`, `telegram.Bot`, database connections).
    *   **Parameterization**: `pytest.mark.parametrize` for testing multiple inputs/scenarios efficiently.
*   **HTTP Client for API Testing**: `httpx` for making asynchronous requests to the FastAPI application during integration and E2E tests.
*   **Database Testing**: `pytest-postgresql` or similar fixtures for spinning up temporary, isolated PostgreSQL databases for integration tests, ensuring clean state for each test run.
*   **Code Coverage**: `coverage.py` integrated with `pytest` to measure test coverage.
*   **Linting & Formatting**: `flake8`, `black`, `isort` to ensure code quality and consistency.
*   **Type Checking**: `mypy` for static type analysis, catching potential errors before runtime.

## 6. CI/CD Integration

Testing is an integral part of the Continuous Integration/Continuous Deployment (CI/CD) pipeline, ensuring that every code change is thoroughly validated before deployment.

1.  **Pre-Commit Hooks**:
    *   `pre-commit` framework configured to run `black`, `isort`, `flake8`, and `mypy` before commits, enforcing code quality standards.
2.  **Automated Build & Test (GitHub Actions / GitLab CI)**:
    *   **Trigger**: Every push to a feature branch and pull request.
    *   **Steps**:
        *   Install dependencies.
        *   Run `flake8`, `black`, `isort`, `mypy`.
        *   Execute all Unit Tests.
        *   Execute all Integration Tests (against a temporary test database).
        *   Generate code coverage reports.
    *   **Outcome**: Build status (pass/fail) and coverage report are reported back to the PR, blocking merges if tests fail or coverage drops below thresholds.
3.  **Scheduled E2E Tests**:
    *   Run E2E tests periodically (e.g., nightly) against a staging environment that closely mirrors production, using mocked external services.
    *   Alert on failures to catch regressions in complex flows.
4.  **Shadow Trading Mode (Future)**:
    *   New features or significant strategy changes will first be deployed to a "Shadow Trading Mode" environment.
    *   This environment will process real-time market data and simulate trade execution, capturing simulated fill prices and PnL to the database without actual capital at risk.
    *   Performance metrics and simulated PnL will be monitored via Grafana dashboards to validate changes before live deployment.