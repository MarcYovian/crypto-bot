import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Search, Filter, CheckCircle2 } from 'lucide-react';
import { cn } from '@/utils/cn';

export type WatchlistStatusFilter = 'ALL' | 'ENABLED' | 'DISABLED';

export interface WatchlistSearchFilterProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  statusFilter: WatchlistStatusFilter;
  onStatusFilterChange: (status: WatchlistStatusFilter) => void;
  enabledCount: number;
  totalCount: number;
}

const FILTERS: WatchlistStatusFilter[] = ['ALL', 'ENABLED', 'DISABLED'];

export function WatchlistSearchFilter({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  enabledCount,
  totalCount,
}: WatchlistSearchFilterProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-surface/50 border border-border/50 text-xs font-mono">
      {/* Left: Status Filter Pills */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 bg-surface/80 p-0.5 rounded-lg border border-border/80">
          <Filter className="w-3.5 h-3.5 text-slate-400 ml-1.5 mr-0.5" />
          {FILTERS.map((st) => {
            const isSelected = statusFilter === st;
            return (
              <button
                key={st}
                onClick={() => onStatusFilterChange(st)}
                className={cn(
                  'px-2.5 py-1 text-[11px] rounded font-medium transition-all',
                  isSelected
                    ? 'bg-brand-500 text-white shadow-glow-brand'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                )}
              >
                {st}
              </button>
            );
          })}
        </div>

        <Badge
          variant="profit"
          size="sm"
          className="gap-1 font-mono text-[10px] hidden sm:inline-flex"
        >
          <CheckCircle2 className="w-2.5 h-2.5 text-emerald-300" />
          {enabledCount} of {totalCount} Pairs Active
        </Badge>
      </div>

      {/* Right: Search Input */}
      <div className="relative w-44 sm:w-56">
        <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
        <Input
          type="text"
          placeholder="Filter symbol (e.g. BTC)..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-8 h-8 text-xs bg-surface/60 border-border/80 font-mono"
        />
      </div>
    </div>
  );
}
