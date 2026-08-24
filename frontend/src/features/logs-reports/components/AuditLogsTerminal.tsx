import { useRef, useEffect, useState } from 'react';
import { LogEntryDTO } from '@/types/logs';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Terminal,
  Copy,
  Check,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export interface AuditLogsTerminalProps {
  logs: LogEntryDTO[];
  isLoading?: boolean;
  autoScroll?: boolean;
}

export function AuditLogsTerminal({
  logs,
  isLoading = false,
  autoScroll = true,
}: AuditLogsTerminalProps) {
  const terminalBottomRef = useRef<HTMLDivElement | null>(null);
  const [copiedTraceId, setCopiedTraceId] = useState<string | null>(null);

  // Auto-scroll effect
  useEffect(() => {
    if (autoScroll && terminalBottomRef.current) {
      terminalBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  const handleCopyTraceId = (traceId: string) => {
    navigator.clipboard.writeText(traceId);
    setCopiedTraceId(traceId);
    setTimeout(() => setCopiedTraceId(null), 2000);
  };

  const getSeverityStyle = (level: string) => {
    switch (level.toUpperCase()) {
      case 'CRITICAL':
      case 'ERROR':
        return {
          textColor: 'text-rose-400',
          badgeVariant: 'loss' as const,
          borderColor: 'border-rose-900/40',
          bg: 'bg-rose-950/20',
        };
      case 'WARNING':
        return {
          textColor: 'text-amber-400',
          badgeVariant: 'warning' as const,
          borderColor: 'border-amber-900/40',
          bg: 'bg-amber-950/20',
        };
      case 'INFO':
        return {
          textColor: 'text-sky-300',
          badgeVariant: 'info' as const,
          borderColor: 'border-sky-900/40',
          bg: 'bg-sky-950/10',
        };
      case 'DEBUG':
      default:
        return {
          textColor: 'text-slate-400',
          badgeVariant: 'neutral' as const,
          borderColor: 'border-slate-800',
          bg: 'bg-transparent',
        };
    }
  };

  return (
    <Card className="glass-card font-mono text-xs overflow-hidden border-slate-800 bg-slate-950/95 shadow-2xl">
      {/* Terminal Window Header Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900/90 border-b border-slate-800 select-none">
        <div className="flex items-center gap-2">
          {/* OS Window Dots */}
          <div className="flex items-center gap-1.5 mr-2">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80 inline-block" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80 inline-block" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 inline-block" />
          </div>

          <Terminal className="w-3.5 h-3.5 text-brand-400" />
          <span className="text-slate-200 font-bold text-xs tracking-tight">
            system_audit_terminal.log
          </span>
        </div>

        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping inline-block" />
          <span>RFC 3339 UTC STREAM</span>
        </div>
      </div>

      {/* Terminal Output Body */}
      <div className="p-3 h-[480px] overflow-y-auto custom-scrollbar font-mono text-[11px] leading-relaxed space-y-1 bg-black/90">
        {isLoading && logs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500 gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping" />
            Connecting to audit log stream...
          </div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 space-y-1">
            <Terminal className="w-8 h-8 text-slate-700 mb-1" />
            <p>No audit logs matching current filter parameters.</p>
          </div>
        ) : (
          logs.map((log) => {
            const sev = getSeverityStyle(log.level);
            const timeStr = log.created_at
              ? new Date(log.created_at).toLocaleTimeString('en-US', {
                  hour12: false,
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })
              : '00:00:00';

            return (
              <div
                key={log.id}
                className={cn(
                  'flex items-start gap-2 p-1.5 rounded hover:bg-slate-900/60 transition-colors border border-transparent hover:border-slate-800',
                  sev.bg
                )}
              >
                {/* Timestamp */}
                <span className="text-slate-500 shrink-0 select-none text-[10px] pt-0.5">
                  [{timeStr}]
                </span>

                {/* Level Badge */}
                <Badge
                  variant={sev.badgeVariant}
                  size="sm"
                  className="font-bold text-[9px] px-1.5 py-0 shrink-0 uppercase"
                >
                  {log.level}
                </Badge>

                {/* Module Tag */}
                {log.module && (
                  <span className="text-slate-400 font-bold shrink-0 text-[10px] pt-0.5">
                    [{log.module}]
                  </span>
                )}

                {/* Log message */}
                <span className={cn('flex-1 break-all pt-0.5', sev.textColor)}>
                  {log.message}
                </span>

                {/* Trace ID Tag */}
                {log.trace_id && (
                  <button
                    type="button"
                    onClick={() => handleCopyTraceId(log.trace_id!)}
                    title={`Click to copy trace_id: ${log.trace_id}`}
                    className="shrink-0 flex items-center gap-1 text-[10px] text-brand-400/90 bg-brand-950/60 border border-brand-800/50 hover:bg-brand-900/60 px-1.5 py-0.5 rounded transition-all select-all font-mono"
                  >
                    {copiedTraceId === log.trace_id ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-400" />
                        <span className="text-emerald-300">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-2.5 h-2.5 text-brand-400" />
                        <span>{log.trace_id}</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            );
          })
        )}
        <div ref={terminalBottomRef} />
      </div>
    </Card>
  );
}
