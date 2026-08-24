import { useState } from 'react';
import {
  PaginatedTradeHistoryDTO,
  TradeHistoryQueryParams,
  TradeHistoryItemDTO,
} from '@/types/trades';
import { TradeDetailModal } from './TradeDetailModal';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatUSDT, formatCrypto, formatPercent, formatDateTime } from '@/utils/format';
import { cn } from '@/utils/cn';
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  History,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';

export interface TradeHistoryTableProps {
  data?: PaginatedTradeHistoryDTO;
  isLoading?: boolean;
  filters: TradeHistoryQueryParams;
  onPageChange: (newPage: number) => void;
  onPageSizeChange: (newPageSize: number) => void;
}

export function TradeHistoryTable({
  data,
  isLoading = false,
  filters,
  onPageChange,
  onPageSizeChange,
}: TradeHistoryTableProps) {
  const [selectedTradeId, setSelectedTradeId] = useState<number | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const items = data?.items || [];
  const total = data?.total || 0;
  const page = data?.page || filters.page || 1;
  const pageSize = data?.page_size || filters.page_size || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const handleRowClick = (item: TradeHistoryItemDTO) => {
    setSelectedTradeId(item.id);
    setIsModalOpen(true);
  };

  return (
    <div className="space-y-4">
      {/* Table Canvas */}
      <div className="overflow-x-auto rounded-lg border border-border/40 font-mono text-xs">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border/60 bg-surface/70 text-[11px] font-semibold text-slate-400 uppercase tracking-wider select-none">
              <th className="p-3.5">ID / Symbol</th>
              <th className="p-3.5">Side</th>
              <th className="p-3.5">Entry</th>
              <th className="p-3.5">Exit</th>
              <th className="p-3.5">Size</th>
              <th className="p-3.5">Net PnL / ROI</th>
              <th className="p-3.5">Result</th>
              <th className="p-3.5">Close Reason</th>
              <th className="p-3.5">Closed At</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30 bg-surface/20">
            {isLoading && items.length === 0 ? (
              <tr>
                <td colSpan={10} className="p-8 text-center text-slate-400">
                  <div className="flex items-center justify-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping" />
                    Loading trade history...
                  </div>
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={10} className="p-8 text-center text-slate-500">
                  <div className="flex flex-col items-center justify-center space-y-2">
                    <History className="w-8 h-8 text-slate-600" />
                    <p>No historical trades found matching filter criteria.</p>
                  </div>
                </td>
              </tr>
            ) : (
              items.map((trade) => {
                const isBuy = trade.side === 'BUY';
                const isWin = trade.result === 'WIN';
                const isLoss = trade.result === 'LOSS';
                const isProfit = (trade.net_pnl ?? 0) >= 0;

                return (
                  <tr
                    key={trade.id}
                    onClick={() => handleRowClick(trade)}
                    className="hover:bg-surface/60 cursor-pointer transition-colors"
                  >
                    {/* ID / Symbol */}
                    <td className="p-3.5 whitespace-nowrap">
                      <div className="font-bold text-white tracking-wide">
                        {trade.symbol}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        #{trade.id}
                      </div>
                    </td>

                    {/* Side */}
                    <td className="p-3.5 whitespace-nowrap">
                      <Badge variant={isBuy ? 'profit' : 'loss'} size="sm">
                        {trade.side}
                      </Badge>
                    </td>

                    {/* Entry Price */}
                    <td className="p-3.5 whitespace-nowrap text-slate-300">
                      {formatUSDT(trade.entry_price)}
                    </td>

                    {/* Exit Price */}
                    <td className="p-3.5 whitespace-nowrap text-slate-300">
                      {formatUSDT(trade.exit_price)}
                    </td>

                    {/* Position Size */}
                    <td className="p-3.5 whitespace-nowrap text-slate-300">
                      {formatCrypto(trade.position_size, 4)}
                    </td>

                    {/* Net PnL / ROI */}
                    <td className="p-3.5 whitespace-nowrap">
                      {trade.net_pnl !== null ? (
                        <div>
                          <div
                            className={cn(
                              'font-bold flex items-center gap-1',
                              isProfit ? 'text-emerald-400' : 'text-rose-400'
                            )}
                          >
                            {isProfit ? (
                              <TrendingUp className="w-3 h-3" />
                            ) : (
                              <TrendingDown className="w-3 h-3" />
                            )}
                            <span>
                              {trade.net_pnl > 0 ? '+' : ''}
                              {formatUSDT(trade.net_pnl)}
                            </span>
                          </div>
                          <div
                            className={cn(
                              'text-[10px]',
                              isProfit ? 'text-emerald-500' : 'text-rose-500'
                            )}
                          >
                            {formatPercent(trade.roi_percent, true)}
                          </div>
                        </div>
                      ) : (
                        <span className="text-slate-500">-</span>
                      )}
                    </td>

                    {/* Result */}
                    <td className="p-3.5 whitespace-nowrap">
                      <Badge
                        variant={
                          isWin
                            ? 'profit-neon'
                            : isLoss
                            ? 'loss-neon'
                            : 'neutral'
                        }
                        size="sm"
                      >
                        {trade.result}
                      </Badge>
                    </td>

                    {/* Close Reason */}
                    <td className="p-3.5 whitespace-nowrap text-slate-400 text-[11px]">
                      {trade.close_reason || '-'}
                    </td>

                    {/* Closed At */}
                    <td className="p-3.5 whitespace-nowrap text-slate-400 text-[11px]">
                      {trade.closed_at ? formatDateTime(trade.closed_at) : '-'}
                    </td>

                    {/* Action */}
                    <td className="p-3.5 whitespace-nowrap text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRowClick(trade);
                        }}
                        className="text-brand-400 hover:text-brand-300 hover:bg-brand-500/10 gap-1 text-xs"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        Drilldown
                      </Button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Server-Side Pagination Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 px-2 text-xs font-mono text-slate-400">
        <div className="flex items-center gap-2">
          <span>
            Showing page <strong className="text-white">{page}</strong> of{' '}
            <strong className="text-white">{totalPages}</strong> ({total} total records)
          </span>

          {/* Page size options */}
          <div className="flex items-center gap-1 ml-4">
            <span className="text-[11px] text-slate-500">Per page:</span>
            {[10, 20, 50].map((size) => (
              <button
                key={size}
                onClick={() => onPageSizeChange(size)}
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
            onClick={() => onPageChange(page - 1)}
            className="h-8 gap-1 text-xs"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Previous
          </Button>

          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages || isLoading}
            onClick={() => onPageChange(page + 1)}
            className="h-8 gap-1 text-xs"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* 5-Level Detail Drilldown Modal */}
      <TradeDetailModal
        tradeId={selectedTradeId}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedTradeId(null);
        }}
      />
    </div>
  );
}
