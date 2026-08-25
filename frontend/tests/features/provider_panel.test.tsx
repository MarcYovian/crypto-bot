import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SignalProvidersPanel } from '@/features/strategies/components/SignalProvidersPanel';
import { SignalProviderDTO, ProviderPerformanceDTO } from '@/types/providers';
import * as providersApi from '@/api/endpoints/providers';
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

const mockProviders: SignalProviderDTO[] = [
  {
    id: 1,
    name: 'Crypto VIP Alpha',
    channel_id: '-100123456789',
    is_active: true,
    confidence_weight: 1.2,
  },
  {
    id: 2,
    name: 'SMC Inner Circle',
    channel_id: '-100987654321',
    is_active: false,
    confidence_weight: 0.9,
  },
];

const mockAnalytics: ProviderPerformanceDTO = {
  provider_id: 1,
  provider_name: 'Crypto VIP Alpha',
  total_signals: 50,
  executed_trades: 45,
  win_rate: 75.0,
  total_net_pnl_usdt: 450.25,
};

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

describe('SignalProvidersPanel Component', () => {
  beforeEach(() => {
    (global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
    vi.clearAllMocks();
  });

  it('renders provider cards with names, channel IDs, and weights', async () => {
    vi.spyOn(providersApi, 'getProvidersApi').mockResolvedValueOnce(
      mockProviders
    );

    renderWithQuery(<SignalProvidersPanel />);

    await waitFor(() => {
      expect(screen.getByText('Crypto VIP Alpha')).toBeInTheDocument();
      expect(screen.getByText('SMC Inner Circle')).toBeInTheDocument();
      expect(screen.getByText('-100123456789')).toBeInTheDocument();
      expect(screen.getByText('1.20x')).toBeInTheDocument();
      expect(screen.getByText('ACTIVE')).toBeInTheDocument();
      expect(screen.getByText('INACTIVE')).toBeInTheDocument();
    });
  });

  it('opens AddProviderModal and creates a new channel', async () => {
    vi.spyOn(providersApi, 'getProvidersApi').mockResolvedValue(mockProviders);
    const createSpy = vi
      .spyOn(providersApi, 'createProviderApi')
      .mockResolvedValueOnce({
        id: 3,
        name: 'New Trend Channel',
        channel_id: '-1001122334455',
        is_active: true,
        confidence_weight: 1.0,
      });

    renderWithQuery(<SignalProvidersPanel />);

    await waitFor(() => {
      expect(screen.getByText('Crypto VIP Alpha')).toBeInTheDocument();
    });

    const addBtn = screen.getByRole('button', { name: /add channel/i });
    await userEvent.click(addBtn);

    expect(
      screen.getByText('Add Telegram Signal Channel')
    ).toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText(/e.g. SMC Alpha/i);
    const channelInput = screen.getByPlaceholderText(/e.g. -1001987654321/i);

    await userEvent.type(nameInput, 'New Trend Channel');
    await userEvent.type(channelInput, '-1001122334455');

    const submitBtn = screen.getByRole('button', {
      name: /register provider/i,
    });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith({
        name: 'New Trend Channel',
        channel_id: '-1001122334455',
        confidence_weight: 1,
      });
    });
  });

  it('opens ProviderAnalyticsModal and displays telemetry', async () => {
    vi.spyOn(providersApi, 'getProvidersApi').mockResolvedValue(mockProviders);
    const analyticsSpy = vi
      .spyOn(providersApi, 'getProviderAnalyticsApi')
      .mockResolvedValueOnce(mockAnalytics);

    renderWithQuery(<SignalProvidersPanel />);

    await waitFor(() => {
      expect(screen.getByText('Crypto VIP Alpha')).toBeInTheDocument();
    });

    const viewAnalyticsBtns = screen.getAllByRole('button', {
      name: /view analytics & win rate/i,
    });
    await userEvent.click(viewAnalyticsBtns[0]);

    await waitFor(() => {
      expect(analyticsSpy).toHaveBeenCalledWith(1);
      expect(
        screen.getByText('Crypto VIP Alpha Performance')
      ).toBeInTheDocument();
      expect(screen.getByText('50')).toBeInTheDocument(); // total signals
      expect(screen.getByText('45')).toBeInTheDocument(); // executed orders
      expect(screen.getAllByText('75.0%').length).toBeGreaterThanOrEqual(1); // win rate
      expect(screen.getByText('$450.25')).toBeInTheDocument(); // realized net pnl
    });
  });
});
