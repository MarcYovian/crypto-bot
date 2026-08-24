import { RiskSimulationResponseDTO } from '@/types/calculator';
import { LiquidationVisualizer } from './LiquidationVisualizer';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatUSDT, formatCrypto } from '@/utils/format';
import {
  Calculator,
  ShieldCheck,
  AlertTriangle,
  Coins,
  DollarSign,
  TrendingDown,
  Gauge,
  Sparkles,
} from 'lucide-react';

export interface SimulationResultCardProps {
  result?: RiskSimulationResponseDTO | null;
  isLoading?: boolean;
  isDebouncing?: boolean;
  geometryError?: string | null;
  requestedLeverage?: number;
}

export function SimulationResultCard({
  result,
  isLoading = false,
  isDebouncing = false,
  geometryError,
  requestedLeverage,
}: SimulationResultCardProps) {
  if (geometryError) {
    return (
      <Card className="glass-card w-full font-mono text-xs h-full flex flex-col justify-center items-center p-8 text-center border-dashed border-rose-500/40 bg-rose-950/10">
        <div className="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center mb-3">
          <AlertTriangle className="w-6 h-6 animate-pulse" />
        </div>
        <h4 className="text-sm font-bold text-white mb-1">
          Invalid Simulation Geometry
        </h4>
        <p className="text-xs text-rose-300 max-w-sm">{geometryError}</p>
      </Card>
    );
  }

  if (isLoading || isDebouncing) {
    return (
      <Card className="glass-card w-full font-mono text-xs h-full flex flex-col justify-center items-center p-12 text-center">
        <div className="w-12 h-12 rounded-full bg-brand-500/20 text-brand-400 flex items-center justify-center mb-3 animate-spin">
          <Calculator className="w-6 h-6" />
        </div>
        <h4 className="text-sm font-bold text-white mb-1">
          Simulating Position Sizing...
        </h4>
        <p className="text-xs text-slate-400">
          Calculating Binance bracket tiers, margin requirements, and liquidation buffer
        </p>
      </Card>
    );
  }

  if (!result) {
    return (
      <Card className="glass-card w-full font-mono text-xs h-full flex flex-col justify-center items-center p-12 text-center text-slate-500">
        <Calculator className="w-10 h-10 mb-2 text-slate-600" />
        <p>Enter trade parameters on the left to calculate position sizing.</p>
      </Card>
    );
  }

  return (
    <Card className="glass-card w-full font-mono text-xs space-y-4">
      <CardHeader className="pb-3 border-b border-border/50 flex flex-row items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-400" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              Position Sizing & Risk Telemetry
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Institutional lot sizing capped strictly at 2.0% loss budget
          </CardDescription>
        </div>

        {/* Safety Badge */}
        <Badge
          variant={result.is_safe ? 'profit' : 'loss'}
          size="md"
          className="font-bold gap-1 shadow-sm"
        >
          {result.is_safe ? (
            <>
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-300" />
              SAFE (2% RISK CAP)
            </>
          ) : (
            <>
              <AlertTriangle className="w-3.5 h-3.5 text-rose-300" />
              UNSAFE / HIGH MARGIN
            </>
          )}
        </Badge>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Dynamic Downscaling Warning Banner */}
        {result.is_leverage_downscaled && (
          <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-500/50 text-amber-300 space-y-1 animate-in fade-in-0">
            <div className="flex items-center gap-2 font-bold text-xs">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>Dynamic Leverage Downscaling Activated</span>
            </div>
            <p className="text-[11px] text-amber-200/90 leading-relaxed">
              Leverage disesuaikan dari{' '}
              <strong className="text-white">{requestedLeverage ?? 'requested'}x</strong> ke{' '}
              <strong className="text-white">{result.effective_leverage}x</strong> untuk mematuhi batas maksimal notional bracket Binance Futures.
            </p>
          </div>
        )}

        {/* 4 Core Metrics Grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* 1. Recommended Position Size */}
          <div className="p-3 rounded-lg bg-surface/70 border border-brand-500/20 space-y-1">
            <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase">
              <span>Position Size</span>
              <Coins className="w-3.5 h-3.5 text-brand-400" />
            </div>
            <div className="text-lg font-bold text-brand-300">
              {formatCrypto(result.calculated_position_size, 4)}{' '}
              <span className="text-xs text-slate-400">{result.symbol.replace('USDT', '')}</span>
            </div>
            <span className="text-[10px] text-slate-500 block">
              Optimal lot quantity
            </span>
          </div>

          {/* 2. Required Margin */}
          <div className="p-3 rounded-lg bg-surface/70 border border-sky-500/20 space-y-1">
            <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase">
              <span>Required Margin</span>
              <DollarSign className="w-3.5 h-3.5 text-sky-400" />
            </div>
            <div className="text-lg font-bold text-white">
              {formatUSDT(result.required_margin_usdt)}
            </div>
            <span className="text-[10px] text-slate-500 block">
              Effective Leverage: <strong className="text-slate-300">{result.effective_leverage}x</strong>
            </span>
          </div>

          {/* 3. Projected Loss at SL */}
          <div className="p-3 rounded-lg bg-surface/70 border border-rose-500/20 space-y-1">
            <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase">
              <span>Loss at Stop Loss</span>
              <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
            </div>
            <div className="text-lg font-bold text-rose-400">
              {formatUSDT(result.projected_loss_at_sl_usdt)}
            </div>
            <span className="text-[10px] text-slate-500 block">
              Max Loss Budget: {formatUSDT(result.max_allowed_loss_usdt)}
            </span>
          </div>

          {/* 4. Estimated Liquidation Price */}
          <div className="p-3 rounded-lg bg-surface/70 border border-amber-500/20 space-y-1">
            <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase">
              <span>Estimated Liq Price</span>
              <Gauge className="w-3.5 h-3.5 text-amber-400" />
            </div>
            <div className="text-lg font-bold text-amber-300">
              {formatUSDT(result.estimated_liquidation_price)}
            </div>
            <span className="text-[10px] text-slate-500 block">
              Stop Distance: {formatUSDT(result.stop_distance_usdt)}
            </span>
          </div>
        </div>

        {/* Liquidation & Safety Visualizer */}
        <LiquidationVisualizer
          side={result.side}
          entryPrice={
            result.side === 'BUY'
              ? result.estimated_liquidation_price + result.stop_distance_usdt * 1.5
              : result.estimated_liquidation_price - result.stop_distance_usdt * 1.5
          }
          slPrice={
            result.side === 'BUY'
              ? result.estimated_liquidation_price + result.stop_distance_usdt * 0.5
              : result.estimated_liquidation_price - result.stop_distance_usdt * 0.5
          }
          liqPrice={result.estimated_liquidation_price}
        />
      </CardContent>
    </Card>
  );
}
