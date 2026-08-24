import { useState, useMemo } from 'react';
import { WatchlistItemDTO, InstrumentDTO } from '@/types/watchlist';
import { useToggleWatchlistMutation, useInstruments } from '@/hooks/useWatchlist';
import { InstrumentBracketModal } from './InstrumentBracketModal';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { formatCrypto } from '@/utils/format';
import { Layers, Coins, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface WatchlistGridProps {
  items: WatchlistItemDTO[];
  isLoading?: boolean;
}

export function WatchlistGrid({ items, isLoading = false }: WatchlistGridProps) {
  const [selectedInstrument, setSelectedInstrument] = useState<InstrumentDTO | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);

  const toggleMutation = useToggleWatchlistMutation();
  const { data: instruments } = useInstruments();

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);

  const paginatedItems = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, safePage, pageSize]);

  const handleToggle = (symbol: string, currentEnabled: boolean) => {
    toggleMutation.mutate({ symbol, enabled: !currentEnabled });
  };

  const handleInspectBrackets = (symbol: string) => {
    const found = instruments?.find((inst) => inst.symbol === symbol);
    if (found) {
      setSelectedInstrument(found);
    } else {
      // Fallback matching object from watchlist item
      const item = items.find((it) => it.symbol === symbol);
      setSelectedInstrument({
        symbol,
        base_asset: symbol.replace('USDT', ''),
        quote_asset: 'USDT',
        price_precision: 2,
        qty_precision: 3,
        tick_size: item?.tick_size ?? 0.1,
        step_size: item?.min_qty ?? 0.001,
        min_notional: 5.0,
        max_leverage: item?.max_leverage ?? 125,
        brackets: [],
      });
    }
    setIsModalOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border border-border/40 font-mono text-xs">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border/60 bg-surface/70 text-[11px] font-semibold text-slate-400 uppercase tracking-wider select-none">
              <th className="p-3.5">Symbol Pair</th>
              <th className="p-3.5">Trading Active</th>
              <th className="p-3.5">Max Leverage</th>
              <th className="p-3.5">Tick Size</th>
              <th className="p-3.5">Min Qty</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30 bg-surface/20">
            {isLoading && items.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-400">
                  <div className="flex items-center justify-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping" />
                    Loading watchlist pairs...
                  </div>
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-500">
                  <div className="flex flex-col items-center justify-center space-y-2">
                    <Coins className="w-8 h-8 text-slate-600" />
                    <p>No whitelisted pairs found matching filter query.</p>
                  </div>
                </td>
              </tr>
            ) : (
              paginatedItems.map((item) => (
                <tr
                  key={item.id || item.symbol}
                  className="hover:bg-surface/60 transition-colors"
                >
                  {/* Symbol */}
                  <td className="p-3.5 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-brand-500/10 border border-brand-500/20 flex items-center justify-center font-bold text-brand-400 text-xs">
                        {item.symbol.slice(0, 3)}
                      </div>
                      <div>
                        <div className="font-bold text-white tracking-wide">
                          {item.symbol}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          Binance USDT-M Futures
                        </div>
                      </div>
                    </div>
                  </td>

                  {/* Active Switch */}
                  <td className="p-3.5 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <RoleGuard requiredRole="ADMIN" mode="disable">
                        <Switch
                          checked={item.enabled}
                          onCheckedChange={() =>
                            handleToggle(item.symbol, item.enabled)
                          }
                          disabled={toggleMutation.isPending}
                        />
                      </RoleGuard>
                      <Badge
                        variant={item.enabled ? 'profit' : 'neutral'}
                        size="sm"
                        className="text-[10px]"
                      >
                        {item.enabled ? 'ENABLED' : 'DISABLED'}
                      </Badge>
                    </div>
                  </td>

                  {/* Max Leverage */}
                  <td className="p-3.5 whitespace-nowrap">
                    <Badge variant="outline" size="sm" className="font-bold text-slate-200">
                      {item.max_leverage}x
                    </Badge>
                  </td>

                  {/* Tick Size */}
                  <td className="p-3.5 whitespace-nowrap text-slate-300">
                    {item.tick_size}
                  </td>

                  {/* Min Qty */}
                  <td className="p-3.5 whitespace-nowrap text-slate-300">
                    {formatCrypto(item.min_qty, 4)}
                  </td>

                  {/* Actions */}
                  <td className="p-3.5 whitespace-nowrap text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleInspectBrackets(item.symbol)}
                      className="text-brand-400 hover:text-brand-300 hover:bg-brand-500/10 gap-1.5 text-xs"
                    >
                      <Layers className="w-3.5 h-3.5" />
                      Inspect Tiers
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination & Density Controls */}
      {total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-4 px-2 pt-1 border-t border-border/40 text-xs font-mono text-slate-400">
          <div className="flex items-center gap-2">
            <span>
              Showing page <strong className="text-white">{safePage}</strong> of{' '}
              <strong className="text-white">{totalPages}</strong> ({total} pairs total)
            </span>

            {/* Per page density switcher */}
            <div className="flex items-center gap-1 ml-4">
              <span className="text-[11px] text-slate-500">Per page:</span>
              {[10, 20, 50].map((size) => (
                <button
                  key={size}
                  onClick={() => {
                    setPageSize(size);
                    setPage(1);
                  }}
                  className={cn(
                    'px-2 py-0.5 rounded text-[11px] transition-all',
                    pageSize === size
                      ? 'bg-brand-500 text-white font-bold'
                      : 'bg-surface/60 hover:bg-surface text-slate-400 hover:text-slate-200'
                  )}
                >
                  {size}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={safePage <= 1 || isLoading}
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              className="h-8 gap-1 text-xs"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={safePage >= totalPages || isLoading}
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              className="h-8 gap-1 text-xs"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Leverage Bracket Modal */}
      <InstrumentBracketModal
        instrument={selectedInstrument}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedInstrument(null);
        }}
      />
    </div>
  );
}
