import { LogQueryParams } from '@/types/logs';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Search,
  SlidersHorizontal,
  X,
  Play,
  Pause,
  ArrowDown,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export interface LogFilterToolbarProps {
  params: LogQueryParams;
  onChange: (params: LogQueryParams) => void;
  isLive: boolean;
  onToggleLive: () => void;
  autoScroll: boolean;
  onToggleAutoScroll: () => void;
  totalLogsCount: number;
}

const LOG_LEVELS = ['ALL', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'DEBUG'];
const LIMIT_OPTIONS = [50, 100, 200];

export function LogFilterToolbar({
  params,
  onChange,
  isLive,
  onToggleLive,
  autoScroll,
  onToggleAutoScroll,
  totalLogsCount,
}: LogFilterToolbarProps) {
  const currentLevel = params.level || 'ALL';

  return (
    <div className="p-3.5 rounded-xl bg-surface/80 border border-border/60 font-mono text-xs space-y-3">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Severity Level Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-400 text-[11px] font-bold mr-1 flex items-center gap-1">
            <SlidersHorizontal className="w-3.5 h-3.5 text-brand-400" /> Level:
          </span>
          {LOG_LEVELS.map((lvl) => {
            const isSelected = currentLevel === lvl;
            return (
              <button
                key={lvl}
                type="button"
                onClick={() => onChange({ ...params, level: lvl })}
                className={cn(
                  'px-2.5 py-1 rounded-md text-[11px] font-bold transition-all border',
                  isSelected
                    ? lvl === 'ERROR' || lvl === 'CRITICAL'
                      ? 'bg-rose-600 text-white border-rose-500 shadow-glow-loss'
                      : lvl === 'WARNING'
                      ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-glow-warning'
                      : lvl === 'INFO'
                      ? 'bg-sky-500 text-white border-sky-400 shadow-sm'
                      : 'bg-brand-500 text-white border-brand-400 shadow-glow-brand'
                    : 'bg-surface/60 text-slate-400 border-border/60 hover:text-white'
                )}
              >
                {lvl}
              </button>
            );
          })}
        </div>

        {/* Live Stream & Auto-Scroll Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Auto-Scroll Toggle */}
          <button
            type="button"
            onClick={onToggleAutoScroll}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-bold transition-all',
              autoScroll
                ? 'bg-surface text-brand-300 border-brand-500/50'
                : 'bg-surface/50 text-slate-400 border-border/60'
            )}
          >
            <ArrowDown
              className={cn(
                'w-3.5 h-3.5',
                autoScroll ? 'text-brand-400 animate-bounce' : 'text-slate-500'
              )}
            />
            Auto-scroll
          </button>

          {/* Live Polling Stream Button */}
          <button
            type="button"
            onClick={onToggleLive}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1 rounded-lg border text-[11px] font-bold transition-all',
              isLive
                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/50 shadow-glow-profit'
                : 'bg-amber-950/80 text-amber-300 border-amber-500/50'
            )}
          >
            {isLive ? (
              <>
                <Pause className="w-3.5 h-3.5" />
                <span>STREAM LIVE</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                <span>STREAM PAUSED</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Search & Limit Row */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2 border-t border-border/40">
        {/* Trace ID search */}
        <div className="relative flex-1 w-full">
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
          <Input
            type="text"
            value={params.trace_id || ''}
            onChange={(e) => onChange({ ...params, trace_id: e.target.value })}
            placeholder="Filter by signal / trade correlation trace_id (e.g. sig-a1b2c3d4)..."
            className="pl-9 pr-8 h-8 text-xs bg-surface/60 border-border/80 text-white font-mono"
          />
          {params.trace_id && (
            <button
              type="button"
              onClick={() => onChange({ ...params, trace_id: '' })}
              className="absolute right-2.5 top-2 text-slate-400 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Limit Dropdown & Counter */}
        <div className="flex items-center gap-2 self-end sm:self-auto shrink-0 text-[11px] text-slate-400">
          <span>Display Limit:</span>
          <div className="flex items-center gap-1">
            {LIMIT_OPTIONS.map((lim) => (
              <button
                key={lim}
                type="button"
                onClick={() => onChange({ ...params, limit: lim })}
                className={cn(
                  'px-2 py-0.5 rounded text-xs font-bold transition-all',
                  (params.limit || 100) === lim
                    ? 'bg-slate-700 text-white border border-slate-500'
                    : 'bg-surface/50 text-slate-500 hover:text-white'
                )}
              >
                {lim}
              </button>
            ))}
          </div>

          <Badge variant="neutral" size="sm" className="ml-1">
            {totalLogsCount} logs loaded
          </Badge>
        </div>
      </div>
    </div>
  );
}
