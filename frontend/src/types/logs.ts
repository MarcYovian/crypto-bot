export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

export interface LogEntryDTO {
  id: number;
  level: LogLevel;
  module?: string | null;
  message: string;
  trace_id?: string | null;
  created_at: string;
}

export interface LogQueryParams {
  level?: string;
  trace_id?: string;
  limit?: number;
}

export interface CsvExportParams {
  start_date?: string;
  end_date?: string;
}
