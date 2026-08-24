import { TradeDetailDTO } from '@/types/trades';
import { Badge } from '@/components/ui/badge';
import { formatUSDT, formatPercent } from '@/utils/format';
import { cn } from '@/utils/cn';
import { TrendingUp, TrendingDown, DollarSign, Percent, Scale } from 'lucide-react';

export interface FinancialSummaryTabProps {
  trade: TradeDetailDTO;
}

export function FinancialSummaryTab({ trade }: FinancialSummaryTabProps) {
  const summary = trade.summary;
  const isCancelled = trade.status === 'CANCELLED';

  if (isCancelled || !summary) {
    return (
      <div className="py-8 text-center text-xs text-slate-500 font-mono space-y-2">
        <Badge variant="neutral" size="sm">
          {trade.status} - NO FINANCIAL SUMMARY
        </Badge>
        <p>This trade was cancelled or expired before final settlement.</p>
      </div>
    );
  }

  const isProfit = summary.net_pnl >= 0;
  const isWin = summary.result === 'WIN';
  const isLoss = summary.result === 'LOSS';

  // Calculate Realized R:R Ratio safely
  let rrRatio: string = '-';
  const riskAmount = trade.risk_details?.risk_amount_usdt ?? 0;
  if (riskAmount > 0) {
    const rawRR = summary.net_pnl / riskAmount;
    rrRatio = `${rawRR.toFixed(2)}R`;
  }

  return (
    <div className="space-y-4 font-mono text-xs">
      {/* Header Outcome Banner */}
      <div className="flex items-center justify-between p-3.5 rounded-lg bg-surface/60 border border-border/60">
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Trade Outcome:</span>
          <Badge
            variant={isWin ? 'profit-neon' : isLoss ? 'loss-neon' : 'neutral'}
            size="sm"
            className="font-bold"
          >
            {summary.result}
          </Badge>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-slate-300">
          <Scale className="w-3.5 h-3.5 text-amber-400" />
          <span>Realized R:R: <strong className="text-white">{rrRatio}</strong></span>
        </div>
      </div>

      {/* Financial Metrics Cards Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Gross PnL */}
        <div className="p-3 rounded-lg bg-surface/40 border border-border/40 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Gross PnL</span>
            <DollarSign className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div
            className={cn(
              'text-base font-bold',
              summary.gross_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
            )}
          >
            {summary.gross_pnl > 0 && '+'}
            {formatUSDT(summary.gross_pnl)}
          </div>
        </div>

        {/* Total Commission */}
        <div className="p-3 rounded-lg bg-surface/40 border border-border/40 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Commissions</span>
            <DollarSign className="w-3.5 h-3.5 text-rose-400" />
          </div>
          <div className="text-base font-bold text-rose-300">
            {formatUSDT(summary.commission)}
          </div>
        </div>

        {/* Net Realized PnL */}
        <div className="p-3 rounded-lg bg-surface/40 border border-border/40 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Net Realized PnL</span>
            {isProfit ? (
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
            )}
          </div>
          <div
            className={cn(
              'text-base font-bold',
              isProfit ? 'text-emerald-400' : 'text-rose-400'
            )}
          >
            {summary.net_pnl > 0 && '+'}
            {formatUSDT(summary.net_pnl)}
          </div>
        </div>

        {/* Realized ROI % */}
        <div className="p-3 rounded-lg bg-surface/40 border border-border/40 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>ROI %</span>
            <Percent className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <div
            className={cn(
              'text-base font-bold',
              isProfit ? 'text-emerald-400' : 'text-rose-400'
            )}
          >
            {formatPercent(summary.roi, true)}
          </div>
        </div>
      </div>
    </div>
  );
}
