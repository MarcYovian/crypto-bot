import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TradeHistoryTable } from '@/features/trades/components/TradeHistoryTable';
import { PaginatedTradeHistoryDTO } from '@/types/trades';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockData: PaginatedTradeHistoryDTO = {
  total: 45,
  page: 1,
  page_size: 20,
  items: [
    {
      id: 101,
      symbol: 'BTCUSDT',
      side: 'BUY',
      entry_price: 50000.0,
      exit_price: 52500.0,
      position_size: 0.02,
      net_pnl: 50.0,
      roi_percent: 5.0,
      result: 'WIN',
      close_reason: 'TP3_HIT',
      opened_at: '2026-08-20T10:00:00Z',
      closed_at: '2026-08-20T14:30:00Z',
    },
    {
      id: 102,
      symbol: 'ETHUSDT',
      side: 'SELL',
      entry_price: 3100.0,
      exit_price: 3160.0,
      position_size: 0.5,
      net_pnl: -30.0,
      roi_percent: -1.94,
      result: 'LOSS',
      close_reason: 'SL_HIT',
      opened_at: '2026-08-21T08:00:00Z',
      closed_at: '2026-08-21T09:15:00Z',
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

describe('TradeHistoryTable Component', () => {
  it('renders historical items with formatted numbers and outcome badges', () => {
    renderWithQuery(
      <TradeHistoryTable
        data={mockData}
        filters={{ page: 1, page_size: 20 }}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />
    );

    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument();
    expect(screen.getByText('WIN')).toBeInTheDocument();
    expect(screen.getByText('LOSS')).toBeInTheDocument();
    expect(screen.getByText('+$50.00')).toBeInTheDocument();
    expect(screen.getByText('-$30.00')).toBeInTheDocument();
    expect(screen.getByText('TP3_HIT')).toBeInTheDocument();
    expect(screen.getByText('SL_HIT')).toBeInTheDocument();
  });

  it('triggers onPageChange on pagination button click', async () => {
    const handlePageChange = vi.fn();

    renderWithQuery(
      <TradeHistoryTable
        data={mockData}
        filters={{ page: 1, page_size: 20 }}
        onPageChange={handlePageChange}
        onPageSizeChange={vi.fn()}
      />
    );

    const nextBtn = screen.getByRole('button', { name: /next/i });
    await userEvent.click(nextBtn);

    expect(handlePageChange).toHaveBeenCalledWith(2);
  });

  it('triggers onPageSizeChange on page size selection', async () => {
    const handlePageSize = vi.fn();

    renderWithQuery(
      <TradeHistoryTable
        data={mockData}
        filters={{ page: 1, page_size: 20 }}
        onPageChange={vi.fn()}
        onPageSizeChange={handlePageSize}
      />
    );

    const size50Btn = screen.getByRole('button', { name: '50' });
    await userEvent.click(size50Btn);

    expect(handlePageSize).toHaveBeenCalledWith(50);
  });
});
