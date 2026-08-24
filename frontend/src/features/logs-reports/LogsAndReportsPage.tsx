import { useState } from 'react';
import { useAuditLogs } from '@/hooks/useLogsAndReports';
import { LogQueryParams } from '@/types/logs';
import { LogFilterToolbar } from './components/LogFilterToolbar';
import { AuditLogsTerminal } from './components/AuditLogsTerminal';
import { CsvExportCard } from './components/CsvExportCard';

export function LogsAndReportsPage() {
  const [params, setParams] = useState<LogQueryParams>({
    level: 'ALL',
    trace_id: '',
    limit: 100,
  });

  const [isLive, setIsLive] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);

  const { data: logs = [], isLoading } = useAuditLogs(params, isLive);

  return (
    <div className="space-y-4 font-mono">
      {/* 1. CSV Performance Report Exporter */}
      <CsvExportCard />

      {/* 2. System Audit Log Terminal Suite */}
      <div className="space-y-3">
        <LogFilterToolbar
          params={params}
          onChange={setParams}
          isLive={isLive}
          onToggleLive={() => setIsLive(!isLive)}
          autoScroll={autoScroll}
          onToggleAutoScroll={() => setAutoScroll(!autoScroll)}
          totalLogsCount={logs.length}
        />

        <AuditLogsTerminal
          logs={logs}
          isLoading={isLoading}
          autoScroll={autoScroll}
        />
      </div>
    </div>
  );
}
