import { useState } from 'react';
import { SignalQueryParams } from '@/types/signals';
import { useSignalsFeed } from '@/hooks/useSignals';
import { useQuery } from '@tanstack/react-query';
import { getAnalyticsSummaryApi } from '@/api/endpoints/analytics';
import { SignalFeedList } from './components/SignalFeedList';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Radio, AlertCircle, RefreshCw } from 'lucide-react';

export function SignalsFeedPage() {
  const [filters, setFilters] = useState<SignalQueryParams>({
    account_id: 1,
    page: 1,
    page_size: 20,
  });

  const { data: signalsData, isLoading, isError, refetch } = useSignalsFeed(filters);

  // Get active account balance for precision risk sizing
  const { data: analytics } = useQuery({
    queryKey: ['analytics', 'summary'],
    queryFn: () => getAnalyticsSummaryApi(1),
    staleTime: 10000,
  });

  const accountBalance = analytics?.total_balance_usdt || 10000.0;

  const handleFilterChange = (newFilters: Partial<SignalQueryParams>) => {
    setFilters((prev) => ({ ...prev, ...newFilters }));
  };

  return (
    <Card className="glass-card w-full">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-brand-400 animate-pulse" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              Live Telegram Signal Feed
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Real-time SMC trading setups from Telegram channels with 1-click risk-guarded execution
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent className="pt-4">
        {isError ? (
          <div className="p-8 rounded-xl bg-rose-950/20 border border-rose-800/40 text-center space-y-4 max-w-lg mx-auto">
            <div className="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 mx-auto flex items-center justify-center">
              <AlertCircle className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                Failed to Load Signal Feed
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Could not fetch Telegram signals from the trading engine API.
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
        ) : (
          <SignalFeedList
            data={signalsData}
            isLoading={isLoading}
            filters={filters}
            onFilterChange={handleFilterChange}
            accountBalance={accountBalance}
          />
        )}
      </CardContent>
    </Card>
  );
}
