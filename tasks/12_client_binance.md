# Task 12: Binance Client Implementation (Expanded & Domain Layer Structure)

## 1. Deskripsi Task
Membangun lapisan klien eksternal **Binance Futures API** (`BinanceClient`) menggunakan library `ccxt.async_support` dan `ccxt.pro`, terisolasi total dari database layer (*Clean Architecture*). Modul ini menangani eksekusi order (Entry, Multi-TP, Dynamic SL), manajemen leverage & margin mode, sinkronisasi metadata presisi instrumen, pembacaan saldo modal, serta pemetaan error bursa (*exchange exceptions*) ke dalam **Domain Custom Exceptions** di direktori `src/domain/exceptions/`.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/domain/exceptions/base.py`](../backend/src/domain/exceptions/base.py) *(Root Domain Exception)*
* `[NEW]` [`backend/src/domain/exceptions/exchange.py`](../backend/src/domain/exceptions/exchange.py) *(Exchange & Binance Specific Custom Exceptions)*
* `[NEW]` [`backend/src/domain/exceptions/__init__.py`](../backend/src/domain/exceptions/__init__.py) *(Central Exception Re-exports)*
* `[NEW]` [`backend/src/clients/binance_client.py`](../backend/src/clients/binance_client.py) *(REST & WebSocket Client)*
* `[NEW]` [`backend/src/clients/__init__.py`](../backend/src/clients/__init__.py)
* `[NEW]` [`backend/tests/clients/test_binance_client.py`](../backend/tests/clients/test_binance_client.py)

---

## 3. Rincian Arsitektur & Isi Komponen

### 1. Domain Exceptions (`src/domain/exceptions/`)
Membungkus error raw CCXT / HTTP response agar service bot murni berbicara dengan *Domain Language*:
* **`DomainError`** (Root base exception untuk semua domain error di aplikasi)
* **`ExchangeError`** (Base exception untuk operasi bursa)
* **`ExchangeNetworkError`** (Koneksi timeout, DNS failure, disconnection)
* **`ExchangeAuthError`** (API Key invalid, signature error, expired key)
* **`InsufficientMarginError`** / **`InsufficientBalanceError`** (Saldo margin tidak mencukupi untuk membuka lot)
* **`OrderRejectError`** (Order ditolak oleh bursa: minimum notional, price out of filter bounds)
* **`RateLimitError`** (Terkena IP ban / 429 Too Many Requests)

---

### 2. `BinanceRestClient` (`src/clients/binance_client.py`)
* Membungkus `ccxt.async_support.binance` dengan konfigurasi `defaultType: "future"`.
* **Method Khusus:**
  1. `async def initialize(self) -> None`:
     * Memuat daftar pasar (`load_markets()`) dan parameter presisi ticker.
  2. `async def fetch_instruments_metadata(self) -> List[Dict[str, Any]]`:
     * Mengambil seluruh simbol USDT-M futures aktif beserta `tick_size`, `step_size`, `min_qty`, `min_notional`, `price_precision`, dan `qty_precision` untuk sinkronisasi database.
  3. `async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]`:
     * Mengatur leverage akun pada pair tertentu (idempotent: menangani kondisi jika leverage sudah sama).
  4. `async def set_margin_mode(self, symbol: str, margin_mode: str = "ISOLATED") -> Dict[str, Any]`:
     * Mengatur margin mode (`ISOLATED` atau `CROSSED`) dengan penanganan aman pesan "No need to change margin type".
  5. `async def set_position_mode(self, dual_side_position: bool = False) -> Dict[str, Any]`:
     * Memastikan mode posisi adalah **One-Way Mode** (bukan Hedge Mode).
  6. `async def create_entry_order(self, symbol: str, side: str, order_type: str, qty: Decimal, price: Optional[Decimal] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]`:
     * Mengirim order entry (`MARKET` atau `LIMIT`).
  7. `async def create_stop_loss_order(self, symbol: str, side: str, stop_price: Decimal, qty: Optional[Decimal] = None, client_order_id: Optional[str] = None, close_position: bool = True) -> Dict[str, Any]`:
     * Mengirim order Stop Loss (`STOP_MARKET`) dengan opsi `closePosition=True`.
  8. `async def create_take_profit_order(self, symbol: str, side: str, tp_price: Decimal, qty: Decimal, client_order_id: Optional[str] = None) -> Dict[str, Any]`:
     * Mengirim order Take Profit (`LIMIT` atau `TAKE_PROFIT_MARKET`) dengan flag `reduceOnly=True`.
  9. `async def cancel_order(self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]`:
     * Membatalkan order tertentu di bursa.
  10. `async def cancel_all_orders(self, symbol: str) -> Dict[str, Any]`:
      * Membatalkan seluruh order terbuka pada simbol tertentu.
  11. `async def fetch_balance(self) -> Dict[str, Decimal]`:
      * Mengambil saldo akun futures: `total_wallet_balance`, `free_margin`, `used_margin`, `unrealized_pnl`.
  12. `async def fetch_ticker_price(self, symbol: str) -> Decimal`:
      * Mengambil harga realtime terkini dari ticker.
  13. `async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]`:
      * Mengambil posisi aktif saat ini di bursa (size, entry_price, pnl, liquidation_price).
  14. `async def close(self) -> None`:
      * Menutup sesi HTTP connector async CCXT.

---

### 3. `BinanceWebSocketClient` (`src/clients/binance_client.py`)
* Membungkus `ccxt.pro.binance` untuk realtime feed:
  1. `async def watch_orders_stream(self, callback_coro) -> None`:
     * Menjalankan infinite loop asinkron mendengarkan event fill order dari exchange (`ORDER_TRADE_UPDATE`).
  2. `async def watch_ticker_stream(self, symbols: List[str], callback_coro) -> None`:
     * Mendengarkan pergerakan harga realtime untuk trailing stop dan SL monitoring.
  3. `async def close(self) -> None`:
     * Menutup koneksi WebSocket gracefully.

---

## 4. Rincian Unit Test & Test Cases (`test_binance_client.py`)

### File Test: `backend/tests/clients/test_binance_client.py`

### Daftar Test Cases yang Diuji:
1. **`test_binance_client_init_and_sandbox_mode`**:
   * *Aksi:* Inisialisasi client dengan `testnet=True` vs `testnet=False`.
   * *Assert:* Sandbox mode aktif dan CCXT mengarah ke endpoint Binance Futures Testnet.
2. **`test_binance_fetch_instruments_metadata_parsing`**:
   * *Aksi:* Mock respon `load_markets()`, panggil `fetch_instruments_metadata()`.
   * *Assert:* Metadata ter-parse dengan tipe data `Decimal` presisi (`tick_size`, `step_size`, `min_notional`).
3. **`test_binance_set_leverage_and_margin_mode_idempotency`**:
   * *Aksi:* Panggil `set_leverage()` dan `set_margin_mode()`, simulasikan respons normal dan respons "No need to change".
   * *Assert:* Berhasil dieksekusi tanpa melempar exception.
4. **`test_binance_create_entry_and_protection_orders`**:
   * *Aksi:* Panggil `create_entry_order()`, `create_stop_loss_order()`, dan `create_take_profit_order()`.
   * *Assert:* Parameter diteruskan ke CCXT dengan format yang tepat (`reduceOnly`, `stopPrice`, `clientOrderId`).
5. **`test_binance_fetch_balance_and_positions`**:
   * *Aksi:* Mock respon `fetch_balance()` dan `fetch_positions()`.
   * *Assert:* Mengembalikan saldo modal dan posisi terbuka dengan tipe data `Decimal`.
6. **`test_binance_cancel_order_and_cancel_all`**:
   * *Aksi:* Mock pemanggilan `cancel_order()` dan `cancel_all_orders()`.
   * *Assert:* Permintaan pembatalan order terkirim dengan parameter simbol yang benar.
7. **`test_binance_domain_exceptions_mapping`**:
   * *Aksi:* Simulasikan CCXT `InsufficientFunds`, `AuthenticationError`, `RateLimitExceeded`, dan `NetworkError`.
   * *Assert:* Exception terbungkus rapi ke dalam domain exceptions di `src.domain.exceptions` (`InsufficientMarginError`, `ExchangeAuthError`, `RateLimitError`, `ExchangeNetworkError`).

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/clients/test_binance_client.py -v
```
