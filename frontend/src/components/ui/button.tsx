import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { Loader2 } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
  variant?:
    | 'primary'
    | 'secondary'
    | 'danger'
    | 'outline'
    | 'ghost'
    | 'neon-profit'
    | 'warning';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  isLoading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'primary',
      size = 'md',
      isLoading = false,
      disabled,
      asChild = false,
      children,
      ...props
    },
    ref
  ) => {
    const Comp = asChild ? Slot : 'button';

    const baseStyles =
      'inline-flex items-center justify-center font-medium transition-all duration-150 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-50 disabled:cursor-not-allowed select-none active:scale-[0.98]';

    const variantStyles = {
      primary:
        'bg-brand-500 hover:bg-brand-600 text-white shadow-sm hover:shadow-glow-brand focus-visible:ring-brand-400',
      secondary:
        'bg-card hover:bg-card-hover text-slate-200 border border-border focus-visible:ring-slate-400',
      danger:
        'bg-trading-loss hover:bg-red-600 text-white shadow-sm hover:shadow-glow-loss focus-visible:ring-red-400',
      'neon-profit':
        'bg-trading-profit hover:bg-emerald-600 text-slate-950 font-semibold shadow-sm hover:shadow-glow-profit focus-visible:ring-emerald-400',
      warning:
        'bg-trading-warning hover:bg-amber-600 text-slate-950 font-semibold shadow-sm hover:shadow-glow-warning focus-visible:ring-amber-400',
      outline:
        'border border-border bg-transparent hover:bg-card hover:text-white text-slate-300 focus-visible:ring-brand-400',
      ghost:
        'bg-transparent hover:bg-card text-slate-300 hover:text-white focus-visible:ring-slate-400',
    };

    const sizeStyles = {
      sm: 'h-8 px-3 text-xs gap-1.5',
      md: 'h-9 px-4 text-sm gap-2',
      lg: 'h-11 px-6 text-base gap-2.5',
      icon: 'h-9 w-9 p-0',
    };

    return (
      <Comp
        className={cn(
          baseStyles,
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        ref={ref}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin text-current" />
            <span>{children}</span>
          </>
        ) : (
          children
        )}
      </Comp>
    );
  }
);

Button.displayName = 'Button';

export { Button };
