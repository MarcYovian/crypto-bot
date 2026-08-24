import { formatUSDT } from '@/utils/format';
import { ShieldCheck, AlertTriangle } from 'lucide-react';

export interface LiquidationVisualizerProps {
  side: 'BUY' | 'SELL';
  entryPrice: number;
  slPrice: number;
  liqPrice: number;
}

export function LiquidationVisualizer({
  side,
  entryPrice,
  slPrice,
  liqPrice,
}: LiquidationVisualizerProps) {
  const isBuy = side === 'BUY';

  // For BUY: Liquidation < SL < Entry (Safe if liq is below SL)
  // For SELL: Liquidation > SL > Entry (Safe if liq is above SL)
  const isLiqSafe = isBuy ? liqPrice < slPrice : liqPrice > slPrice;
  const bufferUSDT = isBuy ? slPrice - liqPrice : liqPrice - slPrice;
  const bufferPercent = entryPrice > 0 ? (bufferUSDT / entryPrice) * 100 : 0;

  return (
    <div className="p-4 rounded-xl bg-surface/50 border border-border/60 space-y-3 font-mono text-xs">
      <div className="flex items-center justify-between">
        <span className="font-bold text-slate-300 flex items-center gap-1.5">
          {isLiqSafe ? (
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          ) : (
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          )}
          Liquidation & Stop Loss Protection Buffer
        </span>
        <span
          className={`text-[11px] font-bold ${
            isLiqSafe ? 'text-emerald-400' : 'text-amber-400'
          }`}
        >
          {isLiqSafe
            ? `+${bufferPercent.toFixed(1)}% Safe Buffer (${formatUSDT(bufferUSDT)})`
            : 'Warning: Liquidation Too Close'}
        </span>
      </div>

      {/* Visual Level Nodes */}
      <div className="grid grid-cols-3 gap-2 text-center pt-1">
        {/* Node 1: Entry */}
        <div className="p-2.5 rounded-lg bg-surface/80 border border-sky-500/30">
          <span className="text-[10px] text-sky-400 font-semibold block uppercase">
            1. Entry Price
          </span>
          <span className="font-bold text-white text-xs block mt-0.5">
            {formatUSDT(entryPrice)}
          </span>
        </div>

        {/* Node 2: Stop Loss */}
        <div className="p-2.5 rounded-lg bg-surface/80 border border-rose-500/30">
          <span className="text-[10px] text-rose-400 font-semibold block uppercase">
            2. Stop Loss (Risk)
          </span>
          <span className="font-bold text-rose-300 text-xs block mt-0.5">
            {formatUSDT(slPrice)}
          </span>
        </div>

        {/* Node 3: Liquidation */}
        <div
          className={`p-2.5 rounded-lg bg-surface/80 border ${
            isLiqSafe ? 'border-amber-500/30' : 'border-rose-600/50'
          }`}
        >
          <span className="text-[10px] text-amber-400 font-semibold block uppercase">
            3. Estimated Liq
          </span>
          <span className="font-bold text-amber-300 text-xs block mt-0.5">
            {formatUSDT(liqPrice)}
          </span>
        </div>
      </div>

      {/* Helper explanation */}
      <p className="text-[10px] text-slate-500 text-center">
        {isBuy
          ? 'Isolated Margin: Stop Loss is triggered before reaching liquidation point.'
          : 'Isolated Margin: Stop Loss protects against short squeezes before liquidation.'}
      </p>
    </div>
  );
}
