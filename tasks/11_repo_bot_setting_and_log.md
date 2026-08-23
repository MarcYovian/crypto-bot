# Task 11: Bot Setting & Log Repositories Implementation (Expanded)

## 1. Deskripsi Task
Membangun repository terpisah untuk model **Konfigurasi Global Dinamis** (`BotSetting` / `bot_settings` table) dan **Pencatatan Log Audit Sistem** (`BotLog` / `bot_logs` table), dilengkapi helper konversi tipe data otomatis (`get_bool`, `get_int`, `get_float`, `get_json`), pencatatan context dictionary, pembersihan log lawas (*log retention purging*), serta **Finalisasi Central Re-exports** seluruh repository di `backend/src/repository/__init__.py`.

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/bot_setting_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/bot_setting_repository.py) *(Model: BotSetting)*
* `[NEW]` [`backend/src/repository/bot_log_repository.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/bot_log_repository.py) *(Model: BotLog)*
* `[MODIFY]` [`backend/src/repository/__init__.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/src/repository/__init__.py) *(Centralized Export)*
* `[NEW]` [`backend/tests/repository/test_system_repositories.py`](file:///home/rodex/Documents/cell/projects/crypto-bot/backend/tests/repository/test_system_repositories.py)

---

## 3. Rincian Isi Repositories

### 1. `bot_setting_repository.py` (`BotSettingRepository`)
* Mewarisi `BaseRepository[BotSetting, BotSettingCreate, BotSettingUpdate]`.
* **Method Khusus:**
  * `async def get_by_key(self, key: str) -> Optional[BotSetting]`:
    * Lookup setting via key unik case-insensitive (`func.upper(BotSetting.key)`).
  * `async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]`:
    * Mengambil nilai string mentah dari key, fallback ke `default` jika tidak ada.
  * `async def get_bool(self, key: str, default: bool = False) -> bool`:
    * Helper boolean: mengembalikan `True` jika value string `'true'`, `'1'`, `'yes'`, `'on'`.
  * `async def get_int(self, key: str, default: int = 0) -> int`:
    * Helper integer: parsing string ke `int` aman.
  * `async def get_float(self, key: str, default: float = 0.0) -> float`:
    * Helper float: parsing string ke `float` aman.
  * `async def get_json(self, key: str, default: Optional[Any] = None) -> Optional[Any]`:
    * Helper JSON: deserialisasi JSON string ke Python dictionary / list.
  * `async def set_value(self, key: str, value: str, category: str = "GENERAL", setting_type: str = "STRING", description: Optional[str] = None) -> BotSetting`:
    * Upsert otomatis (insert jika belum ada, update `value` dan `updated_at` jika sudah ada).
  * `async def get_all_by_category(self, category: str) -> List[BotSetting]`:
    * Mengambil konfigurasi per grup (`TRADING`, `RISK`, `TELEGRAM`, `SYSTEM`).
  * `async def get_all_as_dict(self) -> Dict[str, str]`:
    * Mengambil seluruh key-value pair menjadi kamus dictionary Python untuk in-memory cache.

### 2. `bot_log_repository.py` (`BotLogRepository`)
* Mewarisi `BaseRepository[BotLog, BotLogCreate, BaseSchema]`.
* **Method Khusus:**
  * `async def create_log(self, level: str, message: str, module: Optional[str] = None, context: Optional[Union[str, dict]] = None) -> BotLog`:
    * Helper cepat logging sistem; otomatis serialisasi `dict` ke `context_json`.
  * `async def get_recent_logs(self, limit: int = 100, level: Optional[str] = None, module: Optional[str] = None) -> List[BotLog]`:
    * Menggunakan index `idx_bot_logs_level_created` (diurutkan `created_at DESC`).
  * `async def get_error_logs(self, limit: int = 50, start_date: Optional[datetime] = None) -> List[BotLog]`:
    * Mengambil daftar log berlevel `ERROR` atau `CRITICAL` untuk audit insiden bot.
  * `async def purge_old_logs(self, days: int = 30) -> int`:
    * Menghapus log lawas yang usianya melebihi `days` hari untuk menghemat ruang disk database.

### 3. Central Re-exports di `backend/src/repository/__init__.py`
* Mengekspor secara terpusat:
  * `BaseRepository`
  * `ExchangeRepository`
  * `TradingAccountRepository`, `TradingCredentialRepository`
  * `InstrumentRepository`, `WatchlistRepository`
  * `StrategyRepository`, `SignalProviderRepository`, `RiskProfileRepository`
  * `SignalRepository`
  * `DailyRiskRepository`, `TradeRiskRepository`
  * `TradeRepository`
  * `OrderRepository`, `ExecutionRepository`
  * `TradeEventRepository`, `TradeSummaryRepository`
  * `BotSettingRepository`, `BotLogRepository`

---

## 4. Rincian Unit Test & Test Cases (`test_system_repositories.py`)

### File Test: `backend/tests/repository/test_system_repositories.py`

### Daftar Test Cases yang Diuji:
1. **`test_bot_setting_upsert_and_get_value`**:
   * *Aksi:* Simpan setting `"DEFAULT_LEVERAGE" = "15"`, lalu ubah menjadi `"20"`.
   * *Assert:* `get_value("DEFAULT_LEVERAGE")` mengembalikan `"20"` dan tidak ada duplikasi row.
2. **`test_bot_setting_type_helpers`**:
   * *Aksi:* Simpan setting bertipe Boolean (`"AUTO_TRADE" = "true"`), Integer (`"MAX_OPEN" = "3"`), Float (`"RISK" = "2.5"`), dan JSON (`"PAIRS" = '["BTC", "ETH"]'`).
   * *Assert:* Method `get_bool()`, `get_int()`, `get_float()`, `get_json()` mengembalikan tipe data Python asli dengan benar.
3. **`test_bot_setting_get_all_by_category_and_as_dict`**:
   * *Aksi:* Simpan beberapa setting dengan kategori `TRADING` dan `RISK`, query `get_all_as_dict()`.
   * *Assert:* Dictionary berisi seluruh pasangan key-value yang tersimpan.
4. **`test_bot_log_create_and_filter_by_level`**:
   * *Aksi:* Buat 2 log `INFO` dan 1 log `ERROR`, panggil `get_recent_logs(level="ERROR")`.
   * *Assert:* Hanya 1 log `ERROR` yang dikembalikan.
5. **`test_bot_log_json_context_and_error_query`**:
   * *Aksi:* Log error dengan context dict `{"trade_id": 99, "error_code": -2019}`. Panggil `get_error_logs()`.
   * *Assert:* Log ditemukan dan context JSON dapat di-parse kembali.
6. **`test_bot_log_purge_old_records`**:
   * *Aksi:* Simpan log lawas (created_at 40 hari lalu) dan log baru, jalankan `purge_old_logs(days=30)`.
   * *Assert:* Hanya log lawas yang terhapus dan mengembalikan `rowcount == 1`.
7. **`test_repository_package_central_exports`**:
   * *Aksi:* Import seluruh kelas repository dari `src.repository`.
   * *Assert:* Seluruh repository class ter-export tanpa `ImportError`.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_system_repositories.py -v
```
