import { useActiveTrades } from '@/hooks/useActiveTrades';
import { ActiveTradesTable } from './components/ActiveTradesTable';
import { Button } from '@/components/ui/button';
import { AlertCircle, RefreshCw } from 'lucide-react';

export function ActiveTradesPage() {
  const {
    data: trades,
    isLoading,
    isError,
    refetch,
  } = useActiveTrades(1);

  if (isError) {
    return (
      <div className="p-8 rounded-xl bg-rose-950/20 border border-rose-800/40 text-center space-y-4 max-w-lg mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 mx-auto flex items-center justify-center">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-base font-bold text-white">
            Failed to Load Active Positions
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Could not fetch live position data from the trading engine API.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => refetch()}
          className="gap-2 mx-auto"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Retry Fetch
        </Button>
      </div>
    );
  }

  return (
    <div className="w-full">
      <ActiveTradesTable trades={trades || []} isLoading={isLoading} />
    </div>
  );
}
