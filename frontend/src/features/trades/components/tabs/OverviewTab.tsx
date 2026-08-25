import { TradeDetailDTO } from '@/types/trades';
import { Badge } from '@/components/ui/badge';
import { formatUSDT, formatCrypto, formatDateTime, formatDuration } from '@/utils/format';
import { Clock, ShieldAlert } from 'lucide-react';

export interface OverviewTabProps {
  trade: TradeDetailDTO;
}

export function OverviewTab({ trade }: OverviewTabProps) {
  const isBuy = trade.side === 'BUY';

  // Calculate duration if open/close events exist
  let durationSeconds: number | null = null;
  const openedEvent = trade.events?.find((e) => e.event_type.includes('OPEN') || e.event_type.includes('ENTRY'));
  const closedEvent = trade.events?.find((e) => e.event_type.includes('CLOSE') || e.event_type.includes('SL') || e.event_type.includes('TP'));

  if (openedEvent?.created_at && closedEvent?.created_at) {
    const start = new Date(openedEvent.created_at).getTime();
    const end = new Date(closedEvent.created_at).getTime();
    if (end >= start) {
      durationSeconds = Math.floor((end - start) / 1000);
    }
  }

  return (
    <div className="space-y-4 text-xs font-mono">
      {/* High-Level Badges & Status */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-lg bg-surface/60 border border-border/60">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-white tracking-wide">
            {trade.symbol}
          </span>
          <Badge variant={isBuy ? 'profit' : 'loss'} size="sm">
            {trade.side} {trade.leverage}x
          </Badge>
          <Badge variant="neutral" size="sm">
            {trade.status}
          </Badge>
        </div>
        <div className="text-slate-400 text-[11px]">
          Trade ID: <span className="text-white font-bold">#{trade.trade_id}</span>
        </div>
      </div>

      {/* Primary Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="p-3 rounded-lg bg-surface/40 border border-border/40 space-y-1">
          <span className="text-slate-400 text-[11px] block">Entry Price</span>
          <span className="text-sm font-bold text-white">
            {formatUSDT(trade.entry_price)}
          </span>
        </div>

        <div className="p-3 rounded-lg bg-surface/40 border border-border/40 space-y-1">
          <span className="text-slate-400 text-[11px] block">Initial Stop Loss</span>
          <span className="text-sm font-bold text-rose-400">
            {formatUSDT(trade.sl_price)}
          </span>
        </div>

        <div className="p-3 rounded-lg bg-surface/40 border border-border/40 space-y-1">
          <span className="text-slate-400 text-[11px] block">Position Size</span>
          <span className="text-sm font-bold text-white">
            {formatCrypto(trade.position_size, 4)}
          </span>
        </div>
      </div>

      {/* Lifecycle Timeline */}
      <div className="p-3.5 rounded-lg bg-surface/40 border border-border/40 space-y-2.5">
        <div className="flex items-center gap-1.5 text-slate-300 font-semibold text-xs">
          <Clock className="w-3.5 h-3.5 text-brand-400" />
          <span>Lifecycle Duration</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
          <div>
            <span className="text-slate-500 block">First Event:</span>
            <span className="text-slate-300">
              {trade.events?.[0]?.created_at
                ? formatDateTime(trade.events[0].created_at)
                : '-'}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block">Last Event:</span>
            <span className="text-slate-300">
              {trade.events?.length
                ? formatDateTime(trade.events[trade.events.length - 1].created_at)
                : '-'}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block">Duration:</span>
            <span className="text-slate-200 font-semibold">
              {durationSeconds !== null ? formatDuration(durationSeconds) : '-'}
            </span>
          </div>
        </div>
      </div>

      {/* Audit Events Snippet */}
      {trade.events && trade.events.length > 0 && (
        <div className="p-3 rounded-lg bg-surface/30 border border-border/30 space-y-1.5">
          <span className="text-slate-400 text-[11px] flex items-center gap-1">
            <ShieldAlert className="w-3 h-3 text-amber-400" />
            Audit Lifecycle Events ({trade.events.length})
          </span>
          <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
            {trade.events.map((ev, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between text-[10px] text-slate-400 py-0.5 border-b border-border/20 last:border-0"
              >
                <span className="font-semibold text-slate-200">{ev.event_type}</span>
                <span>{ev.created_at ? formatDateTime(ev.created_at) : ''}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
