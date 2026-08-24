import { useWatchlist } from '@/hooks/useWatchlist';
import { RiskSimulationRequestDTO } from '@/types/calculator';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Calculator,
  ArrowUpRight,
  ArrowDownRight,
  Percent,
  Wallet,
  Zap,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export interface RiskSimulatorFormProps {
  formData: RiskSimulationRequestDTO;
  onChange: (data: RiskSimulationRequestDTO) => void;
}

const DEFAULT_PAIRS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT'];
const LEVERAGE_OPTIONS = [10, 20, 50, 75, 100, 125];
const RISK_PILLS = [0.5, 1.0, 1.5, 2.0, 3.0];

export function RiskSimulatorForm({
  formData,
  onChange,
}: RiskSimulatorFormProps) {
  const { data: watchlist = [] } = useWatchlist();

  const availableSymbols =
    watchlist.length > 0
      ? watchlist.map((w) => w.symbol)
      : DEFAULT_PAIRS;

  const handleFieldChange = <K extends keyof RiskSimulationRequestDTO>(
    field: K,
    val: RiskSimulationRequestDTO[K]
  ) => {
    onChange({
      ...formData,
      [field]: val,
    });
  };

  return (
    <Card className="glass-card w-full font-mono text-xs">
      <CardHeader className="pb-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <Calculator className="w-4 h-4 text-brand-400" />
          <CardTitle className="text-base font-bold text-white tracking-tight">
            Simulation Parameters
          </CardTitle>
        </div>
        <CardDescription className="text-xs text-slate-400 mt-0.5">
          Adjust price levels, wallet equity, and leverage to test position sizing scenarios
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {/* 1. Symbol & Direction Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Symbol Pair */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium block">
              Trading Pair
            </label>
            <select
              value={formData.symbol}
              onChange={(e) => handleFieldChange('symbol', e.target.value)}
              className="w-full h-9 rounded-lg bg-surface/80 border border-border/80 text-white font-mono px-3 text-xs focus:outline-none focus:ring-2 focus:ring-brand-400"
            >
              {availableSymbols.map((sym) => (
                <option key={sym} value={sym} className="bg-slate-900 text-white">
                  {sym}
                </option>
              ))}
            </select>
          </div>

          {/* Trade Direction */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium block">
              Position Direction
            </label>
            <div className="grid grid-cols-2 gap-2 h-9">
              <button
                type="button"
                onClick={() => handleFieldChange('side', 'BUY')}
                className={cn(
                  'flex items-center justify-center gap-1 rounded-lg text-xs font-bold transition-all border',
                  formData.side === 'BUY'
                    ? 'bg-trading-profit/90 text-slate-950 border-emerald-400 shadow-glow-profit'
                    : 'bg-surface/60 text-slate-400 border-border/70 hover:text-white'
                )}
              >
                <ArrowUpRight className="w-3.5 h-3.5" /> BUY / LONG
              </button>
              <button
                type="button"
                onClick={() => handleFieldChange('side', 'SELL')}
                className={cn(
                  'flex items-center justify-center gap-1 rounded-lg text-xs font-bold transition-all border',
                  formData.side === 'SELL'
                    ? 'bg-trading-loss/90 text-white border-rose-400 shadow-glow-loss'
                    : 'bg-surface/60 text-slate-400 border-border/70 hover:text-white'
                )}
              >
                <ArrowDownRight className="w-3.5 h-3.5" /> SELL / SHORT
              </button>
            </div>
          </div>
        </div>

        {/* 2. Entry Price & Stop Loss Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Entry Price */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium block">
              Entry Price (USDT)
            </label>
            <Input
              type="number"
              step="any"
              min="0"
              value={formData.entry_price || ''}
              onChange={(e) =>
                handleFieldChange('entry_price', parseFloat(e.target.value) || 0)
              }
              placeholder="e.g. 50000.00"
              className="h-9 bg-surface/70 border-border/80 text-white font-bold"
            />
          </div>

          {/* Stop Loss Price */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium block">
              Stop Loss Price (USDT)
            </label>
            <Input
              type="number"
              step="any"
              min="0"
              value={formData.sl_price || ''}
              onChange={(e) =>
                handleFieldChange('sl_price', parseFloat(e.target.value) || 0)
              }
              placeholder="e.g. 49000.00"
              className="h-9 bg-surface/70 border-border/80 text-rose-300 font-bold"
            />
          </div>
        </div>

        {/* 3. Account Balance & Risk % Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Account Balance */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium flex items-center justify-between">
              <span className="flex items-center gap-1">
                <Wallet className="w-3.5 h-3.5 text-brand-400" /> Wallet Balance
              </span>
              <span className="text-[10px] text-slate-500">USDT</span>
            </label>
            <Input
              type="number"
              step="any"
              min="0"
              value={formData.wallet_balance || ''}
              onChange={(e) =>
                handleFieldChange(
                  'wallet_balance',
                  parseFloat(e.target.value) || 0
                )
              }
              placeholder="1000.00"
              className="h-9 bg-surface/70 border-border/80 text-white font-bold"
            />
          </div>

          {/* Risk Percentage */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-slate-300 font-medium flex items-center gap-1">
                <Percent className="w-3.5 h-3.5 text-brand-400" /> Risk Budget
              </label>
              <Badge variant="profit" size="sm" className="font-bold">
                {formData.risk_percent.toFixed(1)}% of Balance
              </Badge>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="range"
                min="0.1"
                max="5.0"
                step="0.1"
                value={formData.risk_percent}
                onChange={(e) =>
                  handleFieldChange(
                    'risk_percent',
                    parseFloat(e.target.value) || 0.1
                  )
                }
                className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-brand-500"
              />
              <Input
                type="number"
                step="0.1"
                min="0.1"
                max="5.0"
                value={formData.risk_percent}
                onChange={(e) =>
                  handleFieldChange(
                    'risk_percent',
                    parseFloat(e.target.value) || 0.1
                  )
                }
                className="w-16 h-8 text-center bg-surface/70 border-border/80 font-bold text-xs"
              />
            </div>

            {/* Quick Risk Pills */}
            <div className="flex items-center gap-1 pt-0.5">
              {RISK_PILLS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => handleFieldChange('risk_percent', p)}
                  className={cn(
                    'px-2 py-0.5 rounded text-[10px] font-bold transition-all',
                    formData.risk_percent === p
                      ? 'bg-brand-500 text-white shadow-glow-brand'
                      : 'bg-surface/80 text-slate-400 hover:text-white border border-border/60'
                  )}
                >
                  {p.toFixed(1)}%
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 4. Requested Leverage */}
        <div className="space-y-1.5 p-3 rounded-xl bg-surface/50 border border-border/60">
          <div className="flex items-center justify-between">
            <label className="text-slate-300 font-medium flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-amber-400" /> Requested Leverage Multiplier
            </label>
            <Badge variant="outline" size="sm" className="font-bold text-slate-200">
              {formData.requested_leverage}x
            </Badge>
          </div>

          <div className="flex flex-wrap gap-1.5 pt-1">
            {LEVERAGE_OPTIONS.map((lev) => (
              <button
                key={lev}
                type="button"
                onClick={() => handleFieldChange('requested_leverage', lev)}
                className={cn(
                  'flex-1 min-w-[48px] py-1.5 rounded-lg text-xs font-bold transition-all border',
                  formData.requested_leverage === lev
                    ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-glow-warning font-bold'
                    : 'bg-surface/80 text-slate-400 border-border/70 hover:text-white'
                )}
              >
                {lev}x
              </button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
