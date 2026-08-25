import { useState } from 'react';
import { NavRoute } from './Sidebar';
import {
  LayoutDashboard,
  Zap,
  Radio,
  ShieldAlert,
  Menu,
  X,
  History,
  Eye,
  Sliders,
  Calculator,
  FileText,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export interface MobileNavProps {
  currentRoute: NavRoute;
  onRouteChange: (route: NavRoute) => void;
}

interface MobileShortcut {
  id: NavRoute;
  label: string;
  icon: typeof LayoutDashboard;
}

const PRIMARY_SHORTCUTS: MobileShortcut[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'active-trades', label: 'Trades', icon: Zap },
  { id: 'signals', label: 'Signals', icon: Radio },
  { id: 'operations', label: 'Bot Ops', icon: ShieldAlert },
];

const ALL_NAV_ITEMS: { id: NavRoute; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Dashboard Overview', icon: LayoutDashboard },
  { id: 'active-trades', label: 'Active Trades & Positions', icon: Zap },
  { id: 'history', label: 'Closed Trade History', icon: History },
  { id: 'signals', label: 'Signal Feed & Execution', icon: Radio },
  { id: 'watchlist', label: 'Watchlist & Instruments', icon: Eye },
  { id: 'strategies', label: 'Strategy Configuration', icon: Sliders },
  { id: 'simulator', label: 'Risk Simulator Sandbox', icon: Calculator },
  { id: 'operations', label: 'Bot Operations & Credentials', icon: ShieldAlert },
  { id: 'logs', label: 'System Logs & Reports', icon: FileText },
];

export function MobileNav({ currentRoute, onRouteChange }: MobileNavProps) {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const handleSelectRoute = (route: NavRoute) => {
    onRouteChange(route);
    setIsDrawerOpen(false);
  };

  return (
    <>
      {/* 1. Full Navigation Drawer Backdrop & Modal */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden bg-black/80 backdrop-blur-sm animate-in fade-in-0 flex flex-col justify-end">
          <div className="bg-surface/95 border-t border-border/80 rounded-t-2xl p-4 space-y-3 font-mono text-xs max-h-[80vh] overflow-y-auto custom-scrollbar shadow-2xl">
            <div className="flex items-center justify-between pb-2 border-b border-border/50">
              <span className="font-bold text-white text-sm">
                Terminal Navigation Menu
              </span>
              <button
                type="button"
                onClick={() => setIsDrawerOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg bg-surface"
                aria-label="Close navigation drawer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-1.5 pt-1">
              {ALL_NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive = currentRoute === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleSelectRoute(item.id)}
                    className={cn(
                      'flex items-center gap-3 p-2.5 rounded-xl font-bold transition-all text-left border',
                      isActive
                        ? 'bg-brand-500/20 text-brand-300 border-brand-500/50 shadow-glow-brand'
                        : 'bg-surface/60 text-slate-300 border-border/60 hover:text-white'
                    )}
                  >
                    <Icon
                      className={cn(
                        'w-4 h-4 shrink-0',
                        isActive ? 'text-brand-400' : 'text-slate-400'
                      )}
                    />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 2. Fixed Bottom Navigation Bar */}
      <nav
        aria-label="Mobile Navigation Bar"
        className="fixed bottom-0 left-0 right-0 z-40 md:hidden bg-surface/95 backdrop-blur-md border-t border-border/70 py-1.5 px-3 flex items-center justify-around font-mono text-[10px] select-none"
      >
        {PRIMARY_SHORTCUTS.map((item) => {
          const Icon = item.icon;
          const isActive = currentRoute === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onRouteChange(item.id)}
              className={cn(
                'flex flex-col items-center gap-1 py-1 px-2 rounded-lg transition-all',
                isActive
                  ? 'text-brand-400 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              )}
            >
              <Icon
                className={cn(
                  'w-4 h-4',
                  isActive ? 'text-brand-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.5)]' : 'text-slate-400'
                )}
              />
              <span>{item.label}</span>
            </button>
          );
        })}

        {/* More Menu Drawer Trigger */}
        <button
          type="button"
          onClick={() => setIsDrawerOpen(true)}
          className={cn(
            'flex flex-col items-center gap-1 py-1 px-2 rounded-lg transition-all text-slate-400 hover:text-slate-200',
            isDrawerOpen && 'text-brand-400'
          )}
        >
          <Menu className="w-4 h-4" />
          <span>More</span>
        </button>
      </nav>
    </>
  );
}
