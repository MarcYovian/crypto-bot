import { useState, useMemo } from 'react';
import {
  PaginatedSignalListDTO,
  SignalQueryParams,
  SignalItemDTO,
} from '@/types/signals';
import { SignalCard } from './SignalCard';
import { SignalCompactRow } from './SignalCompactRow';
import { SignalExecutionWizardModal } from './SignalExecutionWizardModal';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ChevronLeft,
  ChevronRight,
  Radio,
  Filter,
  Search,
  LayoutGrid,
  List,
  Zap,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export interface SignalFeedListProps {
  data?: PaginatedSignalListDTO;
  isLoading?: boolean;
  filters: SignalQueryParams;
  onFilterChange: (newFilters: Partial<SignalQueryParams>) => void;
  accountBalance?: number;
}

const STATUS_FILTERS = [
  'ALL',
  'PENDING',
  'PROCESSED',
  'REJECTED',
  'EXPIRED',
];

export function SignalFeedList({
  data,
  isLoading = false,
  filters,
  onFilterChange,
  accountBalance = 10000.0,
}: SignalFeedListProps) {
  const [selectedSignal, setSelectedSignal] = useState<SignalItemDTO | null>(null);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchQuery, setSearchQuery] = useState('');

  const rawItems = useMemo(() => data?.items || [], [data?.items]);
  const total = data?.total || 0;
  const page = data?.page || filters.page || 1;
  const pageSize = data?.page_size || filters.page_size || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Client-side search filtering by symbol / side / trace
  const items = useMemo(() => {
    if (!searchQuery.trim()) return rawItems;
    const q = searchQuery.toLowerCase().trim();
    return rawItems.filter(
      (s) =>
        s.symbol.toLowerCase().includes(q) ||
        s.side.toLowerCase().includes(q) ||
        (s.trace_id && s.trace_id.toLowerCase().includes(q))
    );
  }, [rawItems, searchQuery]);

  const pendingCount = useMemo(() => {
    return rawItems.filter(
      (s) => s.status === 'PENDING' || s.status === 'RECEIVED'
    ).length;
  }, [rawItems]);

  const handleOpenWizard = (signal: SignalItemDTO) => {
    setSelectedSignal(signal);
    setIsWizardOpen(true);
  };

  return (
    <div className="space-y-4">
      {/* Quick Summary Banner & Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-surface/50 border border-border/50 text-xs">
        {/* Left: Status Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 bg-surface/80 p-0.5 rounded-lg border border-border/80">
            <Filter className="w-3 h-3 text-slate-400 ml-1.5 mr-0.5" />
            {STATUS_FILTERS.map((st) => {
              const isSelected = (filters.status || 'ALL') === st;
              return (
                <button
                  key={st}
                  onClick={() =>
                    onFilterChange({
                      status: st === 'ALL' ? undefined : st,
                      page: 1,
                    })
                  }
                  className={cn(
                    'px-2.5 py-1 text-[11px] font-mono rounded font-medium transition-all',
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

          {/* Quick Pending Counter Badge */}
          {pendingCount > 0 && (
            <Badge
              variant="info"
              size="sm"
              className="gap-1 font-mono text-[10px] hidden sm:inline-flex"
            >
              <Zap className="w-2.5 h-2.5 text-sky-300" />
              {pendingCount} Ready to Execute
            </Badge>
          )}
        </div>

        {/* Right: Search Input & View Layout Switcher */}
        <div className="flex items-center gap-2.5">
          <div className="relative w-36 sm:w-44">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <Input
              type="text"
              placeholder="Search symbol..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-8 text-xs bg-surface/60 border-border/80 font-mono"
            />
          </div>

          {/* Grid vs List View Toggle */}
          <div className="flex items-center bg-surface/80 p-0.5 rounded-lg border border-border/80">
            <button
              onClick={() => setViewMode('grid')}
              title="Grid View"
              className={cn(
                'p-1.5 rounded transition-all',
                viewMode === 'grid'
                  ? 'bg-brand-500 text-white shadow-glow-brand'
                  : 'text-slate-400 hover:text-slate-200'
              )}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              title="Compact List View"
              className={cn(
                'p-1.5 rounded transition-all',
                viewMode === 'list'
                  ? 'bg-brand-500 text-white shadow-glow-brand'
                  : 'text-slate-400 hover:text-slate-200'
              )}
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Constrained Scroll Container with Pro Max-Height */}
      <div className="max-h-[580px] overflow-y-auto pr-1 space-y-3 custom-scrollbar">
        {isLoading && rawItems.length === 0 ? (
          <div className="py-16 text-center text-xs font-mono text-slate-400 flex items-center justify-center gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping" />
            Listening for Telegram signals...
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 px-4 text-center flex flex-col items-center justify-center space-y-3 bg-surface/30 border border-dashed border-border/60 rounded-xl font-mono">
            <div className="w-12 h-12 rounded-full bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-brand-400">
              <Radio className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-white tracking-tight">
                No Signals Found
              </h4>
              <p className="text-xs text-slate-400 mt-1 max-w-sm">
                Telegram webhook listener is active and monitoring for incoming signals.
              </p>
            </div>
          </div>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {items.map((signal) => (
              <SignalCard
                key={signal.id}
                signal={signal}
                onExecuteClick={handleOpenWizard}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((signal) => (
              <SignalCompactRow
                key={signal.id}
                signal={signal}
                onExecuteClick={handleOpenWizard}
              />
            ))}
          </div>
        )}
      </div>

      {/* Sticky Bottom Pagination & Density Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 px-2 pt-2 border-t border-border/40 text-xs font-mono text-slate-400">
        <div className="flex items-center gap-2">
          <span>
            Page <strong className="text-white">{page}</strong> of{' '}
            <strong className="text-white">{totalPages}</strong> ({total} total)
          </span>

          {/* Density / Items Per Page */}
          <div className="flex items-center gap-1 ml-3">
            <span className="text-[11px] text-slate-500">Per page:</span>
            {[10, 20, 50].map((size) => (
              <button
                key={size}
                onClick={() =>
                  onFilterChange({ page_size: size, page: 1 })
                }
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
            disabled={page <= 1 || isLoading}
            onClick={() => onFilterChange({ page: page - 1 })}
            className="h-8 gap-1 text-xs"
          >
            <ChevronLeft className="w-3.5 h-3.5" /> Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages || isLoading}
            onClick={() => onFilterChange({ page: page + 1 })}
            className="h-8 gap-1 text-xs"
          >
            Next <ChevronRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Execution Wizard Modal */}
      <SignalExecutionWizardModal
        signal={selectedSignal}
        isOpen={isWizardOpen}
        onClose={() => {
          setIsWizardOpen(false);
          setSelectedSignal(null);
        }}
        accountBalance={accountBalance}
      />
    </div>
  );
}
