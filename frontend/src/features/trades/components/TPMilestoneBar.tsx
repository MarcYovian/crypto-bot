import { ActiveTradeTPLevelDTO } from '@/types/trades';
import { formatUSDT } from '@/utils/format';
import { cn } from '@/utils/cn';
import { CheckCircle2, Circle } from 'lucide-react';

export interface TPMilestoneBarProps {
  tpLevels?: ActiveTradeTPLevelDTO[];
  className?: string;
}

const TP_VOLUME_WEIGHTS: Record<number, string> = {
  1: '50%',
  2: '30%',
  3: '20%',
};

export function TPMilestoneBar({ tpLevels = [], className }: TPMilestoneBarProps) {
  if (!tpLevels || tpLevels.length === 0) {
    return <span className="text-xs text-slate-500 font-mono">-</span>;
  }

  // Sort by level ascending 1 -> 2 -> 3
  const sortedLevels = [...tpLevels].sort((a, b) => a.level - b.level);

  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      {sortedLevels.map((tp) => {
        const weight = TP_VOLUME_WEIGHTS[tp.level] || '';
        return (
          <div
            key={tp.level}
            title={`TP${tp.level} (${weight}) - ${formatUSDT(tp.price)}: ${
              tp.is_hit ? 'HIT' : 'PENDING'
            }`}
            className={cn(
              'flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border transition-all duration-200 select-none',
              tp.is_hit
                ? 'bg-emerald-950/60 border-emerald-500/50 text-emerald-300 shadow-glow-profit animate-in zoom-in-95 duration-150'
                : 'bg-surface/50 border-border/60 text-slate-400 hover:border-slate-500'
            )}
          >
            {tp.is_hit ? (
              <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
            ) : (
              <Circle className="w-2.5 h-2.5 text-slate-500 shrink-0" />
            )}
            <span className="font-semibold">TP{tp.level}</span>
            <span className="text-[9px] opacity-75">{weight}</span>
          </div>
        );
      })}
    </div>
  );
}
