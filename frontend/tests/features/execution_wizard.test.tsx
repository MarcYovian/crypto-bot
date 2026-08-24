import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SignalExecutionWizardModal } from '@/features/signals/components/SignalExecutionWizardModal';
import { SignalItemDTO } from '@/types/signals';
import * as signalsApi from '@/api/endpoints/signals';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockBuySignal: SignalItemDTO = {
  id: 1,
  trace_id: 'sig-001',
  raw_text: 'BUY BTCUSDT Entry: 50000 SL: 49000 TP: 51000/52000',
  symbol: 'BTCUSDT',
  side: 'BUY',
  entry_price: 50000.0,
  sl_price: 49000.0,
  tp_targets: [51000.0, 52000.0, 53000.0],
  confidence_score: 0.95,
  status: 'PENDING',
  created_at: '2026-08-24T14:00:00Z',
};

const mockSellSignal: SignalItemDTO = {
  id: 2,
  trace_id: 'sig-002',
  raw_text: 'SELL ETHUSDT Entry: 3100 SL: 3200 TP: 3000',
  symbol: 'ETHUSDT',
  side: 'SELL',
  entry_price: 3100.0,
  sl_price: 3200.0,
  tp_targets: [3000.0, 2900.0, 2800.0],
  confidence_score: 0.9,
  status: 'PENDING',
  created_at: '2026-08-24T14:10:00Z',
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

class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

describe('SignalExecutionWizardModal Component', () => {
  beforeEach(() => {
    (global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
    vi.clearAllMocks();
  });

  it('pre-fills signal parameters and verifies safe risk badge', () => {
    renderWithQuery(
      <SignalExecutionWizardModal
        signal={mockBuySignal}
        isOpen={true}
        onClose={vi.fn()}
        accountBalance={10000.0}
      />
    );

    expect(screen.getByDisplayValue('50000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('49000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('51000')).toBeInTheDocument();
    expect(screen.getByText(/SAFE/i)).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', {
      name: /confirm & execute order/i,
    });
    expect(submitBtn).toBeEnabled();
  });

  it('disables execute button when price geometry is violated on BUY (SL >= Entry)', async () => {
    renderWithQuery(
      <SignalExecutionWizardModal
        signal={mockBuySignal}
        isOpen={true}
        onClose={vi.fn()}
        accountBalance={10000.0}
      />
    );

    const slInput = screen.getByDisplayValue('49000');
    await userEvent.clear(slInput);
    await userEvent.type(slInput, '51000'); // SL above Entry on BUY

    expect(
      screen.getByText(/Stop Loss must be strictly below Entry price/i)
    ).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', {
      name: /confirm & execute order/i,
    });
    expect(submitBtn).toBeDisabled();
  });

  it('disables execute button when price geometry is violated on SELL (SL <= Entry)', async () => {
    renderWithQuery(
      <SignalExecutionWizardModal
        signal={mockSellSignal}
        isOpen={true}
        onClose={vi.fn()}
        accountBalance={10000.0}
      />
    );

    const slInput = screen.getByDisplayValue('3200');
    await userEvent.clear(slInput);
    await userEvent.type(slInput, '3000'); // SL below Entry on SELL

    expect(
      screen.getByText(/Stop Loss must be strictly above Entry price/i)
    ).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', {
      name: /confirm & execute order/i,
    });
    expect(submitBtn).toBeDisabled();
  });

  it('submits manual execution payload on confirmation click', async () => {
    const executeSpy = vi
      .spyOn(signalsApi, 'manualExecuteSignalApi')
      .mockResolvedValueOnce({
        is_success: true,
        trade_id: 99,
        symbol: 'BTCUSDT',
        side: 'BUY',
        position_size: 0.2,
        leverage: 20,
        entry_order_id: 'ord-123',
        sl_order_id: 'ord-124',
        tp_order_ids: ['ord-125', 'ord-126', 'ord-127'],
        message: 'Order placed',
      });

    renderWithQuery(
      <SignalExecutionWizardModal
        signal={mockBuySignal}
        isOpen={true}
        onClose={vi.fn()}
        accountBalance={10000.0}
      />
    );

    const submitBtn = screen.getByRole('button', {
      name: /confirm & execute order/i,
    });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(executeSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: 'BTCUSDT',
          side: 'BUY',
          entry_price: 50000,
          sl_price: 49000,
          leverage: 20,
          auto_tp_sl: true,
        }),
        1
      );
    });
  });
});
