import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import { cn } from '@/utils/cn';
import { Info } from 'lucide-react';

export interface KPICardProps {
  title: string;
  value: React.ReactNode;
  icon: React.ReactNode;
  subText?: React.ReactNode;
  badge?: React.ReactNode;
  isWarning?: boolean;
  tooltip?: string;
  className?: string;
}

export function KPICard({
  title,
  value,
  icon,
  subText,
  badge,
  isWarning = false,
  tooltip,
  className,
}: KPICardProps) {
  return (
    <Card
      className={cn(
        'glass-card relative overflow-hidden transition-all duration-200 hover:border-slate-600/80',
        isWarning && 'border-amber-500/50 shadow-glow-warning animate-pulse',
        className
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-1.5 font-medium">
            <span>{title}</span>
            {tooltip && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="w-3.5 h-3.5 text-slate-500 hover:text-slate-300 cursor-pointer" />
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  <p className="text-xs max-w-xs leading-relaxed">{tooltip}</p>
                </TooltipContent>
              </Tooltip>
            )}
          </div>
          <div className="text-slate-400 shrink-0">{icon}</div>
        </div>

        <div className="flex items-baseline justify-between gap-2 mt-1">
          <CardTitle className="text-2xl font-mono font-bold tracking-tight text-white">
            {value}
          </CardTitle>
          {badge && <div className="shrink-0">{badge}</div>}
        </div>
      </CardHeader>

      {subText && (
        <CardContent className="pt-0 text-xs text-slate-400">
          {subText}
        </CardContent>
      )}
    </Card>
  );
}
