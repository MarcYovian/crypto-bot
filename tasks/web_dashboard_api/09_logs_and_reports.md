# Task 09: System Audit Logs & CSV Report Export Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint penelusuran log audit sistem interaktif dengan filter level dan correlation `trace_id` (`GET /api/v1/logs`), serta endpoint unduh laporan riwayat transaksi dalam format file CSV (*Comma-Separated Values*) standar bursa/keuangan (`GET /api/v1/reports/export/csv`).

Implementasi ini secara ketat menerapkan **Domain-Driven Service-Repository Pattern**:
* **Domain Layer**:
  * DTO: `LogEntryDTO` (`id`, `level`, `module`, `message`, `trace_id`, `created_at`).
* **Repository Layer**:
  * `BotLogRepository`: Query log terindeks (`idx_bot_logs_level_created`), filter level, dan correlation query `trace_id` pada field `context_json` dan `message` tanpa N+1 query.
  * `TradeRepository` & `TradeSummaryRepository`: Mengambil riwayat closed trades dan trade summaries dengan filter rentang tanggal (`start_date`, `end_date`) menggunakan join eager loading (`selectinload(Trade.summary)`, `selectinload(Trade.instrument)`).
* **Domain Service Layer**:
  * `LogService`: Mengorkestrasi pencarian log audit, parsing JSON context payload, dan ekstraksi `trace_id`.
  * `ReportService`: Mengambil dataset transaksi tertutup, memvalidasi rentang waktu, dan memformat baris CSV berstandar RFC 4180 dengan kalkulasi PnL, komisi, ROI, dan durasi trade.
* **Router Layer**:
  * `logs.py`: Controller endpoint `/api/v1/logs`.
  * `reports.py`: Controller endpoint `/api/v1/reports/export/csv` yang mengembalikan `StreamingResponse` dengan header `Content-Type: text/csv` dan `Content-Disposition: attachment; filename="trades_report.csv"`.

---

## 2. File yang Akan Dibuat & Dimodifikasi

### File Baru:
1. `backend/src/services/log_service.py`: Domain service untuk pencarian dan pemrosesan log audit sistem.
2. `backend/src/services/report_service.py`: Domain service untuk agregasi data dan pembentukan laporan CSV.
3. `backend/src/api/routers/logs.py`: Router FastAPI untuk `/api/v1/logs`.
4. `backend/src/api/routers/reports.py`: Router FastAPI untuk `/api/v1/reports/export/csv`.
5. `backend/tests/api/test_logs_reports_api.py`: Test suite komprehensif untuk pengujian query audit logs dan export CSV.

### Modifikasi File:
1. `backend/src/schemas/system.py` & `backend/src/schemas/__init__.py`: Menambahkan schema DTO:
   * `LogEntryDTO`: (`id: int`, `level: str`, `module: Optional[str]`, `message: str`, `trace_id: Optional[str]`, `created_at: datetime`).
2. `backend/src/repository/bot_log_repository.py`: Menambahkan method `query_logs(level, trace_id, limit)`.
3. `backend/src/services/__init__.py`: Mengekspor `LogService` dan `ReportService`.
4. `backend/src/api/deps.py`: Menambahkan dependency provider `get_log_service()` dan `get_report_service()`.
5. `backend/src/api/routers/__init__.py`: Mengekspor `logs_router` dan `reports_router`.
6. `backend/src/api/app.py`: Me-mount `logs_router` dan `reports_router`.

---

## 3. Spesifikasi Rinci Endpoint & Alur Kerja Bisnis

### A. `GET /api/v1/logs` (Pencarian Log Audit Sistem)
* **Summary**: Query system audit logs.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Query Parameters**:
  * `level: Optional[str]` — Filter tingkat keparahan: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
  * `trace_id: Optional[str]` — Filter penelusuran correlation id sinyal/transaksi (e.g. `sig-a1b2c3d4`).
  * `limit: int = 100` — Batas jumlah log yang dikembalikan (1 s/d 1000).
* **Alur Logika**:
  1. Validasi parameter `level` dan `limit`.
  2. Panggil `BotLogRepository.query_logs(level=level, trace_id=trace_id, limit=limit)`.
  3. Petakan entitas `BotLog` ke `LogEntryDTO`, mengekstrak `trace_id` dari `context_json` atau format message.
  4. Return `200 OK` dengan `List[LogEntryDTO]` berurutan waktu terbaru (*descending*).

---

### B. `GET /api/v1/reports/export/csv` (Unduh Laporan Transaksi CSV)
* **Summary**: Export trade history as CSV file.
* **Authentication**: Wajib Bearer JWT (`ADMIN` atau `VIEWER`).
* **Query Parameters**:
  * `start_date: Optional[date]` — Filter tanggal awal transaksi ditutup (`YYYY-MM-DD`).
  * `end_date: Optional[date]` — Filter tanggal akhir transaksi ditutup (`YYYY-MM-DD`).
