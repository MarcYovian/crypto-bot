import { useEffect, useRef, useState } from 'react';
import { ActiveTradeDTO } from '@/types/trades';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { TPMilestoneBar } from './TPMilestoneBar';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { formatUSDT, formatCrypto, formatPercent } from '@/utils/format';
import { cn } from '@/utils/cn';
import { ShieldCheck, XCircle } from 'lucide-react';

export interface ActiveTradeRowProps {
  trade: ActiveTradeDTO;
  onCloseClick: (trade: ActiveTradeDTO) => void;
}

export function ActiveTradeRow({ trade, onCloseClick }: ActiveTradeRowProps) {
  const isBuy = trade.side === 'BUY';
  const isProfit = trade.unrealized_pnl >= 0;

  // Price Flash Micro-Animation
  const prevPriceRef = useRef<number | null>(trade.current_price);
  const [flashClass, setFlashClass] = useState<string>('');

  useEffect(() => {
    if (
      prevPriceRef.current !== null &&
      trade.current_price !== null &&
      trade.current_price !== prevPriceRef.current
    ) {
      if (trade.current_price > prevPriceRef.current) {
        setFlashClass('bg-emerald-500/20 text-emerald-300 font-bold');
      } else {
        setFlashClass('bg-rose-500/20 text-rose-300 font-bold');
      }

      const timer = setTimeout(() => {
        setFlashClass('');
      }, 150);

      prevPriceRef.current = trade.current_price;
      return () => clearTimeout(timer);
    }
    prevPriceRef.current = trade.current_price;
  }, [trade.current_price]);

  // Determine if BEP SL is active (TP1 hit or SL moved to entry)
  const isTP1Hit = trade.tp_levels?.some((tp) => tp.level === 1 && tp.is_hit);
  const isBEP =
    isTP1Hit ||
    (trade.sl_price !== null &&
      trade.entry_price !== null &&
      (isBuy
        ? trade.sl_price >= trade.entry_price
        : trade.sl_price <= trade.entry_price));

  return (
    <tr className="border-b border-border/40 hover:bg-surface/50 transition-colors font-mono text-xs">
      {/* 1. Symbol & Direction */}
      <td className="p-3.5 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <span className="font-bold text-white tracking-wide">
            {trade.symbol}
          </span>
          <Badge variant={isBuy ? 'profit' : 'loss'} size="sm">
            {trade.side}
          </Badge>
          <span className="text-[10px] text-slate-400 font-normal">
            {trade.leverage}x
          </span>
        </div>
        <div className="text-[10px] text-slate-500 mt-0.5">
          ID: #{trade.trade_id} • {trade.margin_mode}
        </div>
      </td>

      {/* 2. Position Size */}
      <td className="p-3.5 whitespace-nowrap text-slate-300">
        <div className="font-semibold text-white">
          {formatCrypto(trade.remaining_qty, 4)}
        </div>
        <div className="text-[10px] text-slate-500">
          Orig: {formatCrypto(trade.position_size, 4)}
        </div>
      </td>

      {/* 3. Entry Price */}
      <td className="p-3.5 whitespace-nowrap text-slate-300">
        {formatUSDT(trade.entry_price)}
      </td>

      {/* 4. Current Mark Price with Flash Animation */}
      <td className="p-3.5 whitespace-nowrap">
        <span
          className={cn(
            'px-1.5 py-0.5 rounded transition-colors duration-150',
            flashClass || 'text-slate-100'
          )}
        >
          {formatUSDT(trade.current_price)}
        </span>
      </td>

      {/* 5. Stop Loss & BEP indicator */}
      <td className="p-3.5 whitespace-nowrap">
        <div className="flex items-center gap-1.5">
          <span className="text-slate-300">
            {formatUSDT(trade.sl_price)}
          </span>
          {isBEP && (
            <Badge
              variant="profit"
              size="sm"
              className="text-[9px] px-1 py-0 gap-0.5"
            >
              <ShieldCheck className="w-2.5 h-2.5" />
              BEP
            </Badge>
          )}
        </div>
      </td>

      {/* 6. TP Milestones */}
      <td className="p-3.5 whitespace-nowrap">
        <TPMilestoneBar tpLevels={trade.tp_levels} />
      </td>

      {/* 7. Unrealized Floating PnL */}
      <td className="p-3.5 whitespace-nowrap">
        <div
          className={cn(
            'font-bold text-sm',
            isProfit ? 'text-emerald-400' : 'text-rose-400'
          )}
        >
          {isProfit ? '+' : ''}
          {formatUSDT(trade.unrealized_pnl)}
        </div>
        <div
          className={cn(
            'text-[10px] font-medium',
            isProfit ? 'text-emerald-500' : 'text-rose-500'
          )}
        >
          {formatPercent(trade.unrealized_pnl_percent, true)}
        </div>
      </td>

      {/* 8. Action Buttons */}
      <td className="p-3.5 whitespace-nowrap text-right">
        <RoleGuard requiredRole="ADMIN" mode="disable">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onCloseClick(trade)}
            className="text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 gap-1 text-xs"
          >
            <XCircle className="w-3.5 h-3.5" />
            Close
          </Button>
        </RoleGuard>
      </td>
    </tr>
  );
}
