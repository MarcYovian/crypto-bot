import { TradeDetailDTO } from '@/types/trades';
import { formatUSDT } from '@/utils/format';
import { ShieldCheck, Target, DollarSign, Scale } from 'lucide-react';

export interface RiskParametersTabProps {
  trade: TradeDetailDTO;
}

export function RiskParametersTab({ trade }: RiskParametersTabProps) {
  const risk = trade.risk_details;

  if (!risk) {
    return (
      <div className="py-8 text-center text-xs text-slate-500 font-mono">
        No formal risk allocation parameters recorded for this trade.
      </div>
    );
  }

  return (
    <div className="space-y-4 text-xs font-mono">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Risk Allocation */}
        <div className="p-3.5 rounded-lg bg-surface/60 border border-border/60 space-y-1.5">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Max Risk Budget</span>
            <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-base font-bold text-white">
            {formatUSDT(risk.risk_amount_usdt)}
          </div>
          <div className="text-[10px] text-slate-500">
            Calculated from account equity risk %
          </div>
        </div>

        {/* Stop Distance */}
        <div className="p-3.5 rounded-lg bg-surface/60 border border-border/60 space-y-1.5">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Stop Distance</span>
            <Target className="w-3.5 h-3.5 text-sky-400" />
          </div>
          <div className="text-base font-bold text-white">
            {formatUSDT(risk.stop_distance)}
          </div>
          <div className="text-[10px] text-slate-500">
            |Entry - SL| Price delta
          </div>
        </div>

        {/* Required Margin */}
        <div className="p-3.5 rounded-lg bg-surface/60 border border-border/60 space-y-1.5">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Committed Margin</span>
            <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-base font-bold text-white">
            {formatUSDT(risk.required_margin)}
          </div>
          <div className="text-[10px] text-slate-500">
            Notional / Leverage ({trade.leverage}x)
          </div>
        </div>
      </div>

      {/* Safety Guard Note */}
      <div className="p-3 rounded-lg bg-surface/30 border border-border/40 text-[11px] text-slate-400 space-y-1">
        <div className="flex items-center gap-1.5 text-slate-200 font-semibold">
          <Scale className="w-3.5 h-3.5 text-brand-400" />
          <span>Institutional Sizing Formula</span>
        </div>
        <p className="leading-relaxed">
          Position quantity was determined via <code className="text-brand-300">PositionSize = RiskBudget / StopDistance</code>. Leverage is set to {trade.leverage}x Isolated to strictly isolate margin exposure.
        </p>
      </div>
    </div>
  );
}
