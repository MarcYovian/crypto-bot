import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrategyConfigPanel } from '@/features/strategies/components/StrategyConfigPanel';
import { StrategyDTO } from '@/types/strategies';
import * as strategiesApi from '@/api/endpoints/strategies';
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

const mockStrategy: StrategyDTO = {
  id: 1,
  name: 'Standard 3-Stage TP Strategy',
  tp_allocations: [
    { tp_level: 1, percentage: 50.0 },
    { tp_level: 2, percentage: 30.0 },
    { tp_level: 3, percentage: 20.0 },
  ],
  bep_trigger_level: 1,
  trailing_trigger_level: 2,
  is_active: true,
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

describe('StrategyConfigPanel Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders strategy details, initial 50/30/20 allocations, and valid status badge', async () => {
    vi.spyOn(strategiesApi, 'getStrategiesApi').mockResolvedValue([
      mockStrategy,
    ]);

    renderWithQuery(<StrategyConfigPanel />);

    await waitFor(() => {
      expect(
        screen.getByText('Standard 3-Stage TP Strategy')
      ).toBeInTheDocument();
      expect(screen.getByText('50%')).toBeInTheDocument();
      expect(screen.getByText('30%')).toBeInTheDocument();
      expect(screen.getByText('20%')).toBeInTheDocument();
      expect(screen.getByText(/Total: 100.0% \(Valid\)/i)).toBeInTheDocument();
    });
  });

  it('triggers update mutation with new trigger levels on form submission', async () => {
    vi.spyOn(strategiesApi, 'getStrategiesApi').mockResolvedValue([
      mockStrategy,
    ]);
    const updateSpy = vi
      .spyOn(strategiesApi, 'updateStrategyApi')
      .mockResolvedValueOnce({
        ...mockStrategy,
        bep_trigger_level: 2,
      });

    renderWithQuery(<StrategyConfigPanel />);

    await waitFor(() => {
      expect(
        screen.getByText('Standard 3-Stage TP Strategy')
      ).toBeInTheDocument();
    });

    // Select BEP TP2 Milestone
    const tp2Btns = screen.getAllByRole('button', { name: /TP2 Milestone/i });
    await userEvent.click(tp2Btns[0]); // First is BEP

    const saveBtn = screen.getByRole('button', { name: /save strategy rules/i });
    expect(saveBtn).not.toBeDisabled();
    await userEvent.click(saveBtn);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(1, {
        tp1_percent: 50,
        tp2_percent: 30,
        tp3_percent: 20,
        bep_trigger_level: 2,
        trailing_trigger_level: 2,
      });
      expect(
        screen.getByText(/Strategy configuration successfully updated/i)
      ).toBeInTheDocument();
    });
  });
});
