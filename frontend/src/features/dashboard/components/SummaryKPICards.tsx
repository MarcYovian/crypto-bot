import { AnalyticsSummaryDTO } from '@/types/analytics';
import { KPICard } from './KPICard';
import { Badge } from '@/components/ui/badge';
import { TooltipProvider } from '@/components/ui/tooltip';
import { formatUSDT, formatPercent } from '@/utils/format';
import {
  DollarSign,
  Wallet,
  TrendingUp,
  TrendingDown,
  Target,
  Scale,
  ShieldAlert,
} from 'lucide-react';

export interface SummaryKPICardsProps {
  summary?: AnalyticsSummaryDTO;
  isLoading?: boolean;
}

export function SummaryKPICards({ summary }: SummaryKPICardsProps) {
  const totalBalance = summary?.total_balance_usdt ?? 0;
  const freeMargin = summary?.free_margin_usdt ?? 0;
  const dailyPnL = summary?.daily_realized_pnl ?? 0;
  const dailyPnLPct = summary?.daily_pnl_percent ?? 0;
  const winRate = summary?.win_rate ?? 0;
  const totalTrades = summary?.total_trades_count ?? 0;
  const winningTrades = summary?.winning_trades_count ?? 0;
  const losingTrades = summary?.losing_trades_count ?? 0;
  const profitFactor = summary?.profit_factor ?? 0;
  const riskBudget = summary?.daily_risk_budget ?? 200;
  const remainingRisk = summary?.remaining_risk_budget ?? riskBudget;

  const isProfit = dailyPnL >= 0;
  const freeMarginRatio = totalBalance > 0 ? (freeMargin / totalBalance) * 100 : 100;
  const isRiskWarning = riskBudget > 0 && remainingRisk <= 0.2 * riskBudget;

  return (
    <TooltipProvider>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
      {/* 1. Total Balance */}
      <KPICard
        title="Total Balance"
        value={formatUSDT(totalBalance)}
        icon={<DollarSign className="w-4 h-4 text-brand-400" />}
        subText={
          <span className="font-mono text-[11px]">
            Free: {formatUSDT(freeMargin)} ({freeMarginRatio.toFixed(1)}%)
          </span>
        }
        tooltip="Total equity across all active and margin balances."
      />

      {/* 2. Free Margin */}
      <KPICard
        title="Free Margin"
        value={formatUSDT(freeMargin)}
        icon={<Wallet className="w-4 h-4 text-sky-400" />}
        subText={
          <span className="text-[11px]">
            Active Positions: <span className="font-mono text-white font-semibold">{summary?.active_trades_count ?? 0}</span>
          </span>
        }
        tooltip="Available capital for opening new trading positions."
      />

      {/* 3. Daily Realized PnL */}
      <KPICard
        title="Daily Realized PnL"
        value={
          <span className={isProfit ? 'text-emerald-400' : 'text-rose-400'}>
            {dailyPnL > 0 ? `+${formatUSDT(dailyPnL)}` : formatUSDT(dailyPnL)}
          </span>
        }
        icon={
          isProfit ? (
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          ) : (
            <TrendingDown className="w-4 h-4 text-rose-400" />
          )
        }
        badge={
          <Badge variant={isProfit ? 'profit' : 'loss'} size="sm">
            {formatPercent(dailyPnLPct, true)}
          </Badge>
        }
        subText={
          <span className="text-[11px]">
            Since 00:00 UTC
          </span>
        }
        tooltip="Net closed profits and losses accumulated today."
      />

      {/* 4. Win Rate */}
      <KPICard
        title="Win Rate"
        value={formatPercent(winRate, false)}
        icon={<Target className="w-4 h-4 text-purple-400" />}
        subText={
          <div className="space-y-1">
            <div className="flex justify-between font-mono text-[11px]">
              <span className="text-emerald-400">{winningTrades}W</span>
              <span className="text-slate-500">/</span>
              <span className="text-rose-400">{losingTrades}L</span>
              <span className="text-slate-500">({totalTrades} trades)</span>
            </div>
            <div className="w-full h-1 bg-surface rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-brand-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(Math.max(winRate, 0), 100)}%` }}
              />
            </div>
          </div>
        }
        tooltip="Percentage of closed trades hitting Take Profit."
      />

      {/* 5. Profit Factor */}
      <KPICard
        title="Profit Factor"
        value={profitFactor.toFixed(2)}
        icon={<Scale className="w-4 h-4 text-amber-400" />}
        subText={
          <span className="text-[11px]">
            Gross Profit / Loss Ratio
          </span>
        }
        tooltip="Ratio of gross trading profits divided by gross trading losses."
      />

      {/* 6. Remaining Risk Budget */}
      <KPICard
        title="Remaining Risk"
        value={
          <span className={isRiskWarning ? 'text-amber-300' : 'text-slate-100'}>
            {formatUSDT(remainingRisk)}
          </span>
        }
        icon={<ShieldAlert className="w-4 h-4 text-amber-400" />}
        isWarning={isRiskWarning}
        subText={
          <span className="text-[11px] font-mono">
            Cap: {formatUSDT(riskBudget)} (2% Guard)
          </span>
        }
        tooltip="Daily loss budget remaining before Circuit Breaker pauses trading."
      />
    </div>
    </TooltipProvider>
  );
}
