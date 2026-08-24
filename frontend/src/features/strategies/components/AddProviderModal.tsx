import { useState } from 'react';
import { useCreateProviderMutation } from '@/hooks/useProviders';
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
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Radio, AlertCircle, Plus } from 'lucide-react';

export interface AddProviderModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AddProviderModal({ isOpen, onClose }: AddProviderModalProps) {
  const [name, setName] = useState('');
  const [channelId, setChannelId] = useState('');
  const [confidenceWeight, setConfidenceWeight] = useState<number>(1.0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const createMutation = useCreateProviderMutation();

  const isFormValid =
    name.trim().length >= 2 &&
    channelId.trim().length >= 1 &&
    confidenceWeight >= 0.1 &&
    confidenceWeight <= 2.0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid || createMutation.isPending) return;

    setErrorMsg(null);
    try {
      await createMutation.mutateAsync({
        name: name.trim(),
        channel_id: channelId.trim(),
        confidence_weight: Number(confidenceWeight),
      });
      // Reset and close
      setName('');
      setChannelId('');
      setConfidenceWeight(1.0);
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        if (err.message.includes('409') || err.message.toLowerCase().includes('duplicate') || err.message.toLowerCase().includes('already exists')) {
          setErrorMsg('Channel ID or Provider name is already registered in the system.');
        } else {
          setErrorMsg(err.message);
        }
      } else {
        setErrorMsg('Failed to register signal provider channel.');
      }
    }
  };

  return (
    <Modal open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <ModalContent className="max-w-md font-mono text-xs">
        <ModalHeader className="border-b border-border/50 pb-3 pr-8">
          <ModalTitle className="flex items-center gap-2 text-base text-white">
            <Radio className="w-4 h-4 text-brand-400" />
            Add Telegram Signal Channel
          </ModalTitle>
          <ModalDescription className="text-xs text-slate-400">
            Register a Telegram channel ID and configure its AI confidence weighting
          </ModalDescription>
        </ModalHeader>

        <form onSubmit={handleSubmit} className="py-3 space-y-4">
          {errorMsg && (
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-rose-950/30 border border-rose-800/40 text-rose-300 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Channel Name */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium block">
              Channel / Provider Name
            </label>
            <Input
              type="text"
              placeholder="e.g. SMC Alpha VIP Signals"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-9 bg-surface/60 border-border/80"
              required
            />
          </div>

          {/* Telegram Channel ID */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium block">
              Telegram Chat / Channel ID
            </label>
            <Input
              type="text"
              placeholder="e.g. -1001987654321"
              value={channelId}
              onChange={(e) => setChannelId(e.target.value)}
              className="h-9 bg-surface/60 border-border/80"
              required
            />
            <p className="text-[10px] text-slate-500">
              Numeric Telegram channel identifier (typically starting with -100)
            </p>
          </div>

          {/* Confidence Weighting Multiplier */}
          <div className="space-y-2 p-3 rounded-lg bg-surface/40 border border-border/50">
            <div className="flex items-center justify-between">
              <label className="text-slate-300 font-medium">
                Confidence Multiplier
              </label>
              <Badge variant="profit" size="sm" className="font-bold">
                {confidenceWeight.toFixed(2)}x
              </Badge>
            </div>

            <input
              type="range"
              min="0.1"
              max="2.0"
              step="0.05"
              value={confidenceWeight}
              onChange={(e) => setConfidenceWeight(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-brand-500"
            />

            <div className="flex justify-between text-[10px] text-slate-500">
              <span>0.1x (Low weight)</span>
              <span>1.0x (Standard)</span>
              <span>2.0x (Max boost)</span>
            </div>
          </div>

          <ModalFooter className="border-t border-border/50 pt-3">
            <ModalClose asChild>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={createMutation.isPending}
              >
                Cancel
              </Button>
            </ModalClose>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={!isFormValid || createMutation.isPending}
              isLoading={createMutation.isPending}
              className="gap-1.5 shadow-glow-brand"
            >
              {!createMutation.isPending && <Plus className="w-3.5 h-3.5" />}
              Register Provider
            </Button>
          </ModalFooter>
        </form>
      </ModalContent>
    </Modal>
  );
}
