import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BotStatusHero } from '@/features/bot-settings/components/BotStatusHero';
import { BotControlButtons } from '@/features/bot-settings/components/BotControlButtons';
import { BotStatusDTO } from '@/types/bot';
import * as botApi from '@/api/endpoints/bot';
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

const mockActiveStatus: BotStatusDTO = {
  is_running: true,
  is_paused: false,
  trading_status: 'ACTIVE',
  circuit_breaker_active: false,
  binance_ws_connected: true,
  telegram_polling_active: true,
  scheduler_jobs_count: 7,
  last_heartbeat: '2026-08-24T14:30:00Z',
};

const mockTrippedStatus: BotStatusDTO = {
  ...mockActiveStatus,
  is_paused: true,
  circuit_breaker_active: true,
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

describe('BotStatusHero Component', () => {
  beforeEach(() => {
    (global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
    vi.clearAllMocks();
  });

  it('renders active engine status and connected services', () => {
    renderWithQuery(<BotStatusHero status={mockActiveStatus} />);

    expect(screen.getByText(/ACTIVE \/ RUNNING/i)).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Polling Active')).toBeInTheDocument();
    expect(screen.getByText('7 Jobs Active')).toBeInTheDocument();
    expect(screen.getByText('Normal (Armed)')).toBeInTheDocument();
  });

  it('renders circuit breaker tripped critical banner when active', () => {
    renderWithQuery(<BotStatusHero status={mockTrippedStatus} />);

    expect(
      screen.getByText(/CIRCUIT BREAKER TRIPPED/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/DAILY LOSS LIMIT REACHED - TRADING HALTED/i)
    ).toBeInTheDocument();
  });
});

describe('BotControlButtons Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('triggers pauseBotApi when Pause Engine is clicked', async () => {
    const pauseSpy = vi.spyOn(botApi, 'pauseBotApi').mockResolvedValueOnce({
      success: true,
      message: 'Bot paused successfully.',
    });

    renderWithQuery(<BotControlButtons status={mockActiveStatus} />);

    const pauseBtn = screen.getByRole('button', { name: /pause engine/i });
    await userEvent.click(pauseBtn);

    await waitFor(() => {
      expect(pauseSpy).toHaveBeenCalled();
      expect(screen.getByText('Bot paused successfully.')).toBeInTheDocument();
    });
  });

  it('triggers resumeBotApi when Resume Engine is clicked on paused bot', async () => {
    const resumeSpy = vi.spyOn(botApi, 'resumeBotApi').mockResolvedValueOnce({
      success: true,
      message: 'Bot resumed successfully.',
    });

    renderWithQuery(<BotControlButtons status={{ ...mockActiveStatus, is_paused: true }} />);

    const resumeBtn = screen.getByRole('button', { name: /resume engine/i });
    await userEvent.click(resumeBtn);

    await waitFor(() => {
      expect(resumeSpy).toHaveBeenCalled();
      expect(screen.getByText('Bot resumed successfully.')).toBeInTheDocument();
    });
  });

  it('enforces 2-step verification for PANIC CLOSE ALL and renders execution recap', async () => {
    const panicSpy = vi.spyOn(botApi, 'panicCloseApi').mockResolvedValueOnce({
      success: true,
      closed_trades_count: 4,
      canceled_orders_count: 12,
      timestamp: '2026-08-24T14:35:00Z',
    });

    renderWithQuery(<BotControlButtons status={mockActiveStatus} />);

    // Step 1: Click PANIC CLOSE ALL to open modal
    const panicBtn = screen.getByRole('button', { name: /panic close all/i });
    await userEvent.click(panicBtn);

    expect(screen.getByText('EMERGENCY PANIC CLOSE ALL')).toBeInTheDocument();

    const executeBtn = screen.getByRole('button', { name: /execute panic close/i });
    expect(executeBtn).toBeDisabled();

    // Step 2: Check mandatory confirmation checkbox
    const checkbox = screen.getByRole('checkbox');
    await userEvent.click(checkbox);
    expect(executeBtn).not.toBeDisabled();

    // Submit execution
    await userEvent.click(executeBtn);

    await waitFor(() => {
      expect(panicSpy).toHaveBeenCalledWith(true);
      expect(screen.getByText('Emergency Panic Close Executed')).toBeInTheDocument();
      expect(screen.getByText('4')).toBeInTheDocument(); // closed positions
      expect(screen.getByText('12')).toBeInTheDocument(); // canceled orders
    });
  });
});
