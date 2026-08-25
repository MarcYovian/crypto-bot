import { useState, useMemo } from 'react';
import { ActiveTradeDTO } from '@/types/trades';
import { ActiveTradeRow } from './ActiveTradeRow';
import { EmptyPositionsState } from './EmptyPositionsState';
import { ManualCloseModal } from './ManualCloseModal';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { formatUSDT } from '@/utils/format';
import { cn } from '@/utils/cn';
import { Layers, Search } from 'lucide-react';

export interface ActiveTradesTableProps {
  trades?: ActiveTradeDTO[];
  isLoading?: boolean;
}

export function ActiveTradesTable({
  trades = [],
  isLoading = false,
}: ActiveTradesTableProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTrade, setSelectedTrade] = useState<ActiveTradeDTO | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const filteredTrades = useMemo(() => {
    if (!searchQuery.trim()) return trades;
    const query = searchQuery.toLowerCase().trim();
    return trades.filter(
      (t) =>
        t.symbol.toLowerCase().includes(query) ||
        t.side.toLowerCase().includes(query) ||
        String(t.trade_id).includes(query)
    );
  }, [trades, searchQuery]);

  const totalUnrealizedPnL = useMemo(() => {
    return trades.reduce((acc, t) => acc + (t.unrealized_pnl || 0), 0);
  }, [trades]);

  const isTotalProfit = totalUnrealizedPnL >= 0;

  const handleOpenCloseModal = (trade: ActiveTradeDTO) => {
    setSelectedTrade(trade);
    setIsModalOpen(true);
  };

  return (
    <Card className="glass-card w-full">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-brand-400" />
            <CardTitle className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              Active Positions
              <Badge variant="info" size="sm">
                {trades.length} Live
              </Badge>
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Real-time open orders, mark prices, and multi-stage Take Profit tracking
          </CardDescription>
        </div>

        {/* Floating PnL Summary & Search Filter */}
        <div className="flex flex-wrap items-center gap-3">
          {trades.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-surface/80 border border-border/80 font-mono text-xs">
              <span className="text-slate-400">Total Floating:</span>
              <span
                className={cn(
                  'font-bold',
                  isTotalProfit ? 'text-emerald-400' : 'text-rose-400'
                )}
              >
                {isTotalProfit ? '+' : ''}
                {formatUSDT(totalUnrealizedPnL)}
              </span>
            </div>
          )}

          <div className="relative w-full sm:w-48">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <Input
              type="text"
              placeholder="Filter symbol/side..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-8 text-xs bg-surface/50 border-border/80"
            />
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4">
        {isLoading && trades.length === 0 ? (
          <div className="py-12 text-center text-xs font-mono text-slate-400 flex items-center justify-center gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping" />
            Loading active positions...
          </div>
        ) : filteredTrades.length === 0 ? (
          <EmptyPositionsState />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border/40">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border/60 bg-surface/70 text-[11px] font-semibold text-slate-400 uppercase tracking-wider select-none">
                  <th className="p-3.5">Symbol / Side</th>
                  <th className="p-3.5">Size / Qty</th>
                  <th className="p-3.5">Entry Price</th>
                  <th className="p-3.5">Mark Price</th>
                  <th className="p-3.5">Stop Loss</th>
                  <th className="p-3.5">TP Targets</th>
                  <th className="p-3.5">Floating PnL</th>
                  <th className="p-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30 bg-surface/20">
                {filteredTrades.map((trade) => (
                  <ActiveTradeRow
                    key={trade.trade_id}
                    trade={trade}
                    onCloseClick={handleOpenCloseModal}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      {/* Manual Close Modal */}
      <ManualCloseModal
        trade={selectedTrade}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedTrade(null);
        }}
      />
    </Card>
  );
}
