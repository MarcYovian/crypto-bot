import { SignalItemDTO } from '@/types/signals';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { formatUSDT, formatPercent, formatDateTime } from '@/utils/format';
import { Send, Zap } from 'lucide-react';

export interface SignalCompactRowProps {
  signal: SignalItemDTO;
  onExecuteClick: (signal: SignalItemDTO) => void;
}

export function SignalCompactRow({
  signal,
  onExecuteClick,
}: SignalCompactRowProps) {
  const isBuy = signal.side === 'BUY';
  const isPending = signal.status === 'PENDING' || signal.status === 'RECEIVED';
  const isProcessed = signal.status === 'PROCESSED' || signal.status === 'EXECUTED';
  const isRejected = signal.status === 'REJECTED' || signal.status === 'CANCELLED';

  const confidencePct = signal.confidence_score
    ? signal.confidence_score <= 1
      ? signal.confidence_score * 100
      : signal.confidence_score
    : 100;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-surface/50 border border-border/40 hover:bg-surface/80 hover:border-slate-600/80 transition-all font-mono text-xs">
      {/* Symbol & Direction */}
      <div className="flex items-center gap-2 min-w-[160px]">
        <span className="font-bold text-white tracking-wide">
          {signal.symbol}
        </span>
        <Badge variant={isBuy ? 'profit' : 'loss'} size="sm">
          {signal.side}
        </Badge>
        <Badge
          variant="outline"
          size="sm"
          className="text-purple-400 border-purple-800/60 bg-purple-950/30 text-[10px] px-1.5"
        >
          <Zap className="w-2.5 h-2.5 mr-0.5 text-purple-400" />
          {formatPercent(confidencePct, false, 0)}
        </Badge>
      </div>

      {/* Target Prices */}
      <div className="flex items-center gap-4 text-[11px]">
        <div>
          <span className="text-slate-500 mr-1">Entry:</span>
          <span className="text-slate-200 font-semibold">
            {formatUSDT(signal.entry_price)}
          </span>
        </div>
        <div>
          <span className="text-slate-500 mr-1">SL:</span>
          <span className="text-rose-400 font-semibold">
            {formatUSDT(signal.sl_price)}
          </span>
        </div>
        <div className="hidden sm:block">
          <span className="text-slate-500 mr-1">TP1:</span>
          <span className="text-emerald-400 font-semibold">
            {signal.tp_targets?.[0] ? formatUSDT(signal.tp_targets[0]) : '-'}
          </span>
        </div>
      </div>

      {/* Status, Time & Action */}
      <div className="flex items-center gap-3">
        <div className="text-[10px] text-slate-500 hidden md:block">
          {formatDateTime(signal.created_at)}
        </div>

        <Badge
          variant={
            isProcessed
              ? 'profit-neon'
              : isPending
              ? 'info'
              : isRejected
              ? 'loss'
              : 'neutral'
          }
          size="sm"
        >
          {signal.status}
        </Badge>

        <RoleGuard requiredRole="ADMIN" mode="disable">
          <Button
            variant={isPending ? 'primary' : 'secondary'}
            size="sm"
            disabled={!isPending}
            onClick={() => onExecuteClick(signal)}
            className="h-7 px-2.5 text-[11px] gap-1"
          >
            <Send className="w-3 h-3" />
            {isPending ? 'Execute' : signal.status}
          </Button>
        </RoleGuard>
      </div>
    </div>
  );
}
