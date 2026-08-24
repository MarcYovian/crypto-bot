import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SignalFeedList } from '@/features/signals/components/SignalFeedList';
import { PaginatedSignalListDTO } from '@/types/signals';
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

const mockSignals: PaginatedSignalListDTO = {
  total: 2,
  page: 1,
  page_size: 20,
  items: [
    {
      id: 1,
      trace_id: 'sig-btc-001',
      raw_text: 'BUY BTCUSDT Entry: 50000 SL: 49000 TP: 51000/52000',
      symbol: 'BTCUSDT',
      side: 'BUY',
      entry_price: 50000.0,
      sl_price: 49000.0,
      tp_targets: [51000.0, 52000.0],
      confidence_score: 0.95,
      status: 'PENDING',
      created_at: '2026-08-24T14:00:00Z',
    },
    {
      id: 2,
      trace_id: 'sig-eth-002',
      raw_text: 'SELL ETHUSDT Entry: 3100 SL: 3200 TP: 3000',
      symbol: 'ETHUSDT',
      side: 'SELL',
      entry_price: 3100.0,
      sl_price: 3200.0,
      tp_targets: [3000.0],
      confidence_score: 0.9,
      status: 'PROCESSED',
      created_at: '2026-08-24T13:30:00Z',
    },
  ],
};

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

describe('SignalFeedList Component', () => {
  beforeEach(() => {
    (global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
    vi.clearAllMocks();
  });

  it('renders signal cards with symbol, side, confidence score, and price targets', () => {
    renderWithQuery(
      <SignalFeedList
        data={mockSignals}
        filters={{ page: 1, page_size: 20 }}
        onFilterChange={vi.fn()}
      />
    );

    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument();
    expect(screen.getByText('95% AI')).toBeInTheDocument();
    expect(screen.getByText('90% AI')).toBeInTheDocument();
    expect(screen.getByText('$50,000.00')).toBeInTheDocument();
    expect(screen.getByText('$49,000.00')).toBeInTheDocument();
    expect(screen.getAllByText('PENDING').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('PROCESSED').length).toBeGreaterThanOrEqual(1);
  });

  it('triggers onFilterChange when a status filter pill is clicked', async () => {
    const handleFilterChange = vi.fn();

    renderWithQuery(
      <SignalFeedList
        data={mockSignals}
        filters={{ page: 1, page_size: 20 }}
        onFilterChange={handleFilterChange}
      />
    );

    const pendingBtn = screen.getByRole('button', { name: 'PENDING' });
    await userEvent.click(pendingBtn);

    expect(handleFilterChange).toHaveBeenCalledWith({
      status: 'PENDING',
      page: 1,
    });
  });

  it('filters signals by search query keyword', async () => {
    renderWithQuery(
      <SignalFeedList
        data={mockSignals}
        filters={{ page: 1, page_size: 20 }}
        onFilterChange={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText('Search symbol...');
    await userEvent.type(searchInput, 'ETH');

    expect(screen.queryByText('BTCUSDT')).not.toBeInTheDocument();
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument();
  });

  it('switches between Grid and Compact List view', async () => {
    renderWithQuery(
      <SignalFeedList
        data={mockSignals}
        filters={{ page: 1, page_size: 20 }}
        onFilterChange={vi.fn()}
      />
    );

    const listBtn = screen.getByTitle('Compact List View');
    await userEvent.click(listBtn);

    // In Compact List View, Execute button says 'Execute' instead of 'Execute Trade'
    expect(screen.getByRole('button', { name: /execute/i })).toBeInTheDocument();
  });

  it('opens 1-Click Execution Wizard modal when Execute Trade button is clicked', async () => {
    renderWithQuery(
      <SignalFeedList
        data={mockSignals}
        filters={{ page: 1, page_size: 20 }}
        onFilterChange={vi.fn()}
      />
    );

    const executeBtn = screen.getByRole('button', { name: /execute trade/i });
    await userEvent.click(executeBtn);

    expect(
      screen.getByText('1-Click Signal Execution Wizard')
    ).toBeInTheDocument();
    expect(screen.getByText('Confirm & Execute Order')).toBeInTheDocument();
  });
});
