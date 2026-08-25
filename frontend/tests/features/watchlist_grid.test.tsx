import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WatchlistGrid } from '@/features/watchlist/components/WatchlistGrid';
import { WatchlistSearchFilter } from '@/features/watchlist/components/WatchlistSearchFilter';
import { WatchlistItemDTO } from '@/types/watchlist';
import * as watchlistApi from '@/api/endpoints/watchlist';
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

class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

const mockWatchlist: WatchlistItemDTO[] = [
  {
    id: 1,
    symbol: 'BTCUSDT',
    enabled: true,
    max_leverage: 125,
    tick_size: 0.1,
    min_qty: 0.001,
  },
  {
    id: 2,
    symbol: 'ETHUSDT',
    enabled: false,
    max_leverage: 100,
    tick_size: 0.01,
    min_qty: 0.01,
  },
  {
    id: 3,
    symbol: 'SOLUSDT',
    enabled: true,
    max_leverage: 50,
    tick_size: 0.01,
    min_qty: 0.1,
  },
];

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('WatchlistGrid Component', () => {
  beforeEach(() => {
    (global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
    vi.clearAllMocks();
  });

  it('renders watchlist items with symbols, leverage, and active status', () => {
    renderWithQuery(<WatchlistGrid items={mockWatchlist} />);

    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument();
    expect(screen.getByText('125x')).toBeInTheDocument();
    expect(screen.getByText('100x')).toBeInTheDocument();
    expect(screen.getAllByText('ENABLED').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('DISABLED')).toBeInTheDocument();
    expect(screen.getByText(/3 pairs total/i)).toBeInTheDocument();
  });

  it('triggers toggle mutation when switch is clicked', async () => {
    const toggleSpy = vi
      .spyOn(watchlistApi, 'toggleWatchlistApi')
      .mockResolvedValueOnce({
        id: 2,
        symbol: 'ETHUSDT',
        enabled: true,
        max_leverage: 100,
        tick_size: 0.01,
        min_qty: 0.01,
      });

    renderWithQuery(<WatchlistGrid items={mockWatchlist} />);

    const switches = screen.getAllByRole('switch');
    await userEvent.click(switches[1]); // Toggle ETHUSDT

    await waitFor(() => {
      expect(toggleSpy).toHaveBeenCalledWith('ETHUSDT', true);
    });
  });

  it('opens InstrumentBracketModal when Inspect Tiers button is clicked', async () => {
    renderWithQuery(<WatchlistGrid items={mockWatchlist} />);

    const inspectButtons = screen.getAllByRole('button', { name: /inspect tiers/i });
    await userEvent.click(inspectButtons[0]);

    expect(
      screen.getByText('BTCUSDT Specifications & Leverage Tiers')
    ).toBeInTheDocument();
    expect(screen.getByText('Base / Quote:')).toBeInTheDocument();
  });

  it('renders pagination and density selector properly', async () => {
    renderWithQuery(<WatchlistGrid items={mockWatchlist} />);

    expect(screen.getByText(/Showing page/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '10' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '20' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '50' })).toBeInTheDocument();

    const size20Btn = screen.getByRole('button', { name: '20' });
    await userEvent.click(size20Btn);

    expect(size20Btn).toHaveClass('bg-brand-500');
  });
});

describe('WatchlistSearchFilter Component', () => {
  it('triggers onSearchChange when typing in search input', async () => {
    const handleSearch = vi.fn();
    render(
      <WatchlistSearchFilter
        searchQuery=""
        onSearchChange={handleSearch}
        statusFilter="ALL"
        onStatusFilterChange={vi.fn()}
        enabledCount={2}
        totalCount={3}
      />
    );

    const searchInput = screen.getByPlaceholderText(/filter symbol/i);
    await userEvent.type(searchInput, 'BTC');

    expect(handleSearch).toHaveBeenCalled();
  });

  it('triggers onStatusFilterChange when filter pill is clicked', async () => {
    const handleStatus = vi.fn();
    render(
      <WatchlistSearchFilter
        searchQuery=""
        onSearchChange={vi.fn()}
        statusFilter="ALL"
        onStatusFilterChange={handleStatus}
        enabledCount={2}
        totalCount={3}
      />
    );

    const enabledBtn = screen.getByRole('button', { name: 'ENABLED' });
    await userEvent.click(enabledBtn);

    expect(handleStatus).toHaveBeenCalledWith('ENABLED');
  });
});
