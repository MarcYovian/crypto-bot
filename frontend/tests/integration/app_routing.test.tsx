import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '@/App';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as analyticsApi from '@/api/endpoints/analytics';
import * as tradesApi from '@/api/endpoints/trades';
import * as signalsApi from '@/api/endpoints/signals';
import * as watchlistApi from '@/api/endpoints/watchlist';
import * as strategiesApi from '@/api/endpoints/strategies';
import * as providersApi from '@/api/endpoints/providers';
import * as botApi from '@/api/endpoints/bot';
import * as logsApi from '@/api/endpoints/logs';

// Mock auth store
const mockAuthState = {
  user: { id: 1, username: 'admin', role: 'ADMIN' },
  accessToken: 'valid-jwt-token',
  isAuthenticated: true,
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  checkAuth: vi.fn(),
};

vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector?: (state: typeof mockAuthState) => unknown) => {
    return typeof selector === 'function' ? selector(mockAuthState) : mockAuthState;
  },
}));

// Mock WebSocket service and store
vi.mock('@/services/websocketService', () => ({
  wsService: {
    connect: vi.fn(),
    disconnect: vi.fn(),
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    on: vi.fn(() => vi.fn()),
  },
}));

vi.mock('@/stores/wsStore', () => {
  const state = {
    status: 'CONNECTED',
    latencyMs: 12,
    setStatus: vi.fn(),
    setLatency: vi.fn(),
    setLastPing: vi.fn(),
    incrementAttempts: vi.fn(),
    resetAttempts: vi.fn(),
  };
  const store = (selector?: (s: typeof state) => unknown) =>
    typeof selector === 'function' ? selector(state) : state;
  store.getState = () => state;
  return { useWebSocketStore: store };
});

class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
}

describe('Full Application Shell & End-to-End Navigation Integration', () => {
  beforeEach(() => {
    (global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
    Element.prototype.scrollIntoView = vi.fn();
    vi.clearAllMocks();

    // Setup global API mocks
    vi.spyOn(analyticsApi, 'getAnalyticsSummaryApi').mockResolvedValue({
      total_balance_usdt: 10450.5,
      free_margin_usdt: 500.0,
      daily_realized_pnl: 150.25,
      daily_pnl_percent: 1.45,
      daily_risk_budget: 100.0,
      remaining_risk_budget: 45.0,
      win_rate: 68.5,
      total_trades_count: 50,
      winning_trades_count: 34,
      losing_trades_count: 16,
      profit_factor: 2.1,
      active_trades_count: 2,
    });
    vi.spyOn(analyticsApi, 'getEquityCurveApi').mockResolvedValue([]);
    vi.spyOn(tradesApi, 'getActiveTradesApi').mockResolvedValue([]);
    vi.spyOn(tradesApi, 'getTradeHistoryApi').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    vi.spyOn(signalsApi, 'getSignalsFeedApi').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    vi.spyOn(watchlistApi, 'getWatchlistApi').mockResolvedValue([]);
    vi.spyOn(strategiesApi, 'getStrategiesApi').mockResolvedValue([]);
    vi.spyOn(providersApi, 'getProvidersApi').mockResolvedValue([]);
    vi.spyOn(botApi, 'getBotStatusApi').mockResolvedValue({
      is_running: true,
      is_paused: false,
      trading_status: 'ACTIVE',
      circuit_breaker_active: false,
      binance_ws_connected: true,
      telegram_polling_active: true,
      scheduler_jobs_count: 7,
      last_heartbeat: '2026-08-24T14:30:00Z',
    });
    vi.spyOn(botApi, 'getSettingsApi').mockResolvedValue({
      default_leverage: 20,
      confidence_threshold: 0.7,
      risk_percent_per_trade: 2.0,
      max_daily_loss_percent: 6.0,
      max_open_trades: 3,
      is_paused: false,
    });
    vi.spyOn(logsApi, 'getAuditLogsApi').mockResolvedValue([]);
  });

  it('renders executive dashboard by default with top navbar and sidebar', async () => {
    renderApp();

    await waitFor(() => {
      expect(screen.getByText('ENGINE RUNNING')).toBeInTheDocument();
      expect(screen.getByText('ADMIN')).toBeInTheDocument();
      expect(screen.getByText('Portfolio Health & Risk Matrix')).toBeInTheDocument();
    });
  });

  it('navigates across all 8 modules seamlessly via sidebar menu items', async () => {
    renderApp();

    // 1. Navigate to Active Trades
    const tradesBtn = screen.getByRole('button', { name: 'Active Trades' });
    await userEvent.click(tradesBtn);
    expect(
      screen.getByText(/Live Active Positions & Take Profit Milestone Tracker/i)
    ).toBeInTheDocument();

    // 2. Navigate to Trade History
    const historyBtn = screen.getByRole('button', { name: 'Trade History' });
    await userEvent.click(historyBtn);
    expect(
      screen.getByText(/Closed Trade History & Multi-Level Audit Drilldown/i)
    ).toBeInTheDocument();

    // 3. Navigate to Signal Feed
    const signalsBtn = screen.getByRole('button', { name: 'Signal Feed' });
    await userEvent.click(signalsBtn);
    expect(
      screen.getByText(/Telegram Signal Feed & 1-Click Execution Wizard/i)
    ).toBeInTheDocument();

    // 4. Navigate to Watchlist
    const watchlistBtn = screen.getByRole('button', { name: 'Watchlist' });
    await userEvent.click(watchlistBtn);
    expect(
      screen.getByText(/Watchlist Whitelist Pairs & Binance Instrument Sync/i)
    ).toBeInTheDocument();

    // 5. Navigate to Strategies
    const strategiesBtn = screen.getByRole('button', { name: 'Strategies' });
    await userEvent.click(strategiesBtn);
    expect(
      screen.getByText(/Strategy Configuration & Signal Providers Management/i)
    ).toBeInTheDocument();

    // 6. Navigate to Risk Simulator
    const simulatorBtn = screen.getByRole('button', { name: 'Risk Simulator' });
    await userEvent.click(simulatorBtn);
    expect(
      screen.getByText(/Risk Simulator Sandbox & Dynamic Position Sizing/i)
    ).toBeInTheDocument();

    // 7. Navigate to Bot Operations
    const opsBtn = screen.getByRole('button', { name: 'Bot Operations' });
    await userEvent.click(opsBtn);
    expect(
      screen.getByText(/Bot Operations Control Panel & Credential Vault/i)
    ).toBeInTheDocument();

    // 8. Navigate to Logs & Reports
    const logsBtn = screen.getByRole('button', { name: 'Logs & Reports' });
    await userEvent.click(logsBtn);
    expect(
      screen.getByText(/System Audit Logs Terminal & CSV Performance Reports/i)
    ).toBeInTheDocument();
  });
});
