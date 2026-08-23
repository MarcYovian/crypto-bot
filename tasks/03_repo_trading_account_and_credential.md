# Task 03: Trading Account & Credential Repositories Implementation

## 1. Deskripsi Task
Membangun repository terpisah untuk model Akun Trading (`TradingAccount`) dan Kredensial API (`TradingCredential`) guna mengelola otentikasi exchange secara aman.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/trading_account_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/trading_account_repository.py)
* `[NEW]` [`backend/src/repository/trading_credential_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/trading_credential_repository.py)
* `[NEW]` [`backend/tests/repository/test_account_credential_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/tests/repository/test_account_credential_repository.py)

---

## 3. Rincian Isi Repositories

### 1. `trading_account_repository.py` (`TradingAccountRepository`)
* Mewarisi `BaseRepository[TradingAccount, TradingAccountCreate, TradingAccountUpdate]`.
* **Method Khusus:**
  * `async def get_active_account(self, exchange_id: int) -> Optional[TradingAccount]`: Mengambil akun aktif utama untuk exchange tertentu.
  * `async def get_by_environment(self, environment: str = "MAINNET") -> List[TradingAccount]`: Filter akun MAINNET vs TESTNET.
  * `async def get_account_with_credentials(self, account_id: int) -> Optional[TradingAccount]`: Eager load relasi credentials via `selectinload`.

### 2. `trading_credential_repository.py` (`TradingCredentialRepository`)
* Mewarisi `BaseRepository[TradingCredential, TradingCredentialCreate, TradingCredentialUpdate]`.
* **Method Khusus:**
  * `async def get_active_credential(self, account_id: int) -> Optional[TradingCredential]`: Mengambil API Key aktif untuk akun tertentu.
  * `async def deactivate_old_credentials(self, account_id: int) -> int`: Menonaktifkan kunci lama saat rotasi API key.

---

## 4. Rincian Unit Test & Test Cases (`test_account_credential_repository.py`)

### File Test: `backend/tests/repository/test_account_credential_repository.py`

### Daftar Test Cases yang Diuji:
1. **`test_trading_account_create_and_query_active`**:
   * *Aksi:* Buat akun FUTURES TESTNET aktif, query via `repo.get_active_account(exchange_id)`.
   * *Assert:* Akun ditemukan dan `is_active is True`.
2. **`test_trading_account_filter_environment`**:
   * *Aksi:* Buat 1 TESTNET dan 1 MAINNET, query via `repo.get_by_environment("TESTNET")`.
   * *Assert:* Hanya akun TESTNET yang dikembalikan.
3. **`test_trading_credential_create_and_fetch_active`**:
   * *Aksi:* Simpan kredensial terenkripsi untuk akun, query `cred_repo.get_active_credential(account_id)`.
   * *Assert:* Kredensial aktif ditemukan dengan `key_version == 1`.
4. **`test_credential_rotation_deactivate_old`**:
   * *Aksi:* Panggil `deactivate_old_credentials(account_id)`, lalu simpan kredensial baru version 2.
   * *Assert:* Kunci lama `is_active` menjadi `False`, kunci baru aktif.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_account_credential_repository.py -v
```
