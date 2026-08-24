# Task 13: Telegram Client Implementation (Expanded & Domain Layer Structure)

## 1. Deskripsi Task
Membangun lapisan klien **Telegram Communication** (`TelegramNotifierClient` untuk Bot API & Notifikasi Interaktif, dan `TelegramChannelListener` untuk penerimaan sinyal MTProto Telethon), dilengkapi dengan **Domain Custom Exceptions** di `src/domain/exceptions/telegram.py`, formatter template pesan notifikasi HTML (*Trade Alerts, Profit/Loss, Daily Summary*), serta dukungan tombol persetujuan interaktif (*Inline Keyboard Approval Flow*).

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/domain/exceptions/telegram.py`](../backend/src/domain/exceptions/telegram.py) *(Domain Exceptions untuk Telegram)*
* `[MODIFY]` [`backend/src/domain/exceptions/__init__.py`](../backend/src/domain/exceptions/__init__.py) *(Re-export Exceptions)*
* `[NEW]` [`backend/src/clients/telegram_client.py`](../backend/src/clients/telegram_client.py) *(Telegram Bot & Notifier Client)*
* `[MODIFY]` [`backend/src/clients/__init__.py`](../backend/src/clients/__init__.py) *(Central Export Clients)*
* `[NEW]` [`backend/tests/clients/test_telegram_client.py`](../backend/tests/clients/test_telegram_client.py)

---

## 3. Rincian Arsitektur & Isi Komponen

### 1. Domain Exceptions (`src/domain/exceptions/telegram.py`)
Membungkus error HTTP Bot API / Telethon ke dalam bahasa domain:
* **`TelegramError`** (Base Exception untuk komunikasi Telegram)
* **`TelegramAuthError`** (Token bot invalid / unauthorized)
* **`TelegramRateLimitError`** (Flood control / 429 Too Many Requests)
* **`TelegramNetworkError`** (Koneksi timeout / DNS resolution failed)
* **`TelegramSendError`** (Chat tidak ditemukan / user memblokir bot)
* **`TelegramMessageParseError`** (Format parse mode HTML / Markdown error)

---

### 2. `TelegramNotifierClient` (`src/clients/telegram_client.py`)
* Menggunakan klien HTTP asinkron (`httpx.AsyncClient`) untuk memanggil Telegram Bot API resmi secara efisien dan andal.
* **Method Utama & Formatter Notifikasi:**
  1. `async def send_message(self, chat_id: Union[str, int], text: str, parse_mode: str = "HTML", reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`:
     * Mengirim pesan teks umum dengan retry dan penanganan error.
  2. `async def send_signal_confirmation(self, chat_id: Union[str, int], signal_id: int, symbol: str, side: str, entry_range: str, sl: Decimal, tp_targets: List[Decimal], confidence: Optional[Decimal] = None) -> Dict[str, Any]`:
     * Mengirim template alert sinyal baru dilengkapi **Inline Keyboard Buttons**:
       * `[ ✅ Approve ]` (callback data: `sig_app_{signal_id}`)
       * `[ ❌ Reject ]` (callback data: `sig_rej_{signal_id}`)
  3. `async def send_trade_opened_alert(self, chat_id: Union[str, int], symbol: str, side: str, entry_price: Decimal, leverage: int, position_size: Decimal, margin: Decimal, sl_price: Decimal, tp_targets: List[Decimal]) -> Dict[str, Any]`:
     * Mengirim pesan notifikasi bahwa posisi telah resmi terbuka di Binance.
  4. `async def send_take_profit_alert(self, chat_id: Union[str, int], symbol: str, side: str, tp_level: int, exit_price: Decimal, closed_qty: Decimal, realized_pnl: Decimal, remaining_qty: Decimal) -> Dict[str, Any]`:
     * Notifikasi TP tersentuh (misal: "🎯 TP1 Hit! Realized PnL: +$45.00 | SL moved to Break-Even").
  5. `async def send_stop_loss_alert(self, chat_id: Union[str, int], symbol: str, side: str, exit_price: Decimal, closed_qty: Decimal, realized_pnl: Decimal) -> Dict[str, Any]`:
     * Notifikasi posisi menyentuh Stop Loss atau Stop Market.
  6. `async def send_daily_summary_alert(self, chat_id: Union[str, int], date_str: str, starting_balance: Decimal, ending_balance: Decimal, net_pnl: Decimal, total_trades: int, win_rate: float) -> Dict[str, Any]`:
     * Laporan ringkasan rekapitulasi harian 00:00 WIB.
  7. `async def edit_message_text(self, chat_id: Union[str, int], message_id: int, text: str, parse_mode: str = "HTML", reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`:
     * Mengupdate teks pesan setelah tombol Approve/Reject ditekan oleh user.
  8. `async def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> bool`:
     * Memberi feedback popup toast saat user mengklik inline keyboard.
  9. `async def close(self) -> None`:
     * Menutup koneksi HTTP client session.

---

### 3. `TelegramChannelListener` (`src/clients/telegram_client.py`)
* Wrapper asinkron untuk mendengarkan pesan dari VIP signal channels (menggunakan Telethon / MTProto client).
* **Method:**
  * `async def start(self, channel_ids: List[Union[str, int]], on_message_coro) -> None`:
    * Mendaftarkan event listener pada channel ID terkait.
  * `async def stop(self) -> None`:
    * Graceful disconnect listener session.

---

## 4. Rincian Unit Test & Test Cases (`test_telegram_client.py`)

### File Test: `backend/tests/clients/test_telegram_client.py`

### Daftar Test Cases yang Diuji:
1. **`test_telegram_send_formatted_message_html`**:
   * *Aksi:* Kirim pesan HTML, verifikasi payload HTTP POST yang dikirim ke endpoint `sendMessage`.
   * *Assert:* Parameter `chat_id`, `text`, dan `parse_mode="HTML"` sesuai format.
2. **`test_telegram_send_signal_confirmation_with_inline_keyboard`**:
   * *Aksi:* Panggil `send_signal_confirmation()` untuk sinyal ID `101`.
   * *Assert:* Payload memuat struktur `inline_keyboard` dengan callback data `sig_app_101` dan `sig_rej_101`.
3. **`test_telegram_edit_message_after_user_approval`**:
   * *Aksi:* Panggil `edit_message_text()` untuk pesan ID `8812`.
   * *Assert:* Permintaan dikirim ke endpoint `editMessageText` dengan teks terupdate.
4. **`test_telegram_trade_alert_formatters`**:
   * *Aksi:* Panggil `send_trade_opened_alert()`, `send_take_profit_alert()`, dan `send_daily_summary_alert()`.
   * *Assert:* Pesan terformat rapi dengan emoji, nilai harga, dan persentase yang valid.
5. **`test_telegram_answer_callback_query`**:
   * *Aksi:* Panggil `answer_callback_query("cb_query_123", text="Sinyal Disetujui")`.
   * *Assert:* Permintaan POST ke `answerCallbackQuery` terkirim dengan benar.
6. **`test_telegram_domain_exceptions_mapping`**:
   * *Aksi:* Simulasikan respons HTTP 401 (Invalid Token), 429 (Flood Control), 400 (Chat Not Found), dan Network Timeout.
   * *Assert:* Error terbungkus rapi ke `TelegramAuthError`, `TelegramRateLimitError`, `TelegramSendError`, dan `TelegramNetworkError`.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/clients/test_telegram_client.py -v
```
