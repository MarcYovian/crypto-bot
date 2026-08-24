import { useState } from 'react';
import { useStrategies, useUpdateStrategyMutation } from '@/hooks/useStrategies';
import { StrategyDTO } from '@/types/strategies';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RoleGuard } from '@/features/auth/RoleGuard';
import {
  Sliders,
  CheckCircle2,
  AlertCircle,
  ShieldAlert,
  Save,
  Crosshair,
  TrendingUp,
} from 'lucide-react';

interface StrategyConfigFormProps {
  strategy: StrategyDTO;
}

function StrategyConfigForm({ strategy }: StrategyConfigFormProps) {
  const updateMutation = useUpdateStrategyMutation();

  const getInitialTp = (level: number, fallback: number) => {
    const found = strategy.tp_allocations.find((a) => a.tp_level === level);
    return found ? found.percentage : fallback;
  };

  const [tp1, setTp1] = useState<number>(getInitialTp(1, 50));
  const [tp2, setTp2] = useState<number>(getInitialTp(2, 30));
  const [tp3, setTp3] = useState<number>(getInitialTp(3, 20));
  const [bepLevel, setBepLevel] = useState<number>(strategy.bep_trigger_level || 1);
  const [trailingLevel, setTrailingLevel] = useState<number>(strategy.trailing_trigger_level || 2);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);
  const [saveErrorMsg, setSaveErrorMsg] = useState<string | null>(null);

  // Compute allocation sum
  const totalAllocation = Number((tp1 + tp2 + tp3).toFixed(1));
  const is100Percent = Math.abs(totalAllocation - 100) < 0.01;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!is100Percent || updateMutation.isPending) return;

    setSaveSuccessMsg(null);
    setSaveErrorMsg(null);

    try {
      await updateMutation.mutateAsync({
        id: strategy.id,
        payload: {
          tp1_percent: Number(tp1),
          tp2_percent: Number(tp2),
          tp3_percent: Number(tp3),
          bep_trigger_level: Number(bepLevel),
          trailing_trigger_level: Number(trailingLevel),
        },
      });
      setSaveSuccessMsg('Strategy configuration successfully updated.');
      setTimeout(() => setSaveSuccessMsg(null), 5000);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setSaveErrorMsg(err.message);
      } else {
        setSaveErrorMsg('Failed to update strategy configuration.');
      }
      setTimeout(() => setSaveErrorMsg(null), 6000);
    }
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* 1. Take Profit Allocation Visualizer */}
      <div className="space-y-3 p-4 rounded-xl bg-surface/50 border border-border/60">
        <div className="flex items-center justify-between">
          <span className="font-bold text-slate-200 flex items-center gap-1.5">
            <Crosshair className="w-3.5 h-3.5 text-brand-400" />
            3-Stage Take Profit Allocation Distribution
          </span>

          {/* Status validation badge */}
          <Badge
            variant={is100Percent ? 'profit' : 'loss'}
            size="sm"
            className="font-bold gap-1"
          >
            {is100Percent ? (
              <>
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                Total: 100.0% (Valid)
              </>
            ) : (
              <>
                <AlertCircle className="w-3 h-3 text-rose-400" />
                Total: {totalAllocation.toFixed(1)}% (Must Equal 100%)
              </>
            )}
          </Badge>
        </div>

        {/* Proportional Colored Progress Bar */}
        <div className="h-3 rounded-full bg-slate-800 flex overflow-hidden border border-border/40">
          <div
            style={{ width: `${Math.min(100, Math.max(0, tp1))}%` }}
            className="bg-sky-500 transition-all duration-200"
            title={`TP1: ${tp1}%`}
          />
          <div
            style={{ width: `${Math.min(100, Math.max(0, tp2))}%` }}
            className="bg-indigo-500 transition-all duration-200"
            title={`TP2: ${tp2}%`}
          />
          <div
            style={{ width: `${Math.min(100, Math.max(0, tp3))}%` }}
            className="bg-emerald-500 transition-all duration-200"
            title={`TP3: ${tp3}%`}
          />
        </div>

        {/* Sliders Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
          {/* TP1 */}
          <div className="space-y-1.5 p-3 rounded-lg bg-surface/80 border border-sky-500/20">
            <div className="flex items-center justify-between text-xs">
              <span className="text-sky-400 font-bold">TP1 Target</span>
              <span className="text-white font-bold">{tp1}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={tp1}
              onChange={(e) => setTp1(parseFloat(e.target.value) || 0)}
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-sky-500"
            />
            <span className="text-[10px] text-slate-500 block">
              First profit target lock
            </span>
          </div>

          {/* TP2 */}
          <div className="space-y-1.5 p-3 rounded-lg bg-surface/80 border border-indigo-500/20">
            <div className="flex items-center justify-between text-xs">
              <span className="text-indigo-400 font-bold">TP2 Target</span>
              <span className="text-white font-bold">{tp2}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={tp2}
              onChange={(e) => setTp2(parseFloat(e.target.value) || 0)}
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-indigo-500"
            />
            <span className="text-[10px] text-slate-500 block">
              Runner position scaling
            </span>
          </div>

          {/* TP3 */}
          <div className="space-y-1.5 p-3 rounded-lg bg-surface/80 border border-emerald-500/20">
            <div className="flex items-center justify-between text-xs">
              <span className="text-emerald-400 font-bold">TP3 Target</span>
              <span className="text-white font-bold">{tp3}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={tp3}
              onChange={(e) => setTp3(parseFloat(e.target.value) || 0)}
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-emerald-500"
            />
            <span className="text-[10px] text-slate-500 block">
              Final target liquidation
            </span>
          </div>
        </div>
      </div>

      {/* 2. Break-Even & Trailing Stop Trigger Rules */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* BEP Trigger */}
        <div className="p-4 rounded-xl bg-surface/50 border border-border/60 space-y-3">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-brand-400" />
            <div>
              <h4 className="font-bold text-white text-xs">
                Break-Even Price (BEP) Trigger Level
              </h4>
              <p className="text-[10px] text-slate-400">
                Move Stop Loss to Entry price when this TP milestone is reached
              </p>
            </div>
          </div>

          <div className="flex gap-2">
            {[1, 2, 3].map((lvl) => (
              <button
                key={lvl}
                type="button"
                onClick={() => setBepLevel(lvl)}
                className={`flex-1 py-2 rounded-lg text-xs font-bold transition-all border ${
                  bepLevel === lvl
                    ? 'bg-brand-500 text-white border-brand-400 shadow-glow-brand'
                    : 'bg-surface/80 text-slate-400 border-border/70 hover:text-white'
                }`}
              >
                TP{lvl} Milestone
              </button>
            ))}
          </div>
        </div>

        {/* Trailing Stop Trigger */}
        <div className="p-4 rounded-xl bg-surface/50 border border-border/60 space-y-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <div>
              <h4 className="font-bold text-white text-xs">
                Dynamic Trailing Stop Trigger Level
              </h4>
              <p className="text-[10px] text-slate-400">
                Activate dynamic trailing profit protection once reached
              </p>
            </div>
          </div>

          <div className="flex gap-2">
            {[1, 2, 3].map((lvl) => (
              <button
                key={lvl}
                type="button"
                onClick={() => setTrailingLevel(lvl)}
                className={`flex-1 py-2 rounded-lg text-xs font-bold transition-all border ${
                  trailingLevel === lvl
                    ? 'bg-emerald-600 text-white border-emerald-400 shadow-glow-profit'
                    : 'bg-surface/80 text-slate-400 border-border/70 hover:text-white'
                }`}
              >
                TP{lvl} Milestone
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Feedback Notifications */}
      {saveSuccessMsg && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 text-xs animate-in fade-in-0">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{saveSuccessMsg}</span>
        </div>
      )}

      {saveErrorMsg && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs animate-in fade-in-0">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{saveErrorMsg}</span>
        </div>
      )}

      {/* Submit Action */}
      <div className="flex justify-end pt-2">
        <RoleGuard requiredRole="ADMIN" mode="disable">
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={!is100Percent || updateMutation.isPending}
            isLoading={updateMutation.isPending}
            className="gap-2 shadow-glow-brand"
          >
            {!updateMutation.isPending && <Save className="w-4 h-4" />}
            Save Strategy Rules
          </Button>
        </RoleGuard>
      </div>
    </form>
  );
}

