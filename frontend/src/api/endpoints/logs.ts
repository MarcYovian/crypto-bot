import { apiClient } from '@/api/client';
import { LogEntryDTO, LogQueryParams } from '@/types/logs';

/**
 * Query system audit logs with optional severity filtering and trace_id correlation.
 */
export async function getAuditLogsApi(
  params?: LogQueryParams
): Promise<LogEntryDTO[]> {
  const cleanParams: Record<string, unknown> = {};
  if (params?.level && params.level !== 'ALL') {
    cleanParams.level = params.level;
  }
  if (params?.trace_id && params.trace_id.trim() !== '') {
    cleanParams.trace_id = params.trace_id.trim();
  }
  if (params?.limit) {
    cleanParams.limit = params.limit;
  }

  const res = await apiClient.get<LogEntryDTO[]>('/logs', {
    params: cleanParams,
  });
  return res.data;
}

/**
 * Download a complete RFC 4180 CSV export of closed trade history with metrics.
 */
export async function exportTradesCsvApi(
  startDate?: string,
  endDate?: string
): Promise<Blob> {
  const params: Record<string, string> = {};
  if (startDate) params.start_date = startDate;
  if (endDate) params.end_date = endDate;

  const res = await apiClient.get('/reports/export/csv', {
    params,
    responseType: 'blob',
  });

  return res.data as Blob;
}

/**
 * Utility to trigger browser file download from Blob.
 */
export function triggerFileDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
