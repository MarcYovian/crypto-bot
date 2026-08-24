import { Badge } from '@/components/ui/badge';
import { formatUSDT, formatPercent } from '@/utils/format';
import { ShieldCheck, ShieldAlert } from 'lucide-react';

export interface RiskCapIndicatorProps {
  riskAmount: number;
  maxRiskBudget: number;
  totalBalance: number;
}

export function RiskCapIndicator({
  riskAmount,
  maxRiskBudget,
  totalBalance,
}: RiskCapIndicatorProps) {
  const riskPct = totalBalance > 0 ? (riskAmount / totalBalance) * 100 : 0;
  const isSafe = riskAmount <= maxRiskBudget && riskPct <= 2.01; // tolerance for rounding

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="flex items-center justify-between">
        <span className="text-slate-400 text-[11px]">Risk Allocation Check:</span>
        <Badge
          variant={isSafe ? 'profit' : 'loss'}
          size="sm"
          className="gap-1 font-bold"
        >
          {isSafe ? (
            <>
              <ShieldCheck className="w-3 h-3 text-emerald-400" />
              SAFE ({formatPercent(riskPct, false)} $\le$ 2.0%)
            </>
          ) : (
            <>
              <ShieldAlert className="w-3 h-3 text-rose-400" />
              RISK CAP BREACH ({formatPercent(riskPct, false)} &gt; 2.0%)
            </>
          )}
        </Badge>
      </div>

      <div className="p-2.5 rounded-lg bg-surface/60 border border-border/60 flex items-center justify-between text-[11px]">
        <div>
          <span className="text-slate-500 block">Estimated Loss at SL:</span>
          <span
            className={isSafe ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}
          >
            {formatUSDT(riskAmount)}
          </span>
        </div>

        <div className="text-right">
          <span className="text-slate-500 block">Max 2.0% Cap:</span>
          <span className="text-slate-200 font-semibold">
            {formatUSDT(maxRiskBudget)}
          </span>
        </div>
      </div>

      {!isSafe && (
        <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-[11px] text-rose-300 flex items-start gap-2">
          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <span>
            <strong>Pelanggaran Risiko:</strong> Alokasi kerugian ({formatUSDT(riskAmount)}) melebihi batas toleransi institusional 2.0% ({formatUSDT(maxRiskBudget)}). Tombol eksekusi dikunci.
          </span>
        </div>
      )}
    </div>
  );
}
