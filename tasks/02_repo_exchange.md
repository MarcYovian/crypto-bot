# Task 02: Exchange Repository Implementation

## 1. Deskripsi Task
Membangun `ExchangeRepository` terdedikasi untuk entitas master bursa `Exchange` (`exchanges` table) yang mewarisi `BaseRepository[Exchange, ExchangeCreate, ExchangeUpdate]`.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/exchange_repository.py`](../backend/src/repository/exchange_repository.py)
* `[NEW]` [`backend/tests/repository/test_exchange_repository.py`](../backend/tests/repository/test_exchange_repository.py)

---

## 3. Rincian Isi `exchange_repository.py`

### Kelas `ExchangeRepository`
```python
class ExchangeRepository(BaseRepository[Exchange, ExchangeCreate, ExchangeUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(Exchange, session)
```

### Method Khusus:
1. `async def get_by_code(self, code: str) -> Optional[Exchange]`:
   * Mencari exchange berdasarkan kode unik (`code`), misal `"BINANCE"`, `"BYBIT"`.
   * Melakukan case-insensitive search (`func.upper(Exchange.code) == code.upper()`).
2. `async def get_active_exchanges(self) -> List[Exchange]`:
   * Mengambil semua exchange yang memiliki status `status == True`.
3. `async def toggle_status(self, id: int, status: bool) -> Optional[Exchange]`:
   * Mengaktifkan/menonaktifkan bursa dengan cepat.

---

## 4. Rincian Unit Test & Test Cases (`test_exchange_repository.py`)

### File Test: `backend/tests/repository/test_exchange_repository.py`

### Daftar Test Cases yang Diuji:
1. **`test_exchange_create_and_get_by_code`**:
   * *Aksi:* Membuat exchange dengan code `"BINANCE"`, lalu query `repo.get_by_code("binance")` (lowercase input).
   * *Assert:* Record ditemukan dan `code == "BINANCE"`.
2. **`test_exchange_duplicate_code_handling`**:
   * *Aksi:* Mencoba membuat exchange kedua dengan code yang sama (`"BINANCE"`).
   * *Assert:* Melempar IntegrityError / UniqueConstraint error.
3. **`test_exchange_get_active_exchanges`**:
   * *Aksi:* Membuat 1 exchange aktif (`status=True`) dan 1 non-aktif (`status=False`), lalu panggil `repo.get_active_exchanges()`.
   * *Assert:* Hanya exchange yang aktif yang dikembalikan.
4. **`test_exchange_toggle_status`**:
   * *Aksi:* Mengubah status exchange via `repo.toggle_status(id, False)`.
   * *Assert:* Field `status` berubah menjadi `False` dan `updated_at` terupdate.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_exchange_repository.py -v
```
