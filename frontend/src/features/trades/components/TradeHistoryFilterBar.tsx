import { TradeHistoryQueryParams } from '@/types/trades';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, RotateCcw, Filter } from 'lucide-react';

export interface TradeHistoryFilterBarProps {
  filters: TradeHistoryQueryParams;
  onFilterChange: (newFilters: Partial<TradeHistoryQueryParams>) => void;
  onReset: () => void;
}

const OUTCOMES = ['ALL', 'WIN', 'LOSS', 'BREAKEVEN', 'CANCELLED'];

export function TradeHistoryFilterBar({
  filters,
  onFilterChange,
  onReset,
}: TradeHistoryFilterBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-surface/50 border border-border/50 text-xs">
      <div className="flex flex-wrap items-center gap-2.5">
        {/* Symbol Search */}
        <div className="relative w-40">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <Input
            type="text"
            placeholder="Symbol (e.g. BTC)..."
            value={filters.symbol || ''}
            onChange={(e) => onFilterChange({ symbol: e.target.value, page: 1 })}
            className="pl-8 h-8 text-xs bg-surface/60 border-border/80 font-mono"
          />
        </div>

        {/* Outcome Selector */}
        <div className="flex items-center gap-1 bg-surface/80 p-0.5 rounded-lg border border-border/80">
          <Filter className="w-3 h-3 text-slate-400 ml-1.5 mr-0.5" />
          {OUTCOMES.map((out) => {
            const isSelected = (filters.result || 'ALL') === out;
            return (
              <button
                key={out}
                onClick={() =>
                  onFilterChange({
                    result: out === 'ALL' ? undefined : out,
                    page: 1,
                  })
                }
                className={`px-2 py-1 text-[11px] font-mono rounded font-medium transition-all ${
                  isSelected
                    ? 'bg-brand-500 text-white shadow-glow-brand'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                }`}
              >
                {out}
              </button>
            );
          })}
        </div>

        {/* Date Filter Inputs */}
        <div className="flex items-center gap-1.5 font-mono text-[11px] text-slate-400">
          <Input
            type="date"
            value={filters.start_date || ''}
            onChange={(e) =>
              onFilterChange({ start_date: e.target.value, page: 1 })
            }
            className="h-8 text-[11px] bg-surface/60 border-border/80 w-32"
          />
          <span>to</span>
          <Input
            type="date"
            value={filters.end_date || ''}
            onChange={(e) =>
              onFilterChange({ end_date: e.target.value, page: 1 })
            }
            className="h-8 text-[11px] bg-surface/60 border-border/80 w-32"
          />
        </div>
      </div>

      {/* Reset Filters */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onReset}
        className="h-8 text-xs text-slate-400 hover:text-white gap-1.5"
      >
        <RotateCcw className="w-3 h-3" />
        Reset
      </Button>
    </div>
  );
}
