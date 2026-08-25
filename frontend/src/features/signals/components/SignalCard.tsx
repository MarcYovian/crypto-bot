import { useState } from 'react';
import { SignalItemDTO } from '@/types/signals';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { formatUSDT, formatPercent, formatDateTime } from '@/utils/format';
import {
  Send,
  Zap,
  Radio,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

export interface SignalCardProps {
  signal: SignalItemDTO;
  onExecuteClick: (signal: SignalItemDTO) => void;
}

export function SignalCard({ signal, onExecuteClick }: SignalCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

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
    <Card className="glass-card hover:border-slate-600/80 transition-all font-mono text-xs overflow-hidden">
      <CardHeader className="pb-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          {/* Symbol, Side & Confidence */}
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-brand-400 shrink-0" />
            <CardTitle className="text-sm font-bold text-white tracking-wide">
              {signal.symbol}
            </CardTitle>
            <Badge variant={isBuy ? 'profit' : 'loss'} size="sm">
              {signal.side}
            </Badge>
            <Badge
              variant="outline"
              size="sm"
              className="text-purple-400 border-purple-800/60 bg-purple-950/30 text-[10px]"
            >
              <Zap className="w-2.5 h-2.5 mr-0.5 text-purple-400" />
              {formatPercent(confidencePct, false, 0)} AI
            </Badge>
          </div>

          {/* Status Badge */}
          <div>
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
          </div>
        </div>

        <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1">
          <span>{signal.trace_id ? `#${signal.trace_id}` : `ID: #${signal.id}`}</span>
          <span>{formatDateTime(signal.created_at)}</span>
        </div>
      </CardHeader>

      <CardContent className="pt-0 space-y-3">
        {/* Price Targets Grid */}
        <div className="grid grid-cols-3 gap-2 p-2.5 rounded-lg bg-surface/50 border border-border/40 text-[11px]">
          <div>
            <span className="text-slate-500 block text-[10px]">Entry:</span>
            <span className="text-white font-bold">
              {formatUSDT(signal.entry_price)}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">Stop Loss:</span>
            <span className="text-rose-400 font-bold">
              {formatUSDT(signal.sl_price)}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">Take Profits:</span>
            <span className="text-emerald-400 font-semibold text-[10px]">
              {signal.tp_targets && signal.tp_targets.length > 0
                ? signal.tp_targets.map((tp) => formatUSDT(tp)).join(' / ')
                : '-'}
            </span>
          </div>
        </div>

        {/* Expandable Raw Message Snippet */}
        {signal.raw_text && (
          <div className="space-y-1">
            <button
              onClick={() => setIsExpanded((prev) => !prev)}
              className="text-[10px] text-slate-400 hover:text-slate-200 flex items-center gap-1 cursor-pointer transition-colors"
            >
              {isExpanded ? (
                <>
                  <ChevronUp className="w-3 h-3" /> Hide Telegram Raw Text
                </>
              ) : (
                <>
                  <ChevronDown className="w-3 h-3" /> View Telegram Raw Text
                </>
              )}
            </button>
            {isExpanded && (
              <pre className="p-2 rounded bg-black/40 border border-border/30 text-[10px] text-slate-300 whitespace-pre-wrap break-all leading-tight font-mono">
                {signal.raw_text}
              </pre>
            )}
          </div>
        )}

        {/* Action Button: 1-Click Execution */}
        <div className="pt-1 flex items-center justify-end">
          <RoleGuard requiredRole="ADMIN" mode="disable">
            <Button
              variant={isPending ? 'primary' : 'secondary'}
              size="sm"
              disabled={!isPending}
              onClick={() => onExecuteClick(signal)}
              className="gap-1.5 text-xs font-semibold"
            >
              <Send className="w-3.5 h-3.5" />
              {isPending ? 'Execute Trade' : signal.status}
            </Button>
          </RoleGuard>
        </div>
      </CardContent>
    </Card>
  );
}
