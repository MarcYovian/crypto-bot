import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InstrumentSyncButton } from '@/features/watchlist/components/InstrumentSyncButton';
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

describe('InstrumentSyncButton Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('triggers exchange sync API and displays feedback message on success', async () => {
    const syncSpy = vi
      .spyOn(watchlistApi, 'syncInstrumentsApi')
      .mockResolvedValueOnce({
        synced_instruments: 35,
        synced_brackets: 140,
        timestamp: '2026-08-24T14:15:00Z',
      });

    renderWithQuery(<InstrumentSyncButton />);

    const syncBtn = screen.getByRole('button', { name: /sync from binance/i });
    await userEvent.click(syncBtn);

    await waitFor(() => {
      expect(syncSpy).toHaveBeenCalled();
      expect(
        screen.getByText(
          /Successfully synced 35 instruments and 140 leverage brackets from Binance/i
        )
      ).toBeInTheDocument();
    });
  });

  it('handles sync error and displays alert message', async () => {
    vi.spyOn(watchlistApi, 'syncInstrumentsApi').mockRejectedValueOnce(
      new Error('Binance rate limit exceeded')
    );

    renderWithQuery(<InstrumentSyncButton />);

    const syncBtn = screen.getByRole('button', { name: /sync from binance/i });
    await userEvent.click(syncBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Binance rate limit exceeded/i)
      ).toBeInTheDocument();
    });
  });
});
