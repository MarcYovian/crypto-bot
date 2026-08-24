import { useToastStore, ToastItem } from '@/stores/toastStore';
import {
  CheckCircle2,
  AlertTriangle,
  Info,
  Flame,
  X,
} from 'lucide-react';
import { cn } from '@/utils/cn';

function ToastElement({ toast }: { toast: ToastItem }) {
  const removeToast = useToastStore((s) => s.removeToast);

  const getVariantStyles = (variant: ToastItem['variant']) => {
    switch (variant) {
      case 'profit':
        return {
          icon: <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />,
          container:
            'bg-surface/95 border-emerald-500/60 text-emerald-100 shadow-glow-profit',
          title: 'text-emerald-300 font-bold',
        };
      case 'loss':
        return {
          icon: <Flame className="w-5 h-5 text-rose-400 shrink-0 animate-pulse" />,
          container:
            'bg-surface/95 border-rose-500/60 text-rose-100 shadow-glow-loss',
          title: 'text-rose-300 font-bold',
        };
      case 'warning':
        return {
          icon: <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />,
          container:
            'bg-surface/95 border-amber-500/60 text-amber-100 shadow-glow-warning',
          title: 'text-amber-300 font-bold',
        };
      case 'info':
      default:
        return {
          icon: <Info className="w-5 h-5 text-sky-400 shrink-0" />,
          container:
            'bg-surface/95 border-sky-500/60 text-sky-100 shadow-glow-brand',
          title: 'text-sky-300 font-bold',
        };
    }
  };

  const style = getVariantStyles(toast.variant);

  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-3 p-3.5 rounded-xl border backdrop-blur-md font-mono text-xs shadow-2xl transition-all duration-200 animate-in slide-in-from-top-4 sm:slide-in-from-bottom-4 max-w-sm w-full pointer-events-auto',
        style.container
      )}
    >
      {style.icon}
      <div className="flex-1 space-y-0.5 min-w-0">
        <h4 className={cn('text-xs tracking-tight', style.title)}>
          {toast.title}
        </h4>
        {toast.message && (
          <p className="text-[11px] text-slate-300 leading-snug break-words">
            {toast.message}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={() => removeToast(toast.id)}
        className="text-slate-400 hover:text-white transition-colors p-0.5 rounded"
        aria-label="Dismiss toast"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export function ToastProvider() {
  const toasts = useToastStore((s) => s.toasts);

  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none max-w-sm w-full px-4 sm:px-0"
    >
      {toasts.map((t) => (
        <ToastElement key={t.id} toast={t} />
      ))}
    </div>
  );
}
