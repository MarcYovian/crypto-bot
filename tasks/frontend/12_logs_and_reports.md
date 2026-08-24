# Task 12: System Audit Log Terminal & RFC 4180 CSV Report Exporter

## 1. Deskripsi Task
Membangun modul pemantauan log audit internal bergaya terminal monospaced (*System Audit Log Terminal*) dengan syntax highlighting berbasis severity, penelusuran korelasi `trace_id` sinyal, serta generator pengunduh laporan riwayat transaksi berformat CSV berstandar RFC 4180:
1. Membangun komponen **System Audit Log Terminal (`src/features/logs-reports/components/AuditLogsTerminal.tsx`)** yang mengonsumsi endpoint `GET /api/v1/logs`:
   * Antarmuka bergaya terminal konsol gelap pekat (`bg-black/90 font-mono`) dengan toggle *Auto-scroll to bottom*.
   * Syntax highlighting berbasis log severity:
     * `DEBUG`: Teks abu-abu muda (`#94A3B8`).
     * `INFO`: Teks biru elektrik (`#38BDF8`).
     * `WARNING`: Teks kuning amber (`#FBBF24`).
     * `ERROR` / `CRITICAL`: Teks merah mawar (`#F87171`).
   * Filter Bar Terminal: Dropdown filter level (`ALL`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`), input pencarian korelasi `trace_id` (misal: `sig-a1b2c3d4`), dan selector batas limit (50, 100, 200).
2. Membangun komponen **CSV Report Exporter (`src/features/logs-reports/components/CsvExportCard.tsx`)** yang mengonsumsi `GET /api/v1/reports/export/csv`:
   * Form pemilihan rentang tanggal transaksi: Datepicker `Start Date` dan `End Date`.
   * Validasi tanggal lokal: Memastikan `Start Date <= End Date`.
   * Tombol *Download CSV Report*: Memicu request file stream binary, membuat blob URL di browser, dan memulai unduhan file otomatis dengan format nama terstruktur `closed_trades_report_YYYYMMDD_YYYYMMDD.csv`.
   * Memastikan isi file CSV mematuhi standar RFC 4180 (memuat header: Trade ID, Symbol, Side, Entry Price, Close Price, Net PnL, Commission, ROI %, Result, Close Reason, Opened At, Closed At).

---

## 2. File yang Akan Dibuat / Dimodifikasi

### API Endpoints & Types:
* `frontend/src/api/endpoints/logs.ts`: Fungsi API `getAuditLogsApi(params: LogQueryParams)` dan `exportTradesCsvApi(startDate?: string, endDate?: string)`.
* `frontend/src/types/logs.ts`: TypeScript interfaces (`LogEntryDTO`, `LogQueryParams`).

### Komponen UI Log & Laporan:
* `frontend/src/features/logs-reports/LogsAndReportsPage.tsx`: Halaman utama audit logs dan reporting.
* `frontend/src/features/logs-reports/components/AuditLogsTerminal.tsx`: Terminal console penampil log sistem dengan auto-scroll dan copy trace ID.
* `frontend/src/features/logs-reports/components/LogFilterToolbar.tsx`: Toolbar filter severity level dan input trace ID.
* `frontend/src/features/logs-reports/components/CsvExportCard.tsx`: Kartu form datepicker dan tombol trigger unduh file CSV.

### Unit & Integration Tests:
* `frontend/tests/features/audit_logs_terminal.test.tsx`: Pengujian filter severity, pencarian trace ID, dan render baris log.
* `frontend/tests/features/csv_export.test.tsx`: Pengujian validasi rentang tanggal dan trigger download blob stream.

---

## 3. Rincian Endpoint API yang Diintegrasikan

### 1. `GET /api/v1/logs`
* **Query Parameters**:
  * `level` (`DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL`, opsional)
  * `trace_id` (string, opsional, misal: `sig-a1b2c3d4`)
  * `limit` (integer, default: 100)
* **Response (200 OK)**:
  ```json
  [
    {
      "id": 1,
      "level": "INFO",
      "module": "EXECUTION_ENGINE",
      "message": "Market order filled for BTCUSDT: 0.02 BTC @ 50000.00",
      "trace_id": "sig-a1b2c3d4",
      "created_at": "2026-08-24T14:30:05Z"
    }
  ]
  ```

### 2. `GET /api/v1/reports/export/csv`
* **Query Parameters**:
  * `start_date` (string format `YYYY-MM-DD`, opsional)
  * `end_date` (string format `YYYY-MM-DD`, opsional)
* **Response (200 OK)**:
  * Content-Type: `text/csv; charset=utf-8`
  * Content-Disposition: `attachment; filename="closed_trades_report_20260801_20260824.csv"`
  * Payload: Stream binary text CSV RFC 4180.

---

## 4. Rincian Alur Pengunduhan File CSV (Browser Blob Handler)

```typescript
export const downloadCsvBlob = async (startDate?: string, endDate?: string) => {
  const response = await apiClient.get('/api/v1/reports/export/csv', {
    params: { start_date: startDate, end_date: endDate },
    responseType: 'blob',
  });
  
  const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `closed_trades_report_${startDate || 'all'}_${endDate || 'all'}.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
```

---

## 5. Edge Cases & Error Handling
1. **Rentang Tanggal Terbalik (`Start Date > End Date`)**: Datepicker menampilkan validasi error lokal: *"Start Date tidak boleh lebih besar dari End Date"* dan tombol unduh dinonaktifkan.
2. **Dataset Transaksi Kosong pada Periode Terpilih**: Backend mengembalikan CSV yang hanya memuat baris header kolom. File tetap terunduh secara normal dan toast info muncul: *"File CSV terunduh (0 transaksi pada periode ini)"*.
3. **Banjir Log Ekstrem**: Terminal menerapkan batas rendering DOM (maksimal 200 baris terbaru) untuk mencegah konsumsi memori browser berlebih.

---

## 6. Kriteria Keberhasilan (Acceptance Criteria)
1. Terminal konsol menampilkan baris log monospaced dengan warna severity yang tepat (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
2. Filter severity level dan pencarian `trace_id` menyaring baris log secara instan.
3. Form datepicker mengekspor file `.csv` yang langsung terunduh di browser dengan struktur kolom dan nama file valid.
4. Seluruh unit test di `frontend/tests/features/audit_logs_terminal.test.tsx` dan `frontend/tests/features/csv_export.test.tsx` lulus 100%.
