import { useState, useMemo } from 'react';
import { useWatchlist } from '@/hooks/useWatchlist';
import { WatchlistSearchFilter, WatchlistStatusFilter } from './components/WatchlistSearchFilter';
import { WatchlistGrid } from './components/WatchlistGrid';
import { InstrumentSyncButton } from './components/InstrumentSyncButton';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Eye, AlertCircle, RefreshCw } from 'lucide-react';

export function WatchlistPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<WatchlistStatusFilter>('ALL');

  const { data: watchlist = [], isLoading, isError, refetch } = useWatchlist();

  // Filter items by search query and enabled status
  const filteredItems = useMemo(() => {
    return watchlist.filter((item) => {
      // 1. Status Filter
      if (statusFilter === 'ENABLED' && !item.enabled) return false;
      if (statusFilter === 'DISABLED' && item.enabled) return false;

      // 2. Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        return item.symbol.toLowerCase().includes(q);
      }

      return true;
    });
  }, [watchlist, statusFilter, searchQuery]);

  const enabledCount = useMemo(() => {
    return watchlist.filter((item) => item.enabled).length;
  }, [watchlist]);

  return (
    <Card className="glass-card w-full">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4 text-brand-400" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              Watchlist Manager & Binance Instruments
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Configure active whitelist pairs, leverage bracket ceilings, and synchronize Binance Futures exchange specs
          </CardDescription>
        </div>

        {/* Sync from Binance Action */}
        <InstrumentSyncButton />
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {/* Search & Filter Controls */}
        <WatchlistSearchFilter
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          enabledCount={enabledCount}
          totalCount={watchlist.length}
        />

        {/* Error Fallback */}
        {isError ? (
          <div className="p-8 rounded-xl bg-rose-950/20 border border-rose-800/40 text-center space-y-4 max-w-lg mx-auto">
            <div className="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 mx-auto flex items-center justify-center">
              <AlertCircle className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                Failed to Load Watchlist
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Could not retrieve whitelist instruments from the database.
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
          <WatchlistGrid items={filteredItems} isLoading={isLoading} />
        )}
      </CardContent>
    </Card>
  );
}