* **Format Header & Kolom CSV**:
  ```csv
  Trade ID,Symbol,Side,Entry Price,Exit Price,Position Size,Leverage,Gross PnL (USDT),Commission (USDT),Net PnL (USDT),ROI %,Result,Close Reason,Opened At,Closed At
  ```
* **Alur Logika & Pembentukan File**:
  1. Validasi: jika `start_date` dan `end_date` diberikan, pastikan `start_date <= end_date`.
  2. Ambil data transaksi berstatus `CLOSED` via `TradeRepository` / `TradeSummaryRepository` lengkap dengan relasi `instrument` dan `summary` (**Zero N+1 Query**).
  3. Filter rentang `closed_at` berdasarkan parameter tanggal.
  4. Generate file CSV dalam memori menggunakan `io.StringIO` dan `csv.writer` standar RFC 4180.
  5. Return `200 OK` sebagai `StreamingResponse` dengan:
     * `media_type = "text/csv"`
     * `headers = {"Content-Disposition": 'attachment; filename="trades_report.csv"'}`

---

## 4. Matriks Pengujian Lengkap (Test Matrix)

Test suite `backend/tests/api/test_logs_reports_api.py` mencakup:

| Kategori | Nama Test | Deskripsi Skenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **Positif (Logs)** | `test_get_logs_all_recent` | Query 100 log terbaru tanpa filter. | `200 OK`, mengembalikan list `LogEntryDTO` berurutan waktu descending. |
| **Positif (Logs)** | `test_get_logs_filtered_by_level` | Query log dengan filter `level=ERROR`. | `200 OK`, seluruh log yang dikembalikan memiliki level `ERROR`. |
| **Positif (Logs)** | `test_get_logs_filtered_by_trace_id` | Query log dengan filter `trace_id="sig-12345"`. | `200 OK`, mengembalikan log yang berasosiasi dengan trace_id tersebut. |
| **Positif (Logs)** | `test_get_logs_pagination_limit` | Query log dengan `limit=5`. | `200 OK`, mengembalikan tepat 5 log. |
| **Positif (Reports)** | `test_export_trades_csv_success` | Unduh file CSV laporan trade tertutup. | `200 OK`, header `Content-Type: text/csv`, header kolom CSV lengkap dan baris data valid. |
| **Positif (Reports)** | `test_export_trades_csv_date_filter` | Unduh file CSV dengan rentang tanggal `start_date` dan `end_date`. | `200 OK`, hanya trade dalam rentang tanggal yang masuk ke dalam file CSV. |
| **Positif (Reports)** | `test_export_trades_csv_empty_dataset` | Unduh CSV saat database trade kosong. | `200 OK`, mengembalikan file CSV yang hanya memuat baris header kolom. |
| **Negatif** | `test_export_trades_csv_invalid_date_range` | Parameter `start_date > end_date` (e.g. 2026-08-30 s/d 2026-08-01). | `400 Bad Request` (`InvalidDateRangeError`). |
| **Negatif** | `test_get_logs_invalid_level` | Parameter `level="UNKNOWN_LEVEL"`. | `400 Bad Request` atau `422 Unprocessable Entity`. |
| **Security & Auth** | `test_logs_unauthorized_rejection` | Request `/api/v1/logs` tanpa Bearer token. | `401 Unauthorized`. |
| **Security & Auth** | `test_reports_unauthorized_rejection` | Request `/api/v1/reports/export/csv` tanpa Bearer token. | `401 Unauthorized`. |
| **Security & Auth** | `test_logs_and_reports_accessible_by_viewer_and_admin` | Request logs & reports dengan token `VIEWER` dan `ADMIN`. | Keduanya berhasil `200 OK` (laporan & audit logs dapat diakses semua pengguna terautentikasi). |

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. **Pencarian Log Efisien**: Pencarian log audit mampu memfilter berdasarkan severity level (`INFO`, `WARNING`, `ERROR`, dll.) dan mengkorelasikan seluruh siklus eksekusi sinyal menggunakan `trace_id`.
2. **Kesesuaian Format RFC 4180**: File CSV yang diexport memiliki format delimitasi koma yang valid, escaping karakter khusus yang tepat, serta data metrik PnL dan ROI yang presisi.
3. **Zero N+1 Query**: Data trades dan summaries di-query menggunakan batch eager loading.
4. **Kepatuhan OpenAPI**: Endpoint `GET /api/v1/logs` dan `GET /api/v1/reports/export/csv` 100% konsisten dengan `docs/openapi.yaml`.
5. **Mypy Static Typing**: 0 errors pada static type checking (`mypy backend/src/`).
6. **Testing**: Seluruh test di `test_logs_reports_api.py` dan seluruh test backend lulus 100%.
