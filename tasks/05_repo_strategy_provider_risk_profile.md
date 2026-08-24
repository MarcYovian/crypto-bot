# Task 05: Strategy, Signal Provider & Risk Profile Repositories Implementation

## 1. Deskripsi Task
Membangun repository terpisah untuk model Strategi Trading (`Strategy`), Provider Sinyal (`SignalProvider`), dan Profil Risiko (`RiskProfile`).

---

## 2. File yang Dibuat / Diubah
* `[NEW]` [`backend/src/repository/strategy_repository.py`](../backend/src/repository/strategy_repository.py)
* `[NEW]` [`backend/src/repository/signal_provider_repository.py`](../backend/src/repository/signal_provider_repository.py)
* `[NEW]` [`backend/src/repository/risk_profile_repository.py`](../backend/src/repository/risk_profile_repository.py)
* `[NEW]` [`backend/tests/repository/test_master_config_repositories.py`](../backend/tests/repository/test_master_config_repositories.py)

---

## 3. Rincian Isi Repositories

### 1. `strategy_repository.py` (`StrategyRepository`)
* Mewarisi `BaseRepository[Strategy, StrategyCreate, StrategyUpdate]`.
* **Method Khusus:**
  * `async def get_by_name(self, name: str) -> Optional[Strategy]`.
  * `async def get_active_strategies(self) -> List[Strategy]`.

### 2. `signal_provider_repository.py` (`SignalProviderRepository`)
* Mewarisi `BaseRepository[SignalProvider, SignalProviderCreate, SignalProviderUpdate]`.
* **Method Khusus:**
  * `async def get_by_name(self, name: str) -> Optional[SignalProvider]`.
  * `async def get_by_type(self, provider_type: str = "TELEGRAM") -> List[SignalProvider]`.

### 3. `risk_profile_repository.py` (`RiskProfileRepository`)
* Mewarisi `BaseRepository[RiskProfile, RiskProfileCreate, RiskProfileUpdate]`.
* **Method Khusus:**
  * `async def get_active_profile(self) -> Optional[RiskProfile]`: Mengambil default profil risiko aktif (misal 2.0% risk rule).
  * `async def set_active_profile(self, profile_id: int) -> Optional[RiskProfile]`: Mengaktifkan 1 profil dan menonaktifkan lainnya.

---

## 4. Rincian Unit Test & Test Cases (`test_master_config_repositories.py`)

### File Test: `backend/tests/repository/test_master_config_repositories.py`

### Daftar Test Cases yang Diuji:
1. **`test_strategy_create_and_get_by_name`**:
   * *Aksi:* Buat strategi `"SMC Liquidity Sweep"`, query via `repo.get_by_name()`.
   * *Assert:* Strategi ditemukan dengan versi `"1.0.0"`.
2. **`test_signal_provider_filter_by_type`**:
   * *Aksi:* Buat 2 provider `"TELEGRAM"` dan 1 `"WEBHOOK"`, query `repo.get_by_type("TELEGRAM")`.
   * *Assert:* Mengembalikan 2 provider.
3. **`test_risk_profile_get_and_switch_active`**:
   * *Aksi:* Buat Profile A (2% risk) dan Profile B (1% risk), aktifkan Profile B via `set_active_profile()`.
   * *Assert:* `get_active_profile()` mengembalikan Profile B dengan `risk_percent == Decimal("1.0")`.

---

## 5. Rencana Verifikasi
```bash
PYTHONPATH=backend pytest backend/tests/repository/test_master_config_repositories.py -v
```
