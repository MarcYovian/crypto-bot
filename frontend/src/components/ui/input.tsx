import * as React from 'react';
import { cn } from '@/utils/cn';

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  prefixNode?: React.ReactNode;
  suffixNode?: React.ReactNode;
  isError?: boolean;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, prefixNode, suffixNode, isError, ...props }, ref) => {
    return (
      <div className="relative flex items-center w-full">
        {prefixNode && (
          <div className="absolute left-3 z-10 flex items-center pointer-events-none text-slate-400 text-xs font-mono">
            {prefixNode}
          </div>
        )}
        <input
          type={type}
          className={cn(
            'flex h-9 w-full rounded-lg border bg-surface/90 px-3 py-1.5 text-sm text-slate-100 placeholder:text-slate-500 transition-all duration-150',
            'border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:border-transparent',
            'disabled:cursor-not-allowed disabled:opacity-50',
            prefixNode && 'pl-9',
            suffixNode && 'pr-9',
            isError &&
              'border-trading-loss focus-visible:ring-trading-loss bg-rose-950/10',
            className
          )}
          ref={ref}
          {...props}
        />
        {suffixNode && (
          <div className="absolute right-3 z-10 flex items-center pointer-events-none text-slate-400 text-xs font-mono">
            {suffixNode}
          </div>
        )}
      </div>
    );
  }
);
Input.displayName = 'Input';

export { Input };
