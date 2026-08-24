import * as React from 'react';
import { cn } from '@/utils/cn';

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?:
    | 'default'
    | 'profit'
    | 'profit-neon'
    | 'loss'
    | 'loss-neon'
    | 'warning'
    | 'info'
    | 'neutral'
    | 'outline'
    | 'admin'
    | 'viewer';
  size?: 'sm' | 'md';
}

function Badge({
  className,
  variant = 'default',
  size = 'md',
  ...props
}: BadgeProps) {
  const variantStyles = {
    default:
      'bg-slate-800 text-slate-200 border-slate-700',
    profit:
      'bg-emerald-950/80 text-emerald-400 border-emerald-800/60 shadow-sm',
    'profit-neon':
      'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 shadow-glow-profit',
    loss:
      'bg-rose-950/80 text-rose-400 border-rose-800/60 shadow-sm',
    'loss-neon':
      'bg-rose-500/20 text-rose-300 border-rose-500/50 shadow-glow-loss',
    warning:
      'bg-amber-950/80 text-amber-400 border-amber-800/60 shadow-sm',
    info:
      'bg-sky-950/80 text-sky-400 border-sky-800/60 shadow-sm',
    neutral:
      'bg-slate-800/60 text-slate-400 border-slate-700/50',
    outline:
      'border border-border text-slate-300 bg-transparent',
    admin:
      'bg-purple-950/80 text-purple-300 border-purple-800/60 font-semibold shadow-sm',
    viewer:
      'bg-blue-950/80 text-blue-300 border-blue-800/60 font-semibold shadow-sm',
  };

  const sizeStyles = {
    sm: 'px-2 py-0.5 text-[10px] leading-tight font-medium',
    md: 'px-2.5 py-1 text-xs font-medium',
  };

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1 rounded-full border transition-colors select-none font-mono',
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      {...props}
    />
  );
}

export { Badge };
