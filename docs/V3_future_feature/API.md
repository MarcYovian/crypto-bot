# API.md: SMC QuantEngine

## Authentication & Authorization

The SMC QuantEngine API uses JSON Web Tokens (JWT) for authentication and authorization. Access tokens must be included in the `Authorization` header of all protected requests.

*   **Authentication Method**: JWT (Bearer Token)
*   **Header Format**: `Authorization: Bearer <YOUR_JWT_TOKEN>`
*   **Authorization Levels**:
    *   `Admin`: Full read/write access, including critical operations like watchlist management and emergency trade overrides.
    *   `Trader`: Read-only access to overview and trade status.

## Standard Response & Pagination Formats

All API responses adhere to a consistent structure for clarity and ease of integration.

*   **Successful Responses**:
    *   `200 OK`, `201 Created`, `204 No Content`: Typically return a JSON object with a `data` field containing the requested resource or a `message` field for confirmation.
    *   Example: `{"message": "Operation successful.", "data": {"id": "abc", "status": "completed"}}`
*   **Error Responses**:
    *   `4xx Client Error`, `5xx Server Error`: Return a JSON object with a `detail` field describing the error.
    *   Example: `{"detail": "Symbol not found."}`
*   **Pagination**:
    *   For endpoints returning collections, pagination will be implemented using query parameters `?page=<int>&page_size=<int>`. The response will include `total_items`, `page`, `page_size`, `total_pages`, and `items` (the list of resources).
    *   Example: `{"total_items": 100, "page": 1, "page_size": 10, "total_pages": 10, "items": [...]}`

## API Endpoints

The following are the core API endpoints for interacting with the SMC QuantEngine.

### System Overview

#### GET /v1/overview

*   **Description**: Provides a high-level summary of the trading engine's status, including account equity, daily PnL, and active trade count. (FR-04)
*   **Auth Level**: `Trader`, `Admin`
*   **Request Body**: None
*   **Response Body (JSON)**:
    ```json
    {
      "total_equity_usd": 15000.75,
      "daily_pnl_usd": 125.30,
      "daily_pnl_percent": 0.84,
      "active_trades_count": 3,
      "last_updated_utc": "2023-10-27T10:30:00Z"
    }
    ```
*   **Status Codes**:
    *   `200 OK`: Successfully retrieved overview.
    *   `401 Unauthorized`: Missing or invalid authentication token.
    *   `403 Forbidden`: Insufficient permissions.

### Watchlist Management

#### GET /v1/watchlist

*   **Description**: Retrieves the list of symbols currently in the active trading watchlist. (FR-05)
*   **Auth Level**: `Trader`, `Admin`
*   **Request Body**: None
*   **Response Body (JSON)**:
    ```json
    {
      "watchlist": [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT"
      ],
      "last_updated_utc": "2023-10-27T10:35:00Z"
    }
    ```
*   **Status Codes**:
    *   `200 OK`: Successfully retrieved watchlist.
    *   `401 Unauthorized`: Missing or invalid authentication token.
    *   `403 Forbidden`: Insufficient permissions.

#### POST /v1/watchlist

*   **Description**: Adds a new symbol to the active trading watchlist. (FR-05)
*   **Auth Level**: `Admin`
*   **Request Body (JSON)**:
    ```json
    {
      "symbol": "ADAUSDT"
    }
    ```
*   **Response Body (JSON)**:
    ```json
    {
      "message": "Symbol ADAUSDT added to watchlist.",
      "watchlist": [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "ADAUSDT"
      ]
    }
    ```
*   **Status Codes**:
    *   `201 Created`: Symbol successfully added.
    *   `400 Bad Request`: Invalid symbol format or symbol already exists.
    *   `401 Unauthorized`: Missing or invalid authentication token.
    *   `403 Forbidden`: Insufficient permissions.

#### DELETE /v1/watchlist/{symbol}

*   **Description**: Removes a symbol from the active trading watchlist. (FR-05)
*   **Auth Level**: `Admin`
*   **Path Parameters**:
    *   `symbol` (string, required): The trading pair symbol to remove (e.g., `ADAUSDT`).
*   **Request Body**: None
*   **Response Body (JSON)**:
    ```json
    {
      "message": "Symbol ADAUSDT removed from watchlist.",
      "watchlist": [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT"
      ]
    }
    ```
*   **Status Codes**:
    *   `200 OK`: Symbol successfully removed.
    *   `400 Bad Request`: Invalid symbol format.
    *   `401 Unauthorized`: Missing or invalid authentication token.
    *   `403 Forbidden`: Insufficient permissions.
    *   `404 Not Found`: Symbol not found in the watchlist.

### Emergency Trade Operations

#### POST /v1/trades/close_all

*   **Description**: Initiates an emergency closure of all open positions at market price. This is a critical operation. (FR-02 equivalent for API)
*   **Auth Level**: `Admin`
*   **Request Body (JSON)**:
    ```json
    {
      "confirmation": true
    }
    ```
    *   *Note*: The `confirmation` field is required to prevent accidental execution.
*   **Response Body (JSON)**:
    ```json
    {
      "message": "Emergency close initiated for all open positions. Monitoring execution.",
      "closed_positions_count": 3,
      "timestamp_utc": "2023-10-27T10:40:00Z"
    }
    ```
*   **Status Codes**:
    *   `202 Accepted`: Request to close all positions has been accepted and is being processed.
    *   `400 Bad Request`: Missing or invalid `confirmation` field.
    *   `401 Unauthorized`: Missing or invalid authentication token.
    *   `403 Forbidden`: Insufficient permissions.
    *   `500 Internal Server Error`: An unexpected error occurred during the emergency close process.