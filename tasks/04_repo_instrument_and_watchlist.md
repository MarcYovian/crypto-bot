# Task 04: Instrument & Watchlist Repositories Implementation

## 1. Deskripsi Task
Membangun repository terpisah untuk model Pasangan Perdagangan (`Instrument`) dan Daftar Pantau Bot (`Watchlist`) untuk aturan presisi trading dan filter pair aktif.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/instrument_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/instrument_repository.py)
* `[NEW]` [`backend/src/repository/watchlist_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/watchlist_repository.py)
* `[NEW]` [`backend/tests/repository/test_instrument_watchlist_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/tests/repository/test_instrument_watchlist_repository.py)

---

## 3. Rincian Isi Repositories

### 1. `instrument_repository.py` (`InstrumentRepository`)
* Mewarisi `BaseRepository[Instrument, InstrumentCreate, InstrumentUpdate]`.
* **Method Khusus:**
  * `async def get_by_symbol(self, symbol: str, exchange_id: Optional[int] = None) -> Optional[Instrument]`:
    * Mengambil detail presisi instrumen (tick_size, step_size, min_qty, precision).
    * Normalisasi simbol (`symbol.upper()`).
  * `async def get_all_active(self, exchange_id: Optional[int] = None) -> List[Instrument]`.
  * `async def bulk_upsert_instruments(self, instruments: List[InstrumentCreate]) -> int`: Memperbarui metadata instrumen dari sync exchange info.

### 2. `watchlist_repository.py` (`WatchlistRepository`)
* Mewarisi `BaseRepository[Watchlist, WatchlistCreate, WatchlistUpdate]`.
* **Method Khusus:**
  * `async def is_symbol_enabled(self, symbol: str) -> bool`: Query cepat melalui join `instruments` untuk memeriksa apakah bot diizinkan trading pair tersebut.
  * `async def get_enabled_watchlist_with_instruments(self) -> List[Watchlist]`: Mengambil semua watchlist aktif dengan `selectinload(Watchlist.instrument)`.
  * `async def set_symbol_enabled(self, instrument_id: int, enabled: bool) -> Watchlist`.

---

## 4. Rincian Unit Test & Test Cases (`test_instrument_watchlist_repository.py`)

### File Test: `backend/tests/repository/test_instrument_watchlist_repository.py`

### Daftar Test Cases yang Diuji:
1. **`test_instrument_create_and_get_by_symbol`**:
   * *Aksi:* Buat instrumen `"BTCUSDT"`, panggil `repo.get_by_symbol("btcusdt")`.
   * *Assert:* Metadata presisi (`tick_size=0.10`, `step_size=0.001`) terambil dengan benar.
2. **`test_watchlist_add_and_is_symbol_enabled`**:
   * *Aksi:* Tambahkan instrumen ke watchlist (`enabled=True`), lalu panggil `wl_repo.is_symbol_enabled("BTCUSDT")`.
   * *Assert:* Mengembalikan `True`.
3. **`test_watchlist_disabled_symbol_check`**:
   * *Aksi:* Set `enabled=False` pada watchlist, panggil `is_symbol_enabled("BTCUSDT")`.
   * *Assert:* Mengembalikan `False`.
4. **`test_watchlist_eager_load_instrument`**:
   * *Aksi:* Panggil `get_enabled_watchlist_with_instruments()`.
   * *Assert:* Objek `Watchlist.instrument` dapat diakses langsung tanpa error async session.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_instrument_watchlist_repository.py -v
```
