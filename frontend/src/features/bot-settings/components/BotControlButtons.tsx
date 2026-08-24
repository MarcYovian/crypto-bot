import { useState } from 'react';
import {
  usePauseBotMutation,
  useResumeBotMutation,
} from '@/hooks/useBotOperations';
import { BotStatusDTO, PanicCloseResponseDTO } from '@/types/bot';
import { PanicCloseModal } from './PanicCloseModal';
import { PanicRecapDialog } from './PanicRecapDialog';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { Button } from '@/components/ui/button';
import { Pause, Play, Flame, AlertCircle, CheckCircle2 } from 'lucide-react';

export interface BotControlButtonsProps {
  status?: BotStatusDTO | null;
}

export function BotControlButtons({ status }: BotControlButtonsProps) {
  const [isPanicModalOpen, setIsPanicModalOpen] = useState(false);
  const [recapData, setRecapData] = useState<PanicCloseResponseDTO | null>(null);
  const [feedbackMsg, setFeedbackMsg] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  const pauseMutation = usePauseBotMutation();
  const resumeMutation = useResumeBotMutation();

  const isPaused = status?.is_paused ?? false;

  const handlePause = async () => {
    try {
      const res = await pauseMutation.mutateAsync();
      setFeedbackMsg({ type: 'success', text: res.message || 'Bot trading engine paused.' });
      setTimeout(() => setFeedbackMsg(null), 5000);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setFeedbackMsg({ type: 'error', text: err.message });
      } else {
        setFeedbackMsg({ type: 'error', text: 'Failed to pause bot engine.' });
      }
      setTimeout(() => setFeedbackMsg(null), 5000);
    }
  };

  const handleResume = async () => {
    try {
      const res = await resumeMutation.mutateAsync();
      setFeedbackMsg({ type: 'success', text: res.message || 'Bot trading engine resumed.' });
      setTimeout(() => setFeedbackMsg(null), 5000);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setFeedbackMsg({ type: 'error', text: err.message });
      } else {
        setFeedbackMsg({ type: 'error', text: 'Failed to resume bot engine.' });
      }
      setTimeout(() => setFeedbackMsg(null), 5000);
    }
  };

  return (
    <div className="space-y-3 font-mono text-xs">
      {/* Action Buttons Grid */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-4 rounded-xl bg-surface/60 border border-border/60">
        <div>
          <h3 className="font-bold text-white text-sm tracking-tight">
            Engine Operation Controls
          </h3>
          <p className="text-slate-400 text-xs mt-0.5">
            Manage trading state and trigger emergency liquidation
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Pause / Resume Toggle */}
          <RoleGuard requiredRole="ADMIN" mode="disable">
            {isPaused ? (
              <Button
                type="button"
                variant="primary"
                size="md"
                onClick={handleResume}
                isLoading={resumeMutation.isPending}
                disabled={resumeMutation.isPending}
                className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white shadow-glow-profit"
              >
                {!resumeMutation.isPending && <Play className="w-4 h-4" />}
                Resume Engine
              </Button>
            ) : (
              <Button
                type="button"
                variant="warning"
                size="md"
                onClick={handlePause}
                isLoading={pauseMutation.isPending}
                disabled={pauseMutation.isPending}
                className="gap-1.5"
              >
                {!pauseMutation.isPending && <Pause className="w-4 h-4" />}
                Pause Engine
              </Button>
            )}
          </RoleGuard>

          {/* Giant Danger Button: Panic Close All */}
          <RoleGuard requiredRole="ADMIN" mode="disable">
            <Button
              type="button"
              variant="danger"
              size="md"
              onClick={() => setIsPanicModalOpen(true)}
              className="gap-1.5 shadow-glow-loss font-bold border-rose-500/50"
            >
              <Flame className="w-4 h-4 text-rose-300 animate-pulse" />
              PANIC CLOSE ALL
            </Button>
          </RoleGuard>
        </div>
      </div>

      {/* Feedback Alert Toast */}
      {feedbackMsg && (
        <div
          className={`flex items-center gap-2 p-3 rounded-lg border text-xs animate-in fade-in-0 ${
            feedbackMsg.type === 'success'
              ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
              : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
          }`}
        >
          {feedbackMsg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          )}
          <span>{feedbackMsg.text}</span>
        </div>
      )}

      {/* 2-Step Panic Close Modal */}
      <PanicCloseModal
        isOpen={isPanicModalOpen}
        onClose={() => setIsPanicModalOpen(false)}
        onSuccess={(recap) => setRecapData(recap)}
      />

      {/* Execution Recap Dialog */}
      <PanicRecapDialog
        isOpen={recapData !== null}
        onClose={() => setRecapData(null)}
        recap={recapData}
      />
    </div>
  );
}
