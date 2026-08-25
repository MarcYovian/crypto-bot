import { useState } from 'react';
import { usePanicCloseMutation } from '@/hooks/useBotOperations';
import { PanicCloseResponseDTO } from '@/types/bot';
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
} from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { ShieldAlert, AlertTriangle, Flame } from 'lucide-react';

export interface PanicCloseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (recap: PanicCloseResponseDTO) => void;
}

export function PanicCloseModal({
  isOpen,
  onClose,
  onSuccess,
}: PanicCloseModalProps) {
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const panicMutation = usePanicCloseMutation();

  const handleExecutePanic = async () => {
    if (!isConfirmed || panicMutation.isPending) return;

    setErrorMsg(null);
    try {
      const res = await panicMutation.mutateAsync(true);
      setIsConfirmed(false);
      onClose();
      onSuccess(res);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Failed to execute emergency panic close.');
      }
    }
  };

  const handleModalClose = () => {
    setIsConfirmed(false);
    setErrorMsg(null);
    onClose();
  };

  return (
    <Modal open={isOpen} onOpenChange={handleModalClose}>
      <ModalContent className="max-w-md bg-surface/95 border-rose-600/70 text-slate-100 font-mono text-xs shadow-glow-loss">
        <ModalHeader className="pb-3 border-b border-border/50 pr-8">
          <div className="flex items-center gap-2 text-rose-400">
            <Flame className="w-5 h-5 animate-pulse" />
            <ModalTitle className="text-base font-bold text-white tracking-tight">
              EMERGENCY PANIC CLOSE ALL
            </ModalTitle>
          </div>
          <ModalDescription className="text-xs text-rose-300/90 mt-1">
            2-Step Authorization Required • High Impact Market Action
          </ModalDescription>
        </ModalHeader>

        <div className="space-y-4 pt-2">
          {/* Critical Warning Callout */}
          <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-600/60 space-y-2 text-rose-200">
            <div className="flex items-center gap-2 font-bold text-xs">
              <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
              <span>PERINGATAN AKSI DARURAT PASAR:</span>
            </div>
            <p className="text-[11px] leading-relaxed text-rose-200/90">
              Aksi ini akan menutup <strong>SELURUH posisi terbuka di pasar secara instan</strong> (Market Order) dan <strong>membatalkan SEMUA limit/TP/SL order</strong> yang aktif di exchange Binance Futures.
            </p>
          </div>

          {/* Error notification */}
          {errorMsg && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-rose-950/80 border border-rose-600 text-rose-300 text-xs">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Mandatory Checkbox Step */}
          <label className="flex items-start gap-2.5 p-3 rounded-lg bg-surface/80 border border-border/80 cursor-pointer hover:border-slate-500 transition-colors select-none">
            <input
              type="checkbox"
              checked={isConfirmed}
              onChange={(e) => setIsConfirmed(e.target.checked)}
              className="mt-0.5 w-4 h-4 rounded bg-slate-800 border-slate-600 text-rose-500 focus:ring-rose-400 cursor-pointer"
            />
            <span className="text-xs text-slate-200 font-medium leading-tight">
              Saya mengerti aksi darurat ini akan menutup semua posisi market dan membatalkan seluruh order.
            </span>
          </label>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="md"
              onClick={handleModalClose}
              disabled={panicMutation.isPending}
            >
              Cancel
            </Button>

            <Button
              type="button"
              variant="danger"
              size="md"
              onClick={handleExecutePanic}
              disabled={!isConfirmed || panicMutation.isPending}
              isLoading={panicMutation.isPending}
              className="gap-1.5 shadow-glow-loss font-bold"
            >
              {!panicMutation.isPending && <Flame className="w-4 h-4" />}
              EXECUTE PANIC CLOSE
            </Button>
          </div>
        </div>
      </ModalContent>
    </Modal>
  );
}
