import { useState } from 'react';
import {
  LayoutDashboard,
  Zap,
  History,
  Radio,
  Eye,
  Sliders,
  Calculator,
  ShieldAlert,
  FileText,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export type NavRoute =
  | 'overview'
  | 'active-trades'
  | 'history'
  | 'signals'
  | 'watchlist'
  | 'strategies'
  | 'simulator'
  | 'operations'
  | 'logs';

export interface SidebarProps {
  currentRoute: NavRoute;
  onRouteChange: (route: NavRoute) => void;
}

interface NavItem {
  id: NavRoute;
  label: string;
  icon: typeof LayoutDashboard;
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'active-trades', label: 'Active Trades', icon: Zap },
  { id: 'history', label: 'Trade History', icon: History },
  { id: 'signals', label: 'Signal Feed', icon: Radio },
  { id: 'watchlist', label: 'Watchlist', icon: Eye },
  { id: 'strategies', label: 'Strategies', icon: Sliders },
  { id: 'simulator', label: 'Risk Simulator', icon: Calculator },
  { id: 'operations', label: 'Bot Operations', icon: ShieldAlert },
  { id: 'logs', label: 'Logs & Reports', icon: FileText },
];

export function Sidebar({ currentRoute, onRouteChange }: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        'sticky top-[57px] z-30 h-[calc(100vh-57px)] border-r border-border/70 bg-surface/95 backdrop-blur-md transition-all duration-300 flex flex-col justify-between select-none font-sans shrink-0',
        isCollapsed ? 'w-16' : 'w-56 lg:w-60'
      )}
    >
      {/* Navigation Links */}
      <div className="p-3 space-y-1 overflow-y-auto custom-scrollbar">
        {!isCollapsed && (
          <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500 font-mono">
            Navigation Menu
          </div>
        )}

        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = currentRoute === item.id;

            return (
              <button
                key={item.id}
                onClick={() => onRouteChange(item.id)}
                title={isCollapsed ? item.label : undefined}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-all group relative',
                  isActive
                    ? 'bg-brand-500/15 text-brand-400 border border-brand-500/30 shadow-glow font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-surface/80 border border-transparent'
                )}
              >
                {/* Active Neon Bar Indicator */}
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-r bg-brand-400 shadow-glow" />
                )}

                <Icon
                  className={cn(
                    'w-4 h-4 shrink-0 transition-transform group-hover:scale-110',
                    isActive ? 'text-brand-400' : 'text-slate-400'
                  )}
                />

                {!isCollapsed && (
                  <span className="truncate tracking-wide">{item.label}</span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Collapse / Expand Toggle Button */}
      <div className="p-3 border-t border-border/60">
        <button
          onClick={() => setIsCollapsed((prev) => !prev)}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-slate-400 hover:text-white hover:bg-surface/80 text-xs transition-colors border border-border/40 font-mono"
        >
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span className="text-[11px]">Collapse Rail</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
