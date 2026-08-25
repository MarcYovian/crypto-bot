import { useState } from 'react';
import { TradeHistoryQueryParams } from '@/types/trades';
import { useTradeHistory } from '@/hooks/useTradeHistory';
import { TradeHistoryFilterBar } from './components/TradeHistoryFilterBar';
import { TradeHistoryTable } from './components/TradeHistoryTable';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { History, AlertCircle, RefreshCw } from 'lucide-react';

export function TradeHistoryPage() {
  const [filters, setFilters] = useState<TradeHistoryQueryParams>({
    account_id: 1,
    page: 1,
    page_size: 20,
  });

  const { data, isLoading, isError, refetch } = useTradeHistory(filters);

  const handleFilterChange = (newFilters: Partial<TradeHistoryQueryParams>) => {
    setFilters((prev) => ({ ...prev, ...newFilters }));
  };

  const handleResetFilters = () => {
    setFilters({
      account_id: 1,
      page: 1,
      page_size: 20,
    });
  };

  return (
    <Card className="glass-card w-full">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-brand-400" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              Closed Trade History
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Paginated historical audit log with multi-level deep drilldown inspection
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {/* Multi-Criteria Filter Bar */}
        <TradeHistoryFilterBar
          filters={filters}
          onFilterChange={handleFilterChange}
          onReset={handleResetFilters}
        />

        {/* Error State Fallback */}
        {isError ? (
          <div className="p-8 rounded-xl bg-rose-950/20 border border-rose-800/40 text-center space-y-4 max-w-lg mx-auto">
            <div className="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 mx-auto flex items-center justify-center">
              <AlertCircle className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                Failed to Load Trade History
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Could not fetch closed transaction records from the backend API.
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => refetch()}
              className="gap-2 mx-auto"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Retry Fetch History
            </Button>
          </div>
        ) : (
          <TradeHistoryTable
            data={data}
            isLoading={isLoading}
            filters={filters}
            onPageChange={(page) => handleFilterChange({ page })}
            onPageSizeChange={(pageSize) =>
              handleFilterChange({ page_size: pageSize, page: 1 })
            }
          />
        )}
      </CardContent>
    </Card>
  );
}
