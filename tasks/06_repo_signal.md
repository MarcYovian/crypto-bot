# Task 06: Signal Repository Implementation

## 1. Deskripsi Task
Membangun `SignalRepository` khusus untuk model `TradingSignal` (`trading_signals` table) yang menangani persistensi sinyal masuk, deduplikasi Telegram message, approval confirmation lifecycle, dan transisi status sinyal.

---

## 2. File yang Dibuat / Diubah
* `[MODIFY]` [`backend/src/repository/signal_repository.py`](../backend/src/repository/signal_repository.py)
* `[NEW]` [`backend/tests/repository/test_signal_repository.py`](../backend/tests/repository/test_signal_repository.py)

---

## 3. Rincian Isi `signal_repository.py`

### Kelas `SignalRepository`
```python
class SignalRepository(BaseRepository[TradingSignal, TradingSignalCreate, TradingSignalUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(TradingSignal, session)
```

### Method Khusus:
1. `async def get_by_telegram_message_id(self, message_id: int) -> Optional[TradingSignal]`:
   * Menggunakan index `idx_signals_tg_msg_id` untuk lookup instan pesan duplikat dari Telegram.
2. `async def has_active_signal(self, instrument_id: int, side: str) -> bool`:
   * Menggunakan index `idx_signals_status_created` untuk mengecek apakah ada sinyal dengan status `RECEIVED` atau `EXECUTED` yang belum selesai pada pair dan side yang sama.
3. `async def get_pending_confirmation_signals(self) -> List[TradingSignal]`:
   * Mengambil sinyal berstatus `confirmation_status == 'PENDING'` yang membutuhkan persetujuan user via Inline Keyboard.
4. `async def update_confirmation_status(self, signal_id: int, confirmation_status: str) -> Optional[TradingSignal]`:
   * Mengupdate status menjadi `APPROVED` atau `REJECTED`.
5. `async def update_status(self, signal_id: int, status: str) -> Optional[TradingSignal]`:
   * Mengupdate lifecycle sinyal (`RECEIVED` ➔ `EXECUTED` / `CANCELLED` / `EXPIRED`).

---

## 4. Rincian Unit Test & Test Cases (`test_signal_repository.py`)

### File Test: `backend/tests/repository/test_signal_repository.py`

### Daftar Test Cases yang Diuji:
1. **`test_signal_create_and_deduplication_lookup`**:
   * *Aksi:* Buat sinyal dengan `telegram_message_id = 998811`, panggil `repo.get_by_telegram_message_id(998811)`.
   * *Assert:* Sinyal ditemukan dan atribut sesuai input.
2. **`test_signal_has_active_signal_check`**:
   * *Aksi:* Buat sinyal status `RECEIVED` untuk BTCUSDT BUY, panggil `repo.has_active_signal(instrument_id, "BUY")`.
   * *Assert:* Mengembalikan `True`.
3. **`test_signal_pending_confirmation_flow`**:
   * *Aksi:* Buat sinyal dengan `confirmation_status="PENDING"`, query `get_pending_confirmation_signals()`, lalu update ke `"APPROVED"`.
   * *Assert:* Status terupdate menjadi `APPROVED` dan tidak muncul lagi di daftar pending.
4. **`test_signal_lifecycle_transition`**:
   * *Aksi:* Update status sinyal dari `RECEIVED` ke `EXECUTED`.
   * *Assert:* Field `status == "EXECUTED"` dan `updated_at` terupdate.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_signal_repository.py -v
```
