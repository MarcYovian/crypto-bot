# Task 01: Base Repository Implementation

## 1. Deskripsi Task
Membangun generic abstract base repository `BaseRepository[ModelType, CreateSchemaType, UpdateSchemaType]` menggunakan SQLAlchemy 2.0 Async (`AsyncSession`) yang menyediakan operasi CRUD standar dan session management yang reusable.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/base.py`](../backend/src/repository/base.py)
* `[NEW]` [`backend/tests/repository/test_base_repository.py`](../backend/tests/repository/test_base_repository.py)

---

## 3. Rincian Isi `base.py`

### Kelas `BaseRepository`
```python
class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session
```

### Method yang Disediakan:
1. `async def get(self, id: int) -> Optional[ModelType]`: Mengambil 1 record berdasarkan Primary Key.
2. `async def get_multi(self, skip: int = 0, limit: int = 100) -> List[ModelType]`: Mengambil daftar record dengan pagination offset/limit.
3. `async def create(self, schema: CreateSchemaType) -> ModelType`: Membuat record baru dari Pydantic schema atau dict, melakukan `session.add()`, `commit()`, dan `refresh()`.
4. `async def update(self, db_obj: ModelType, schema: Union[UpdateSchemaType, Dict[str, Any]]) -> ModelType`: Memperbarui atribut objek dari schema/dict, melakukan `commit()`, dan `refresh()`.
5. `async def delete(self, id: int) -> bool`: Menghapus record berdasarkan ID. Mengembalikan `True` jika record ditemukan & dihapus, `False` jika tidak ditemukan.
6. `async def count(self) -> int`: Menghitung total record pada tabel.

---

## 4. Rincian Unit Test & Test Cases (`test_base_repository.py`)

### File Test: `backend/tests/repository/test_base_repository.py`

### Daftar Test Cases yang Diuji:
1. **`test_base_repo_create_and_get`**:
   * *Aksi:* Membuat record via `repo.create(schema)` lalu mengambilnya kembali via `repo.get(id)`.
   * *Assert:* Field tersimpan sesuai input dan ID auto-increment terisi.
2. **`test_base_repo_get_multi_pagination`**:
   * *Aksi:* Menambahkan 5 record, lalu memanggil `repo.get_multi(skip=1, limit=2)`.
   * *Assert:* Mengembalikan tepat 2 item dengan offset yang benar.
3. **`test_base_repo_update_with_schema_and_dict`**:
   * *Aksi:* Update sebagian atribut record via Pydantic update schema dan dict terpisah.
   * *Assert:* Atribut terupdate di database tanpa merusak atribut lainnya.
4. **`test_base_repo_delete`**:
   * *Aksi:* Menghapus record via `repo.delete(id)` dan mengecek `repo.get(id)`.
   * *Assert:* `repo.delete()` mengembalikan `True`, dan query `get()` berikutnya mengembalikan `None`.
5. **`test_base_repo_count`**:
   * *Aksi:* Memanggil `repo.count()`.
   * *Assert:* Jumlah baris sesuai dengan total record aktif.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_base_repository.py -v
```
