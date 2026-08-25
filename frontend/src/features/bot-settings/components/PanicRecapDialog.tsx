import { PanicCloseResponseDTO } from '@/types/bot';
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
} from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { formatDateTime } from '@/utils/format';
import { ShieldCheck, CheckCircle2, ZapOff, Trash2 } from 'lucide-react';

export interface PanicRecapDialogProps {
  isOpen: boolean;
  onClose: () => void;
  recap: PanicCloseResponseDTO | null;
}

export function PanicRecapDialog({
  isOpen,
  onClose,
  recap,
}: PanicRecapDialogProps) {
  if (!recap) return null;

  return (
    <Modal open={isOpen} onOpenChange={onClose}>
      <ModalContent className="max-w-md bg-surface/95 border-emerald-500/40 text-slate-100 font-mono text-xs shadow-glow-profit">
        <ModalHeader className="pb-3 border-b border-border/50 pr-8">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <ModalTitle className="text-base font-bold text-white tracking-tight">
              Emergency Panic Close Executed
            </ModalTitle>
          </div>
          <ModalDescription className="text-xs text-slate-400 mt-1">
            All active positions have been market liquidated and orders revoked
          </ModalDescription>
        </ModalHeader>

        <div className="space-y-4 pt-2">
          {/* Execution Metric Cards */}
          <div className="grid grid-cols-2 gap-3">
            {/* Closed Positions */}
            <div className="p-3.5 rounded-xl bg-surface/80 border border-emerald-500/30 space-y-1 text-center">
              <ZapOff className="w-5 h-5 text-emerald-400 mx-auto" />
              <div className="text-2xl font-black text-white">
                {recap.closed_trades_count}
              </div>
              <span className="text-[11px] text-slate-400 font-semibold block">
                Positions Liquidated
              </span>
            </div>

            {/* Canceled Orders */}
            <div className="p-3.5 rounded-xl bg-surface/80 border border-indigo-500/30 space-y-1 text-center">
              <Trash2 className="w-5 h-5 text-indigo-400 mx-auto" />
              <div className="text-2xl font-black text-white">
                {recap.canceled_orders_count}
              </div>
              <span className="text-[11px] text-slate-400 font-semibold block">
                Orders Canceled
              </span>
            </div>
          </div>

          {/* Timestamp details */}
          <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-800/40 flex items-center justify-between text-[11px]">
            <span className="text-slate-400">Execution Timestamp:</span>
            <span className="text-emerald-300 font-bold">
              {formatDateTime(recap.timestamp)}
            </span>
          </div>

          {/* Dismiss button */}
          <div className="flex justify-end pt-2">
            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={onClose}
              className="gap-2 w-full shadow-glow-profit"
            >
              <CheckCircle2 className="w-4 h-4" />
              Acknowledge & Dismiss
            </Button>
          </div>
        </div>
      </ModalContent>
    </Modal>
  );
}
