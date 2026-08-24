import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ActiveTradesTable } from '@/features/trades/components/ActiveTradesTable';
import { ActiveTradeDTO } from '@/types/trades';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock auth store for RoleGuard
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (
    selector?: (state: { user: { role: string } | null }) => unknown
  ) => {
    const state = { user: { role: 'ADMIN' } };
    return typeof selector === 'function' ? selector(state) : state;
  },
}));

const mockTrades: ActiveTradeDTO[] = [
  {
    trade_id: 101,
    symbol: 'BTCUSDT',
    side: 'BUY',
    status: 'OPEN',
    entry_price: 50000.0,
    current_price: 50600.0,
    sl_price: 49000.0,
    position_size: 0.02,
    remaining_qty: 0.02,
    unrealized_pnl: 12.0,
    unrealized_pnl_percent: 1.2,
    leverage: 20,
    margin_mode: 'ISOLATED',
    tp_levels: [
      { level: 1, price: 51000.0, is_hit: true },
      { level: 2, price: 52000.0, is_hit: false },
      { level: 3, price: 53000.0, is_hit: false },
    ],
    opened_at: '2026-08-24T13:00:00Z',
  },
  {
    trade_id: 102,
    symbol: 'ETHUSDT',
    side: 'SELL',
    status: 'OPEN',
    entry_price: 3100.0,
    current_price: 3150.0,
    sl_price: 3200.0,
    position_size: 0.5,
    remaining_qty: 0.5,
    unrealized_pnl: -25.0,
    unrealized_pnl_percent: -1.61,
    leverage: 15,
    margin_mode: 'ISOLATED',
    tp_levels: [
      { level: 1, price: 3000.0, is_hit: false },
      { level: 2, price: 2900.0, is_hit: false },
      { level: 3, price: 2800.0, is_hit: false },
    ],
    opened_at: '2026-08-24T13:30:00Z',
  },
];

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('ActiveTradesTable Component', () => {
  it('renders active positions with symbols, sides, prices, and PnL', () => {
    renderWithQuery(<ActiveTradesTable trades={mockTrades} />);

    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument();
    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('SELL')).toBeInTheDocument();
    expect(screen.getByText('$50,000.00')).toBeInTheDocument();
    expect(screen.getByText('$50,600.00')).toBeInTheDocument();
    expect(screen.getByText('+$12.00')).toBeInTheDocument();
    expect(screen.getByText('-$25.00')).toBeInTheDocument();
  });

  it('displays BEP badge when TP1 is hit', () => {
    renderWithQuery(<ActiveTradesTable trades={mockTrades} />);

    // Trade 101 has TP1 hit = true, should render BEP badge
    expect(screen.getByText('BEP')).toBeInTheDocument();
  });

  it('filters active trades table by search query', async () => {
    renderWithQuery(<ActiveTradesTable trades={mockTrades} />);

    const searchInput = screen.getByPlaceholderText('Filter symbol/side...');
    await userEvent.type(searchInput, 'ETH');

    expect(screen.queryByText('BTCUSDT')).not.toBeInTheDocument();
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument();
  });

  it('renders EmptyPositionsState when trade list is empty', () => {
    renderWithQuery(<ActiveTradesTable trades={[]} />);

    expect(screen.getByText('No Active Positions')).toBeInTheDocument();
    expect(
      screen.getByText(/trading engine is standing by/i)
    ).toBeInTheDocument();
  });
});
