import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ManualCloseModal } from '@/features/trades/components/ManualCloseModal';
import { ActiveTradeDTO } from '@/types/trades';
import * as tradesApi from '@/api/endpoints/trades';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockTrade: ActiveTradeDTO = {
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
  tp_levels: [],
  opened_at: '2026-08-24T13:00:00Z',
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

describe('ManualCloseModal Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders position snapshot and warning details', () => {
    renderWithQuery(
      <ManualCloseModal trade={mockTrade} isOpen={true} onClose={vi.fn()} />
    );

    expect(screen.getByText('Manual Market Close Position')).toBeInTheDocument();
    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('ID: #101')).toBeInTheDocument();
    expect(screen.getByText('0.02')).toBeInTheDocument();
    expect(screen.getByText('Confirm Market Close')).toBeInTheDocument();
  });

  it('submits closeTradeApi on confirmation click', async () => {
    const handleClose = vi.fn();
    const closeSpy = vi
      .spyOn(tradesApi, 'closeTradeApi')
      .mockResolvedValueOnce({
        success: true,
        message: 'Trade closed successfully.',
      });

    renderWithQuery(
      <ManualCloseModal trade={mockTrade} isOpen={true} onClose={handleClose} />
    );

    const confirmBtn = screen.getByRole('button', {
      name: /confirm market close/i,
    });
    await userEvent.click(confirmBtn);

    await waitFor(() => {
      expect(closeSpy).toHaveBeenCalledWith(101, 'UI_MANUAL_CLOSE');
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it('displays error message when API fails', async () => {
    vi.spyOn(tradesApi, 'closeTradeApi').mockRejectedValueOnce(
      new Error('Trade is not in a closeable status')
    );

    renderWithQuery(
      <ManualCloseModal trade={mockTrade} isOpen={true} onClose={vi.fn()} />
    );

    const confirmBtn = screen.getByRole('button', {
      name: /confirm market close/i,
    });
    await userEvent.click(confirmBtn);

    await waitFor(() => {
      expect(
        screen.getByText('Trade is not in a closeable status')
      ).toBeInTheDocument();
    });
  });
});
