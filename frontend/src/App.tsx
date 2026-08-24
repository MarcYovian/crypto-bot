import { useState } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { AuthGuard } from '@/features/auth';
import { AppLayout } from '@/components/layout/AppLayout';
import { NavRoute } from '@/components/layout/Sidebar';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ExecutiveDashboardPage } from '@/features/dashboard';
import { ActiveTradesPage, TradeHistoryPage } from '@/features/trades';
import { SignalsFeedPage } from '@/features/signals';
import { WatchlistPage } from '@/features/watchlist';
import { StrategiesPage } from '@/features/strategies';
import { RiskSimulatorPage } from '@/features/calculator';
import { BotOperationsPage } from '@/features/bot-settings';
import { LogsAndReportsPage } from '@/features/logs-reports';

export default function App() {
  // Initialize Duplex Real-Time WebSocket stream
  useWebSocket();

  const [currentRoute, setCurrentRoute] = useState<NavRoute>('overview');

  const renderCurrentView = () => {
    switch (currentRoute) {
      case 'overview':
        return <ExecutiveDashboardPage />;
      case 'active-trades':
        return (
          <div className="space-y-4">
            <h1 className="text-xl font-bold tracking-tight text-white font-mono">
              Live Active Positions & Take Profit Milestone Tracker
            </h1>
            <ActiveTradesPage />
          </div>
        );
      case 'history':
        return (
          <div className="space-y-4">
            <h1 className="text-xl font-bold tracking-tight text-white font-mono">
              Closed Trade History & Multi-Level Audit Drilldown
            </h1>
            <TradeHistoryPage />
          </div>
        );
      case 'signals':
        return (
          <div className="space-y-4">
            <h1 className="text-xl font-bold tracking-tight text-white font-mono">
              Telegram Signal Feed & 1-Click Execution Wizard
            </h1>
            <SignalsFeedPage />
          </div>
        );
      case 'watchlist':
        return (
          <div className="space-y-4">
            <h1 className="text-xl font-bold tracking-tight text-white font-mono">
              Watchlist Whitelist Pairs & Binance Instrument Sync
            </h1>
            <WatchlistPage />
          </div>
        );
      case 'strategies':
        return (
          <div className="space-y-4">
            <h1 className="text-xl font-bold tracking-tight text-white font-mono">
              Strategy Configuration & Signal Providers Management
            </h1>
            <StrategiesPage />
          </div>
        );
      case 'simulator':
        return (
          <div className="space-y-4">
            <h1 className="text-xl font-bold tracking-tight text-white font-mono">
              Risk Simulator Sandbox & Dynamic Position Sizing
            </h1>
            <RiskSimulatorPage />
          </div>
        );
      case 'operations':
        return (
          <div className="space-y-4">
            <h1 className="text-xl font-bold tracking-tight text-white font-mono">
              Bot Operations Control Panel & Credential Vault
            </h1>
            <BotOperationsPage />
          </div>
        );
      case 'logs':
        return (
          <div className="space-y-4">
            <h1 className="text-xl font-bold tracking-tight text-white font-mono">
              System Audit Logs Terminal & CSV Performance Reports
            </h1>
            <LogsAndReportsPage />
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <AuthGuard>
      <TooltipProvider>
        <AppLayout currentRoute={currentRoute} onRouteChange={setCurrentRoute}>
          {renderCurrentView()}
        </AppLayout>
      </TooltipProvider>
    </AuthGuard>
  );
}
