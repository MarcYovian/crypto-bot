import { useState } from 'react';
import { useSyncInstrumentsMutation } from '@/hooks/useWatchlist';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { Button } from '@/components/ui/button';
import { RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';

export function InstrumentSyncButton() {
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const syncMutation = useSyncInstrumentsMutation();

  const handleSync = async () => {
    setSyncFeedback(null);
    setSyncError(null);
    try {
      const result = await syncMutation.mutateAsync();
      setSyncFeedback(
        `Successfully synced ${result.synced_instruments} instruments and ${result.synced_brackets} leverage brackets from Binance.`
      );
      setTimeout(() => setSyncFeedback(null), 5000);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setSyncError(err.message);
      } else {
        setSyncError('Failed to synchronize instruments from Binance.');
      }
      setTimeout(() => setSyncError(null), 6000);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1.5 font-mono text-xs">
      <RoleGuard requiredRole="ADMIN" mode="disable">
        <Button
          variant="outline"
          size="sm"
          onClick={handleSync}
          disabled={syncMutation.isPending}
          isLoading={syncMutation.isPending}
          className="gap-2 text-xs border-brand-500/40 text-brand-400 hover:text-white hover:bg-brand-500/20"
        >
          {!syncMutation.isPending && <RefreshCw className="w-3.5 h-3.5" />}
          Sync from Binance
        </Button>
      </RoleGuard>

      {/* Sync Success Feedback */}
      {syncFeedback && (
        <div className="flex items-center gap-1.5 text-[11px] text-emerald-400 animate-in fade-in-0 duration-200">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>{syncFeedback}</span>
        </div>
      )}

      {/* Sync Error Feedback */}
      {syncError && (
        <div className="flex items-center gap-1.5 text-[11px] text-rose-400 animate-in fade-in-0 duration-200">
          <AlertCircle className="w-3.5 h-3.5" />
          <span>{syncError}</span>
        </div>
      )}
    </div>
  );
}
