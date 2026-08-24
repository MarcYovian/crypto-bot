import { useState } from 'react';
import { ActiveTradeDTO } from '@/types/trades';
import { useCloseTradeMutation } from '@/hooks/useActiveTrades';
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
  ModalFooter,
  ModalClose,
} from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatUSDT, formatCrypto, formatPercent } from '@/utils/format';
import { ShieldAlert, AlertCircle } from 'lucide-react';

export interface ManualCloseModalProps {
  trade: ActiveTradeDTO | null;
  isOpen: boolean;
  onClose: () => void;
}

export function ManualCloseModal({
  trade,
  isOpen,
  onClose,
}: ManualCloseModalProps) {
  const [error, setError] = useState<string | null>(null);
  const closeMutation = useCloseTradeMutation();

  if (!trade) return null;

  const isBuy = trade.side === 'BUY';
  const isProfit = trade.unrealized_pnl >= 0;

  const handleConfirmClose = async () => {
    setError(null);
    try {
      await closeMutation.mutateAsync({
        tradeId: trade.trade_id,
        reason: 'UI_MANUAL_CLOSE',
      });
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to close position. Please try again.');
      }
    }
  };

  return (
    <Modal open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <ModalContent className="max-w-md">
        <ModalHeader>
          <ModalTitle className="text-rose-400 flex items-center gap-2 text-lg">
            <ShieldAlert className="w-5 h-5 text-rose-400" />
            Manual Market Close Position
          </ModalTitle>
          <ModalDescription className="text-xs text-slate-400">
            Emergency market close will immediately liquidate the open position at market price.
          </ModalDescription>
        </ModalHeader>

        <div className="space-y-4 py-2 text-xs">
          {error && (
            <div
              role="alert"
              className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 text-xs text-rose-300 flex items-center gap-2"
            >
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Position Details Snapshot */}
          <div className="p-3.5 rounded-lg bg-surface/70 border border-border/70 space-y-2.5 font-mono">
            <div className="flex items-center justify-between pb-2 border-b border-border/50">
              <span className="text-sm font-bold text-white flex items-center gap-2">
                {trade.symbol}
                <Badge variant={isBuy ? 'profit' : 'loss'} size="sm">
                  {trade.side} {trade.leverage}x
                </Badge>
              </span>
              <Badge variant="neutral" size="sm">
                ID: #{trade.trade_id}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <span className="text-slate-400 block">Remaining Qty:</span>
                <span className="text-white font-semibold">
                  {formatCrypto(trade.remaining_qty, 4)}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block">Entry Price:</span>
                <span className="text-slate-200">
                  {formatUSDT(trade.entry_price)}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block">Current Mark:</span>
                <span className="text-slate-200">
                  {formatUSDT(trade.current_price)}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block">Est. Floating PnL:</span>
                <span
                  className={
                    isProfit
                      ? 'text-emerald-400 font-bold'
                      : 'text-rose-400 font-bold'
                  }
                >
                  {isProfit ? '+' : ''}
                  {formatUSDT(trade.unrealized_pnl)} ({formatPercent(trade.unrealized_pnl_percent, true)})
                </span>
              </div>
            </div>
          </div>

          <div className="bg-rose-950/20 border border-rose-800/40 p-3 rounded-lg text-rose-300 text-[11px] leading-relaxed">
            ⚠️ <strong>Perhatian:</strong> Order MARKET akan dikirimkan langsung ke exchange. Semua sisa take profit dan pending stop loss terkait trade #{trade.trade_id} akan otomatis dibatalkan.
          </div>
        </div>

        <ModalFooter>
          <ModalClose asChild>
            <Button
              variant="secondary"
              size="sm"
              disabled={closeMutation.isPending}
            >
              Cancel
            </Button>
          </ModalClose>
          <Button
            variant="danger"
            size="sm"
            onClick={handleConfirmClose}
            isLoading={closeMutation.isPending}
            className="shadow-glow-loss"
          >
            Confirm Market Close
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
