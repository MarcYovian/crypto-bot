import { useAuthStore } from '@/stores/authStore';
import { useWebSocketStore } from '@/stores/wsStore';
import { useQuery } from '@tanstack/react-query';
import { getAnalyticsSummaryApi } from '@/api/endpoints/analytics';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatUSDT } from '@/utils/format';
import {
  Zap,
  Radio,
  LogOut,
  User as UserIcon,
  Shield,
} from 'lucide-react';

export function Navbar() {
  const { user, logout } = useAuthStore();
  const { status } = useWebSocketStore();

  const isConnected = status === 'CONNECTED';
  const isConnecting = status === 'RECONNECTING';

  const { data: analytics } = useQuery({
    queryKey: ['analytics', 'summary'],
    queryFn: () => getAnalyticsSummaryApi(1),
    staleTime: 10000,
  });

  const totalBalance = analytics?.total_balance_usdt || 10000.0;
  const isProfit = (analytics?.daily_realized_pnl || 0) >= 0;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/70 bg-surface/90 backdrop-blur-md px-4 sm:px-6 py-2.5 flex items-center justify-between font-sans">
      {/* Brand & Bot Hero Status */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-brand-600 to-sky-400 p-0.5 shadow-glow">
            <div className="w-full h-full bg-surface rounded-[7px] flex items-center justify-center">
              <Zap className="w-4 h-4 text-brand-400 fill-brand-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-1.5 leading-none">
              <span className="font-extrabold text-sm tracking-tight text-white">
                SMC<span className="text-brand-400">Bot</span>
              </span>
              <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">
                v2.0 PRO
              </span>
            </div>
            <span className="text-[10px] text-slate-400 hidden sm:block">
              Binance Futures Terminal
            </span>
          </div>
        </div>

        <div className="h-5 w-px bg-border/60 mx-1 hidden sm:block" />

        {/* Bot Engine Status Hero */}
        <div className="hidden sm:flex items-center gap-1.5 bg-surface/80 border border-emerald-900/40 px-2.5 py-1 rounded-full">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="text-[11px] font-mono font-bold text-emerald-400 tracking-wide">
            ENGINE RUNNING
          </span>
        </div>
      </div>

      {/* Right Stats & Profile Area */}
      <div className="flex items-center gap-3 sm:gap-4 font-mono">
        {/* Real-time WebSocket Connection Badge */}
        <div className="flex items-center gap-1.5 bg-surface/60 border border-border/60 px-2 py-1 rounded-lg text-xs">
          <Radio
            className={`w-3 h-3 ${
              isConnected
                ? 'text-emerald-400 animate-pulse'
                : isConnecting
                ? 'text-amber-400 animate-spin'
                : 'text-rose-400'
            }`}
          />
          <span className="text-[10px] hidden md:inline text-slate-400">WS:</span>
          <span
            className={`text-[10px] font-bold ${
              isConnected
                ? 'text-emerald-400'
                : isConnecting
                ? 'text-amber-400'
                : 'text-rose-400'
            }`}
          >
            {isConnected ? 'LIVE' : isConnecting ? 'SYNCING' : 'OFFLINE'}
          </span>
        </div>

        {/* Live Total Balance Hero */}
        <div className="flex flex-col items-end pl-2">
          <span className="text-[10px] text-slate-400 font-sans leading-none">
            Total Balance
          </span>
          <div className="flex items-center gap-1.5 leading-tight">
            <span className="text-sm sm:text-base font-bold text-white tracking-wide">
              {formatUSDT(totalBalance)}
            </span>
            <span
              className={`text-[10px] font-semibold hidden sm:inline ${
                isProfit ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {analytics?.daily_realized_pnl && analytics.daily_realized_pnl !== 0
                ? `${isProfit ? '+' : ''}${formatUSDT(analytics.daily_realized_pnl)}`
                : ''}
            </span>
          </div>
        </div>

        {/* User Profile & Role Guard */}
        <div className="flex items-center gap-2 pl-2 border-l border-border/60">
          <div className="hidden lg:flex flex-col items-end leading-tight font-sans">
            <div className="flex items-center gap-1">
              <UserIcon className="w-3 h-3 text-slate-400" />
              <span className="text-xs font-semibold text-slate-200">
                {user?.username || 'Trader'}
              </span>
            </div>
            <Badge
              variant={user?.role === 'ADMIN' ? 'admin' : 'viewer'}
              size="sm"
              className="text-[9px] px-1 py-0 h-4 mt-0.5"
            >
              <Shield className="w-2.5 h-2.5 mr-0.5" />
              {user?.role || 'VIEWER'}
            </Badge>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={logout}
            title="Sign Out"
            className="h-8 w-8 p-0 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </header>
  );
}
