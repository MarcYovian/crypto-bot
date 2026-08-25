import { TradeDetailDTO } from '@/types/trades';
import { formatUSDT, formatCrypto, formatDateTime } from '@/utils/format';
import { cn } from '@/utils/cn';

export interface ExecutionsTabProps {
  trade: TradeDetailDTO;
}

export function ExecutionsTab({ trade }: ExecutionsTabProps) {
  const executions = trade.executions || [];

  if (executions.length === 0) {
    return (
      <div className="py-8 text-center text-xs text-slate-500 font-mono">
        No execution fills recorded. Position may have been cancelled prior to entry fill.
      </div>
    );
  }

  return (
    <div className="space-y-3 font-mono text-xs">
      <div className="overflow-x-auto rounded-lg border border-border/40">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border/60 bg-surface/70 text-[11px] font-semibold text-slate-400 uppercase tracking-wider select-none">
              <th className="p-2.5">Fill Price</th>
              <th className="p-2.5">Executed Qty</th>
              <th className="p-2.5">Commission</th>
              <th className="p-2.5">Realized PnL</th>
              <th className="p-2.5 text-right">Executed At</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30 bg-surface/20">
            {executions.map((exec, idx) => {
              const isProfit = exec.realized_pnl >= 0;
              return (
                <tr key={idx} className="hover:bg-surface/50 transition-colors">
                  <td className="p-2.5 font-bold text-white whitespace-nowrap">
                    {formatUSDT(exec.price)}
                  </td>
                  <td className="p-2.5 text-slate-200 whitespace-nowrap">
                    {formatCrypto(exec.qty, 4)}
                  </td>
                  <td className="p-2.5 text-rose-300 whitespace-nowrap">
                    {formatUSDT(exec.commission)}
                  </td>
                  <td
                    className={cn(
                      'p-2.5 font-semibold whitespace-nowrap',
                      exec.realized_pnl !== 0
                        ? isProfit
                          ? 'text-emerald-400'
                          : 'text-rose-400'
                        : 'text-slate-400'
                    )}
                  >
                    {exec.realized_pnl !== 0 && (isProfit ? '+' : '')}
                    {formatUSDT(exec.realized_pnl)}
                  </td>
                  <td className="p-2.5 text-right text-slate-400 text-[10px] whitespace-nowrap">
                    {exec.executed_at ? formatDateTime(exec.executed_at) : '-'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
