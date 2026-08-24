import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TradeDetailModal } from '@/features/trades/components/TradeDetailModal';
import { TradeDetailDTO } from '@/types/trades';
import * as tradesApi from '@/api/endpoints/trades';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockDetail: TradeDetailDTO = {
  trade_id: 101,
  symbol: 'BTCUSDT',
  side: 'BUY',
  status: 'CLOSED',
  entry_price: 50000.0,
  sl_price: 49000.0,
  position_size: 0.02,
  leverage: 20,
  risk_details: {
    risk_amount_usdt: 20.0,
    stop_distance: 1000.0,
    required_margin: 50.0,
  },
  orders: [
    {
      id: 1,
      exchange_order_id: 'binance-101',
      purpose: 'ENTRY',
      order_type: 'LIMIT',
      side: 'BUY',
      price: 50000.0,
      qty: 0.02,
      status: 'FILLED',
    },
    {
      id: 2,
      exchange_order_id: 'binance-102',
      purpose: 'TP1',
      order_type: 'LIMIT',
      side: 'SELL',
      price: 51000.0,
      qty: 0.01,
      status: 'FILLED',
    },
  ],
  executions: [
    {
      price: 50000.0,
      qty: 0.02,
      commission: 0.4,
      realized_pnl: 0.0,
      executed_at: '2026-08-20T10:00:00Z',
    },
    {
      price: 51000.0,
      qty: 0.01,
      commission: 0.2,
      realized_pnl: 10.0,
      executed_at: '2026-08-20T12:00:00Z',
    },
  ],
  events: [
    {
      event_type: 'POSITION_OPENED',
      payload: '{}',
      created_at: '2026-08-20T10:00:00Z',
    },
    {
      event_type: 'TP1_HIT',
      payload: '{}',
      created_at: '2026-08-20T12:00:00Z',
    },
  ],
  summary: {
    gross_pnl: 20.0,
    net_pnl: 19.4,
    commission: 0.6,
    roi: 38.8,
    result: 'WIN',
  },
};

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('TradeDetailModal Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches and renders trade details across the 5 tabs', async () => {
    vi.spyOn(tradesApi, 'getTradeDetailApi').mockResolvedValueOnce(mockDetail);

    renderWithQuery(
      <TradeDetailModal tradeId={101} isOpen={true} onClose={vi.fn()} />
    );

    // 1. Overview Tab (Default)
    await waitFor(() => {
      expect(
        screen.getByText('Trade Deep Drilldown #101')
      ).toBeInTheDocument();
      expect(screen.getByText('$50,000.00')).toBeInTheDocument();
    });

    // 2. Switch to Risk Tab
    const riskTab = screen.getByRole('tab', { name: /2\. Risk/i });
    await userEvent.click(riskTab);

    expect(screen.getByText('Max Risk Budget')).toBeInTheDocument();
    expect(screen.getByText('$20.00')).toBeInTheDocument();
    expect(screen.getByText('$1,000.00')).toBeInTheDocument();

    // 3. Switch to Orders Tab
    const ordersTab = screen.getByRole('tab', { name: /3\. Orders/i });
    await userEvent.click(ordersTab);

    expect(screen.getByText('#binance-101')).toBeInTheDocument();
    expect(screen.getByText('TP1')).toBeInTheDocument();

    // 4. Switch to Executions Tab
    const fillsTab = screen.getByRole('tab', { name: /4\. Fills/i });
    await userEvent.click(fillsTab);

    expect(screen.getByText('Executed Qty')).toBeInTheDocument();
    expect(screen.getByText('0.02')).toBeInTheDocument();

    // 5. Switch to Financials Tab
    const finTab = screen.getByRole('tab', { name: /5\. Financials/i });
    await userEvent.click(finTab);

    expect(screen.getByText('+$19.40')).toBeInTheDocument();
    expect(screen.getByText('0.97R')).toBeInTheDocument(); // 19.4 / 20 = 0.97R
  });

  it('handles cancelled trade with no executions safely', async () => {
    const cancelledDetail: TradeDetailDTO = {
      ...mockDetail,
      status: 'CANCELLED',
      executions: [],
      summary: null,
    };

    vi.spyOn(tradesApi, 'getTradeDetailApi').mockResolvedValueOnce(
      cancelledDetail
    );

    renderWithQuery(
      <TradeDetailModal tradeId={101} isOpen={true} onClose={vi.fn()} />
    );

    await waitFor(() => {
      expect(screen.getByText('CANCELLED')).toBeInTheDocument();
    });

    // Switch to Financials Tab
    const finTab = screen.getByRole('tab', { name: /5\. Financials/i });
    await userEvent.click(finTab);

    expect(
      screen.getByText(/CANCELLED - NO FINANCIAL SUMMARY/i)
    ).toBeInTheDocument();
  });
});
