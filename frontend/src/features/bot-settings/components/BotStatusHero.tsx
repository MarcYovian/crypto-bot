import { BotStatusDTO } from '@/types/bot';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDateTime } from '@/utils/format';
import {
  Zap,
  Radio,
  Clock,
  ShieldCheck,
  ShieldAlert,
  Server,
} from 'lucide-react';

export interface BotStatusHeroProps {
  status?: BotStatusDTO | null;
  isLoading?: boolean;
}

export function BotStatusHero({ status, isLoading = false }: BotStatusHeroProps) {
  if (isLoading || !status) {
    return (
      <Card className="glass-card p-6 border-brand-500/20 font-mono animate-pulse">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 rounded-full bg-slate-700" />
          <div className="h-5 w-48 bg-slate-800 rounded" />
        </div>
      </Card>
    );
  }

  const isRunning = status.is_running && !status.is_paused;
  const isCircuitBreakerTripped = status.circuit_breaker_active;

  return (
    <Card className="glass-card p-5 font-mono text-xs border-brand-500/30 space-y-4">
      {/* Top Banner Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div className="flex items-center gap-3">
          <div className="relative flex h-4 w-4">
            {isRunning && !isCircuitBreakerTripped && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            )}
            <span
              className={`relative inline-flex rounded-full h-4 w-4 ${
                isCircuitBreakerTripped
                  ? 'bg-rose-500'
                  : isRunning
                  ? 'bg-emerald-500'
                  : 'bg-amber-500'
              }`}
            />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-tight">
                Bot Engine Runtime:
              </h2>
              <Badge
                variant={
                  isCircuitBreakerTripped
                    ? 'loss'
                    : isRunning
                    ? 'profit'
                    : 'warning'
                }
                size="md"
                className="font-bold gap-1 shadow-sm"
              >
                {isCircuitBreakerTripped
                  ? '🚨 CIRCUIT BREAKER TRIPPED'
                  : isRunning
                  ? '🟢 ACTIVE / RUNNING'
                  : '🟡 PAUSED'}
              </Badge>
            </div>
            <p className="text-slate-400 text-[11px] mt-0.5">
              High-frequency Binance Futures execution core with real-time risk guards
            </p>
          </div>
        </div>

        {/* Heartbeat Badge */}
        <div className="flex items-center gap-1.5 text-slate-400 text-[11px] bg-surface/70 px-3 py-1.5 rounded-lg border border-border/60">
          <Clock className="w-3.5 h-3.5 text-brand-400" />
          <span>Heartbeat:</span>
          <span className="text-slate-200 font-bold">
            {status.last_heartbeat
              ? formatDateTime(status.last_heartbeat)
              : 'Live'}
          </span>
        </div>
      </div>

      {/* Circuit Breaker Critical Alert (if tripped) */}
      {isCircuitBreakerTripped && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-600/70 text-rose-300 space-y-1 animate-pulse">
          <div className="flex items-center gap-2 font-bold text-sm text-rose-200">
            <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0" />
            <span>DAILY LOSS LIMIT REACHED - TRADING HALTED</span>
          </div>
          <p className="text-xs text-rose-300/90 leading-relaxed">
            The automated circuit breaker was triggered because daily realized losses exceeded the strict risk threshold. Incoming signals are automatically discarded until an Admin resumes the engine.
          </p>
        </div>
      )}

      {/* 4 Health Service Status Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {/* 1. Binance WebSocket User Data */}
        <div className="p-3 rounded-lg bg-surface/60 border border-border/60 flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              status.binance_ws_connected
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
            }`}
          >
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase">
              Binance WebSocket
            </span>
            <span
              className={`font-bold text-xs ${
                status.binance_ws_connected
                  ? 'text-emerald-400'
                  : 'text-rose-400'
              }`}
            >
              {status.binance_ws_connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>

        {/* 2. Telegram Polling Ingestion */}
        <div className="p-3 rounded-lg bg-surface/60 border border-border/60 flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              status.telegram_polling_active
                ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                : 'bg-slate-800 text-slate-500 border border-border/40'
            }`}
          >
            <Radio className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase">
              Telegram Feed
            </span>
            <span
              className={`font-bold text-xs ${
                status.telegram_polling_active
                  ? 'text-sky-400'
                  : 'text-slate-500'
              }`}
            >
              {status.telegram_polling_active ? 'Polling Active' : 'Idle'}
            </span>
          </div>
        </div>

        {/* 3. Background Cron Scheduler */}
        <div className="p-3 rounded-lg bg-surface/60 border border-border/60 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center justify-center">
            <Server className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase">
              Cron Scheduler
            </span>
            <span className="font-bold text-xs text-indigo-300">
              {status.scheduler_jobs_count} Jobs Active
            </span>
          </div>
        </div>

        {/* 4. Circuit Breaker Guard */}
        <div className="p-3 rounded-lg bg-surface/60 border border-border/60 flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              !status.circuit_breaker_active
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
            }`}
          >
            {status.circuit_breaker_active ? (
              <ShieldAlert className="w-4 h-4" />
            ) : (
              <ShieldCheck className="w-4 h-4" />
            )}
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase">
              Circuit Breaker
            </span>
            <span
              className={`font-bold text-xs ${
                status.circuit_breaker_active
                  ? 'text-rose-400'
                  : 'text-emerald-400'
              }`}
            >
              {status.circuit_breaker_active ? 'TRIPPED' : 'Normal (Armed)'}
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
}
