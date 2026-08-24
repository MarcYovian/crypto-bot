import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAnalyticsSummaryApi, getEquityCurveApi } from '@/api/endpoints/analytics';
import { TimeframeOption } from '@/types/analytics';
import { SummaryKPICards } from './components/SummaryKPICards';
import { EquityCurveChart } from './components/EquityCurveChart';
import { DashboardSkeleton } from './components/DashboardSkeleton';
import { Button } from '@/components/ui/button';
import { AlertCircle, RefreshCw } from 'lucide-react';

export function DashboardOverviewPage() {
  const [timeframe, setTimeframe] = useState<TimeframeOption>('30d');

  const {
    data: summary,
    isLoading: isSummaryLoading,
    isError: isSummaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['analytics', 'summary'],
    queryFn: () => getAnalyticsSummaryApi(1),
    refetchInterval: 10000, // 10s background sync
    staleTime: 5000,
  });

  const {
    data: equityPoints,
    isLoading: isEquityLoading,
    isError: isEquityError,
    refetch: refetchEquity,
  } = useQuery({
    queryKey: ['analytics', 'equity-curve', timeframe],
    queryFn: () => getEquityCurveApi(timeframe),
    staleTime: 30000,
  });

  if (isSummaryLoading && !summary) {
    return <DashboardSkeleton />;
  }

  if (isSummaryError && !summary) {
    return (
      <div className="p-8 rounded-xl bg-rose-950/20 border border-rose-800/40 text-center space-y-4 max-w-lg mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 mx-auto flex items-center justify-center">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-base font-bold text-white">
            Failed to Load Analytics
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Could not fetch portfolio metrics from the backend API.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            refetchSummary();
            refetchEquity();
          }}
          className="gap-2 mx-auto"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Retry Fetch Analytics
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 6 Executive KPI Metrics */}
      <section>
        <SummaryKPICards summary={summary} isLoading={isSummaryLoading} />
      </section>

      {/* Interactive Equity Curve Chart */}
      <section>
        {isEquityError ? (
          <div className="p-6 rounded-xl bg-surface/50 border border-border/50 text-center text-xs text-slate-400 space-y-2">
            <p>Could not load equity curve data.</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetchEquity()}
            >
              Retry
            </Button>
          </div>
        ) : (
          <EquityCurveChart
            points={equityPoints || []}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            isLoading={isEquityLoading}
          />
        )}
      </section>
    </div>
  );
}
