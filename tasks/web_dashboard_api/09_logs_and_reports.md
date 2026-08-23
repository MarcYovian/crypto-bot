# Task 09: System Audit Logs & CSV Report Export Endpoints

## 1. Deskripsi Task
Mengimplementasikan endpoint penelusuran log audit sistem dengan filter level dan correlation `trace_id` (`/api/v1/logs`), serta endpoint unduh riwayat transaksi dalam format file CSV/Excel (`/api/v1/reports/export/csv`).

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/api/routers/logs.py`: Router FastAPI untuk query log audit sistem.
* `backend/src/api/routers/reports.py`: Router FastAPI untuk export data laporan.
* `backend/tests/api/test_logs_reports_api.py`: Test suite untuk logs dan reports.

### Modifikasi File:
* `backend/src/api/app.py`: Menambahkan mounting `logs_router` dan `reports_router`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `GET /api/v1/logs`:
  * **Query Params**: `level: Optional[str]` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`), `trace_id: Optional[str]`, `limit: int = 100`.
  * **Logika**: Mengambil log dari tabel `bot_logs` diurutkan dari yang terbaru (*descending*).
  * **Response (200)**: `List[LogEntryDTO]`.
* `GET /api/v1/reports/export/csv`:
  * **Query Params**: `start_date: Optional[date]`, `end_date: Optional[date]`.
  * **Logika**: Mengambil data transaksi dari `trades` dan `trade_summaries`, memformat menjadi baris CSV dengan kolom: `ID, Symbol, Side, Entry Price, Exit Price, Position Size, Leverage, Gross PnL, Fee, Net PnL, ROI %, Result, Close Reason, Opened At, Closed At`.
  * **Response (200)**: `StreamingResponse` / File download dengan header `Content-Type: text/csv` dan `Content-Disposition: attachment; filename="trades_report.csv"`.

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Pencarian Log Fleksibel**: Mampu memfilter log berdasarkan log-level dan melacak alur transaksi tertentu menggunakan `trace_id`.
2. **Format CSV Valid**: File CSV yang diunduh memiliki struktur header dan baris data yang valid, dapat dibuka di Microsoft Excel atau Google Sheets.
3. **Testing**: Seluruh test di `backend/tests/api/test_logs_reports_api.py` lulus 100%.
