import { useProviderAnalytics } from '@/hooks/useProviders';
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
  ModalFooter,
  ModalClose,
} from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatUSDT, formatPercent } from '@/utils/format';
import { BarChart3, TrendingUp, Radio, AlertCircle } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

export interface ProviderAnalyticsModalProps {
  providerId: number | null;
  providerName?: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ProviderAnalyticsModal({
  providerId,
  providerName = 'Signal Provider',
  isOpen,
  onClose,
}: ProviderAnalyticsModalProps) {
  const { data: analytics, isLoading, isError } = useProviderAnalytics(
    isOpen ? providerId : null
  );

  return (
    <Modal open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <ModalContent className="max-w-lg font-mono text-xs">
        <ModalHeader className="border-b border-border/50 pb-3 pr-8">
          <ModalTitle className="flex items-center gap-2 text-base text-white">
            <BarChart3 className="w-4 h-4 text-brand-400" />
            {analytics?.provider_name || providerName} Performance
          </ModalTitle>
          <ModalDescription className="text-xs text-slate-400">
            Historical signal execution telemetry and realized profit metrics
          </ModalDescription>
        </ModalHeader>

        <div className="py-4">
          {isLoading ? (
            <div className="grid grid-cols-2 gap-3">
              <Skeleton className="h-20 w-full rounded-lg" />
              <Skeleton className="h-20 w-full rounded-lg" />
              <Skeleton className="h-20 w-full rounded-lg" />
              <Skeleton className="h-20 w-full rounded-lg" />
            </div>
          ) : isError ? (
            <div className="p-6 rounded-lg bg-rose-950/20 border border-rose-800/40 text-center space-y-2">
              <AlertCircle className="w-6 h-6 text-rose-400 mx-auto" />
              <p className="text-xs text-slate-300">
                Failed to load performance analytics for this provider.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* 4-Metric Grid */}
              <div className="grid grid-cols-2 gap-3">
                {/* Total Signals */}
                <div className="p-3 rounded-lg bg-surface/60 border border-border/60">
                  <div className="flex items-center justify-between text-slate-400 text-[11px]">
                    <span>Total Signals</span>
                    <Radio className="w-3.5 h-3.5 text-sky-400" />
                  </div>
                  <div className="text-xl font-bold text-white mt-1">
                    {analytics?.total_signals ?? 0}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    Ingested from Telegram
                  </span>
                </div>

                {/* Executed Trades */}
                <div className="p-3 rounded-lg bg-surface/60 border border-border/60">
                  <div className="flex items-center justify-between text-slate-400 text-[11px]">
                    <span>Executed Orders</span>
                    <TrendingUp className="w-3.5 h-3.5 text-brand-400" />
                  </div>
                  <div className="text-xl font-bold text-white mt-1">
                    {analytics?.executed_trades ?? 0}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    Auto/Manual Executions
                  </span>
                </div>

                {/* Win Rate */}
                <div className="p-3 rounded-lg bg-surface/60 border border-border/60">
                  <div className="flex items-center justify-between text-slate-400 text-[11px]">
                    <span>Win Rate</span>
                    <Badge
                      variant={(analytics?.win_rate ?? 0) >= 50 ? 'profit' : 'loss'}
                      size="sm"
                    >
                      {((analytics?.win_rate ?? 0)).toFixed(1)}%
                    </Badge>
                  </div>
                  <div
                    className={`text-xl font-bold mt-1 ${
                      (analytics?.win_rate ?? 0) >= 50
                        ? 'text-emerald-400'
                        : 'text-slate-200'
                    }`}
                  >
                    {formatPercent(analytics?.win_rate ?? 0, false, 1)}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    Winning Trades Ratio
                  </span>
                </div>

                {/* Realized Net PnL */}
                <div className="p-3 rounded-lg bg-surface/60 border border-border/60">
                  <div className="flex items-center justify-between text-slate-400 text-[11px]">
                    <span>Realized Net PnL</span>
                    <Badge
                      variant={
                        (analytics?.total_net_pnl_usdt ?? 0) >= 0 ? 'profit' : 'loss'
                      }
                      size="sm"
                    >
                      USDT
                    </Badge>
                  </div>
                  <div
                    className={`text-xl font-bold mt-1 ${
                      (analytics?.total_net_pnl_usdt ?? 0) >= 0
                        ? 'text-emerald-400'
                        : 'text-rose-400'
                    }`}
                  >
                    {formatUSDT(analytics?.total_net_pnl_usdt ?? 0, 2)}
                  </div>
                  <span className="text-[10px] text-slate-500">
                    Net after fees & slippage
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        <ModalFooter className="border-t border-border/50 pt-3">
          <ModalClose asChild>
            <Button variant="secondary" size="sm">
              Close Telemetry
            </Button>
          </ModalClose>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
