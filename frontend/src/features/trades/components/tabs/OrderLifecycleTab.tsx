import { TradeDetailDTO } from '@/types/trades';
import { Badge } from '@/components/ui/badge';
import { formatUSDT, formatCrypto } from '@/utils/format';

export interface OrderLifecycleTabProps {
  trade: TradeDetailDTO;
}

export function OrderLifecycleTab({ trade }: OrderLifecycleTabProps) {
  const orders = trade.orders || [];

  if (orders.length === 0) {
    return (
      <div className="py-8 text-center text-xs text-slate-500 font-mono">
        No exchange order records found for this trade.
      </div>
    );
  }

  return (
    <div className="space-y-3 font-mono text-xs">
      <div className="overflow-x-auto rounded-lg border border-border/40">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border/60 bg-surface/70 text-[11px] font-semibold text-slate-400 uppercase tracking-wider select-none">
              <th className="p-2.5">Purpose</th>
              <th className="p-2.5">Type</th>
              <th className="p-2.5">Side</th>
              <th className="p-2.5">Price</th>
              <th className="p-2.5">Qty</th>
              <th className="p-2.5">Status</th>
              <th className="p-2.5 text-right">Exchange ID</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30 bg-surface/20">
            {orders.map((ord) => {
              const isFilled = ord.status === 'FILLED';
              const isCanceled = ord.status === 'CANCELED' || ord.status === 'EXPIRED';

              return (
                <tr key={ord.id} className="hover:bg-surface/50 transition-colors">
                  <td className="p-2.5 font-bold text-white whitespace-nowrap">
                    {ord.purpose}
                  </td>
                  <td className="p-2.5 text-slate-300 whitespace-nowrap">
                    {ord.order_type}
                  </td>
                  <td className="p-2.5 whitespace-nowrap">
                    <Badge
                      variant={ord.side === 'BUY' ? 'profit' : 'loss'}
                      size="sm"
                      className="text-[9px]"
                    >
                      {ord.side}
                    </Badge>
                  </td>
                  <td className="p-2.5 text-slate-200 whitespace-nowrap">
                    {ord.price ? formatUSDT(ord.price) : 'MARKET'}
                  </td>
                  <td className="p-2.5 text-slate-300 whitespace-nowrap">
                    {formatCrypto(ord.qty, 4)}
                  </td>
                  <td className="p-2.5 whitespace-nowrap">
                    <Badge
                      variant={
                        isFilled
                          ? 'profit-neon'
                          : isCanceled
                          ? 'neutral'
                          : 'info'
                      }
                      size="sm"
                      className="text-[9px]"
                    >
                      {ord.status}
                    </Badge>
                  </td>
                  <td className="p-2.5 text-right text-slate-400 text-[10px] whitespace-nowrap">
                    {ord.exchange_order_id ? `#${ord.exchange_order_id}` : '-'}
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
