import { useQuery, useMutation } from '@tanstack/react-query';
import {
  getAuditLogsApi,
  exportTradesCsvApi,
  triggerFileDownload,
} from '@/api/endpoints/logs';
import { LogEntryDTO, LogQueryParams, CsvExportParams } from '@/types/logs';

export function useAuditLogs(params: LogQueryParams, isLive = true) {
  return useQuery<LogEntryDTO[]>({
    queryKey: ['logs', params.level, params.trace_id, params.limit],
    queryFn: () => getAuditLogsApi(params),
    refetchInterval: isLive ? 3000 : false,
    staleTime: 2500,
  });
}

export function useExportCsvMutation() {
  return useMutation<Blob, Error, CsvExportParams>({
    mutationFn: ({ start_date, end_date }) =>
      exportTradesCsvApi(start_date, end_date),
    onSuccess: (blob, variables) => {
      const startTag = variables.start_date
        ? variables.start_date.replace(/-/g, '')
        : 'all';
      const endTag = variables.end_date
        ? variables.end_date.replace(/-/g, '')
        : 'all';
      const filename = `closed_trades_report_${startTag}_${endTag}.csv`;
      triggerFileDownload(blob, filename);
    },
  });
}
