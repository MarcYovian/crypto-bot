import { Radio } from 'lucide-react';

export function EmptyPositionsState() {
  return (
    <div className="py-12 px-4 text-center flex flex-col items-center justify-center space-y-3 bg-surface/30 border border-dashed border-border/60 rounded-xl">
      <div className="w-12 h-12 rounded-full bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-brand-400">
        <Radio className="w-6 h-6 animate-pulse" />
      </div>
      <div>
        <h4 className="text-sm font-bold text-white tracking-tight">
          No Active Positions
        </h4>
        <p className="text-xs text-slate-400 mt-1 max-w-sm">
          Trading engine is standing by and monitoring instruments for valid SMC setup signals.
        </p>
      </div>
    </div>
  );
}
