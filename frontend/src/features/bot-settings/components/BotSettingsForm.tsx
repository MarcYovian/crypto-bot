import { useState } from 'react';
import { useBotSettings, useUpdateSettingsMutation } from '@/hooks/useBotOperations';
import { BotSettingsDTO, BotSettingsUpdateRequestDTO } from '@/types/bot';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RoleGuard } from '@/features/auth/RoleGuard';
import {
  Sliders,
  Shield,
  Save,
  CheckCircle2,
  AlertCircle,
  Percent,
  TrendingDown,
  Layers,
  Sparkles,
} from 'lucide-react';

interface BotSettingsFormFieldsProps {
  settings: BotSettingsDTO;
}

function BotSettingsFormFields({ settings }: BotSettingsFormFieldsProps) {
  const [formData, setFormData] = useState<BotSettingsUpdateRequestDTO>({
    default_leverage: settings.default_leverage || 20,
    confidence_threshold: settings.confidence_threshold || 0.7,
    risk_percent_per_trade: settings.risk_percent_per_trade || 2.0,
    max_daily_loss_percent: settings.max_daily_loss_percent || 6.0,
    max_open_trades: settings.max_open_trades || 3,
  });

  const [feedback, setFeedback] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  const updateMutation = useUpdateSettingsMutation();

  const handleFieldChange = <K extends keyof BotSettingsUpdateRequestDTO>(
    key: K,
    val: BotSettingsUpdateRequestDTO[K]
  ) => {
    setFormData((prev) => ({ ...prev, [key]: val }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (updateMutation.isPending) return;

    setFeedback(null);
    try {
      await updateMutation.mutateAsync(formData);
      setFeedback({
        type: 'success',
        text: 'Bot configuration settings successfully saved and applied to live engine.',
      });
      setTimeout(() => setFeedback(null), 5000);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setFeedback({ type: 'error', text: err.message });
      } else {
        setFeedback({ type: 'error', text: 'Failed to update bot configuration.' });
      }
      setTimeout(() => setFeedback(null), 6000);
    }
  };

  return (
    <form onSubmit={handleSave} className="space-y-4">
      {/* 2-Column Settings Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 1. Default Leverage */}
        <div className="p-4 rounded-xl bg-surface/50 border border-border/60 space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-slate-300 font-bold flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Default Leverage
            </label>
            <Badge variant="outline" size="sm" className="font-bold text-amber-300">
              {formData.default_leverage}x
            </Badge>
          </div>
          <p className="text-[10px] text-slate-400">
            Initial leverage applied to incoming market orders
          </p>
          <div className="flex items-center gap-2 pt-1">
            <input
              type="range"
              min="1"
              max="125"
              step="1"
              value={formData.default_leverage}
              onChange={(e) =>
                handleFieldChange('default_leverage', parseInt(e.target.value) || 1)
              }
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-amber-500"
            />
            <Input
              type="number"
              min="1"
              max="125"
              value={formData.default_leverage}
              onChange={(e) =>
                handleFieldChange('default_leverage', parseInt(e.target.value) || 1)
              }
              className="w-16 h-8 text-center bg-surface/80 border-border/80 font-bold text-xs"
            />
          </div>
        </div>

        {/* 2. Confidence Threshold */}
        <div className="p-4 rounded-xl bg-surface/50 border border-border/60 space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-slate-300 font-bold flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-sky-400" /> AI Confidence Threshold
            </label>
            <Badge variant="outline" size="sm" className="font-bold text-sky-300">
              {(formData.confidence_threshold ?? 0).toFixed(2)}
            </Badge>
          </div>
          <p className="text-[10px] text-slate-400">
            Minimum parsed signal confidence score required for auto-execution
          </p>
          <div className="flex items-center gap-2 pt-1">
            <input
              type="range"
              min="0.10"
              max="1.00"
              step="0.05"
              value={formData.confidence_threshold}
              onChange={(e) =>
                handleFieldChange(
                  'confidence_threshold',
                  parseFloat(e.target.value) || 0.5
                )
              }
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-sky-500"
            />
            <Input
              type="number"
              min="0.10"
              max="1.00"
              step="0.05"
              value={formData.confidence_threshold}
              onChange={(e) =>
                handleFieldChange(
                  'confidence_threshold',
                  parseFloat(e.target.value) || 0.5
                )
              }
              className="w-16 h-8 text-center bg-surface/80 border-border/80 font-bold text-xs"
            />
          </div>
        </div>

        {/* 3. Risk Percent Per Trade */}
        <div className="p-4 rounded-xl bg-surface/50 border border-border/60 space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-slate-300 font-bold flex items-center gap-1.5">
              <Percent className="w-3.5 h-3.5 text-emerald-400" /> Risk Per Trade
            </label>
            <Badge variant="profit" size="sm" className="font-bold">
              {(formData.risk_percent_per_trade ?? 0).toFixed(1)}% of Equity
            </Badge>
          </div>
          <p className="text-[10px] text-slate-400">
            Strict position sizing loss budget at Stop Loss (Default 2.0%)
          </p>
          <div className="flex items-center gap-2 pt-1">
            <input
              type="range"
              min="0.1"
              max="10.0"
              step="0.1"
              value={formData.risk_percent_per_trade}
              onChange={(e) =>
                handleFieldChange(
                  'risk_percent_per_trade',
                  parseFloat(e.target.value) || 0.5
                )
              }
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-emerald-500"
            />
            <Input
              type="number"
              min="0.1"
              max="10.0"
              step="0.1"
              value={formData.risk_percent_per_trade}
              onChange={(e) =>
                handleFieldChange(
                  'risk_percent_per_trade',
                  parseFloat(e.target.value) || 0.5
                )
              }
              className="w-16 h-8 text-center bg-surface/80 border-border/80 font-bold text-xs"
            />
          </div>
        </div>

        {/* 4. Max Daily Loss Percent */}
        <div className="p-4 rounded-xl bg-surface/50 border border-border/60 space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-slate-300 font-bold flex items-center gap-1.5">
              <TrendingDown className="w-3.5 h-3.5 text-rose-400" /> Max Daily Loss (Circuit Breaker)
            </label>
            <Badge variant="loss" size="sm" className="font-bold">
              {(formData.max_daily_loss_percent ?? 0).toFixed(1)}% Limit
            </Badge>
          </div>
          <p className="text-[10px] text-slate-400">
            Automatically trips circuit breaker & pauses engine when reached
          </p>
          <div className="flex items-center gap-2 pt-1">
            <input
              type="range"
              min="1.0"
              max="20.0"
              step="0.5"
              value={formData.max_daily_loss_percent}
              onChange={(e) =>
                handleFieldChange(
                  'max_daily_loss_percent',
                  parseFloat(e.target.value) || 1.0
                )
              }
              className="w-full h-1.5 bg-slate-700 rounded appearance-none cursor-pointer accent-rose-500"
            />
            <Input
              type="number"
              min="1.0"
              max="20.0"
              step="0.5"
              value={formData.max_daily_loss_percent}
              onChange={(e) =>
                handleFieldChange(
                  'max_daily_loss_percent',
                  parseFloat(e.target.value) || 1.0
                )
              }
              className="w-16 h-8 text-center bg-surface/80 border-border/80 font-bold text-xs"
            />
          </div>
        </div>
      </div>

      {/* Max Concurrent Open Trades */}
      <div className="p-4 rounded-xl bg-surface/50 border border-border/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <label className="text-slate-300 font-bold flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-brand-400" /> Maximum Concurrent Open Positions
          </label>
          <p className="text-[10px] text-slate-400 mt-0.5">
            Limits active market exposure to prevent over-allocation (Max 10)
          </p>
        </div>

        <div className="flex items-center gap-2">
          {[1, 2, 3, 4, 5, 8, 10].map((num) => (
            <button
              key={num}
              type="button"
              onClick={() => handleFieldChange('max_open_trades', num)}
              className={`w-8 h-8 rounded-lg font-bold text-xs transition-all border ${
                formData.max_open_trades === num
                  ? 'bg-brand-500 text-white border-brand-400 shadow-glow-brand'
                  : 'bg-surface/80 text-slate-400 border-border/70 hover:text-white'
              }`}
            >
              {num}
            </button>
          ))}
        </div>
      </div>

      {/* Feedback Toast */}
      {feedback && (
        <div
          className={`flex items-center gap-2 p-3 rounded-lg border text-xs animate-in fade-in-0 ${
            feedback.type === 'success'
              ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
              : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
          }`}
        >
          {feedback.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          )}
          <span>{feedback.text}</span>
        </div>
      )}

      {/* Submit Button */}
      <div className="flex justify-end pt-2">
        <RoleGuard requiredRole="ADMIN" mode="disable">
          <Button
            type="submit"
            variant="primary"
            size="md"
            isLoading={updateMutation.isPending}
            disabled={updateMutation.isPending}
            className="gap-2 shadow-glow-brand"
          >
            {!updateMutation.isPending && <Save className="w-4 h-4" />}
            Save Bot Settings
          </Button>
        </RoleGuard>
      </div>
    </form>
  );
}

export function BotSettingsForm() {
  const { data: settings, isLoading, isError } = useBotSettings();

  return (
    <Card className="glass-card font-mono text-xs w-full">
      <CardHeader className="pb-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-brand-400" />
          <CardTitle className="text-base font-bold text-white tracking-tight">
            Dynamic Bot Configuration & Risk Profile
          </CardTitle>
        </div>
        <CardDescription className="text-xs text-slate-400 mt-0.5">
          Tune leverage defaults, AI signal thresholds, and automatic circuit breaker limits
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-4">
        {isLoading ? (
          <div className="p-8 text-center text-slate-400">
            <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping mr-2 inline-block" />
            Loading bot settings...
          </div>
        ) : isError || !settings ? (
          <div className="p-6 rounded-lg bg-rose-950/20 border border-rose-800/40 text-center space-y-2">
            <AlertCircle className="w-6 h-6 text-rose-400 mx-auto" />
            <p className="text-xs text-slate-300">
              Failed to load bot settings from backend.
            </p>
          </div>
        ) : (
          <BotSettingsFormFields key={JSON.stringify(settings)} settings={settings} />
        )}
      </CardContent>
    </Card>
  );
}
