import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAnalyticsSummaryApi, getEquityCurveApi } from '@/api/endpoints/analytics';
import { TimeframeOption } from '@/types/analytics';
import { SummaryKPICards } from './components/SummaryKPICards';
import { EquityCurveChart } from './components/EquityCurveChart';
import { DashboardSkeleton } from './components/DashboardSkeleton';
import { ActiveTradesPage } from '@/features/trades';
import { SignalsFeedPage } from '@/features/signals';
import { Button } from '@/components/ui/button';
import { AlertCircle, RefreshCw } from 'lucide-react';

export function ExecutiveDashboardPage() {
  const [timeframe, setTimeframe] = useState<TimeframeOption>('30d');

  const {
    data: summary,
    isLoading: isSummaryLoading,
    isError: isSummaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['analytics', 'summary', 1],
    queryFn: () => getAnalyticsSummaryApi(1),
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const {
    data: equityPoints,
    isLoading: isEquityLoading,
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
            Failed to Load Executive Analytics
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Could not retrieve summary metrics from the analytics backend.
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
          <RefreshCw className="w-3.5 h-3.5" /> Retry Analytics Sync
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 1. Top Section: 6 Institutional KPI Metrics */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 font-mono">
            Portfolio Health & Risk Matrix
          </h2>
          <span className="text-[10px] text-slate-500 font-mono">
            Auto-refreshing live stream
          </span>
        </div>
        {summary && <SummaryKPICards summary={summary} />}
      </section>

      {/* 2. Middle Section: 2-Column Pro Terminal Layout (60% Chart | 40% Live Positions) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Interactive Equity Curve Chart */}
        <div className="lg:col-span-7 xl:col-span-7 min-w-0">
          <EquityCurveChart
            points={equityPoints || []}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            isLoading={isEquityLoading}
          />
        </div>

        {/* Right Column: Live Active Positions */}
        <div className="lg:col-span-5 xl:col-span-5 min-w-0">
          <ActiveTradesPage />
        </div>
      </section>

      {/* 3. Bottom Section: Live Telegram Signals Stream & Execution Wizard */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 font-mono">
            Telegram Real-Time SMC Signals & Execution Stream
          </h2>
        </div>
        <SignalsFeedPage />
      </section>
    </div>
  );
}