export function StrategyConfigPanel() {
  const { data: strategies = [], isLoading, isError } = useStrategies();

  // Active strategy
  const activeStrategy = strategies[0];

  return (
    <Card className="glass-card w-full font-mono text-xs">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-brand-400" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              {activeStrategy?.name || 'Multi-Stage Take Profit Strategy'}
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Configure dynamic take profit distribution, break-even price triggers, and trailing stop levels
          </CardDescription>
        </div>

        {activeStrategy && (
          <Badge variant="profit" size="sm" className="font-bold">
            {activeStrategy.is_active ? 'LIVE ACTIVE STRATEGY' : 'INACTIVE'}
          </Badge>
        )}
      </CardHeader>

      <CardContent className="pt-4 space-y-6">
        {isLoading ? (
          <div className="p-8 text-center text-slate-400">
            <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping mr-2 inline-block" />
            Loading strategy rules...
          </div>
        ) : isError || !activeStrategy ? (
          <div className="p-6 rounded-lg bg-rose-950/20 border border-rose-800/40 text-center space-y-2">
            <AlertCircle className="w-6 h-6 text-rose-400 mx-auto" />
            <p className="text-xs text-slate-300">
              Failed to load strategy rules from backend.
            </p>
          </div>
        ) : (
          <StrategyConfigForm key={activeStrategy.id} strategy={activeStrategy} />
        )}
      </CardContent>
    </Card>
  );
}
