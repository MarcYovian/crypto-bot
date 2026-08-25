import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CredentialVaultCard } from '@/features/bot-settings/components/CredentialVaultCard';
import { BotSettingsForm } from '@/features/bot-settings/components/BotSettingsForm';
import { BotSettingsDTO, CredentialSaveResponseDTO } from '@/types/bot';
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

const mockSettings: BotSettingsDTO = {
  default_leverage: 20,
  confidence_threshold: 0.7,
  risk_percent_per_trade: 2.0,
  max_daily_loss_percent: 6.0,
  max_open_trades: 3,
  is_paused: false,
};

const mockCredentialResponse: CredentialSaveResponseDTO = {
  success: true,
  account_id: 1,
  credential_id: 1,
  wallet_balance_usdt: 10450.5,
  environment: 'TESTNET',
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

describe('CredentialVaultCard Component', () => {
  beforeEach(() => {
    (global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
    vi.clearAllMocks();
  });

  it('toggles password masking for API key and Secret key', async () => {
    renderWithQuery(<CredentialVaultCard />);

    const apiKeyInput = screen.getByPlaceholderText(/enter binance api key/i);
    const secretKeyInput = screen.getByPlaceholderText(/enter binance secret key/i);

    expect(apiKeyInput).toHaveAttribute('type', 'password');
    expect(secretKeyInput).toHaveAttribute('type', 'password');

    const showApiBtn = screen.getByRole('button', { name: /show api key/i });
    await userEvent.click(showApiBtn);
    expect(apiKeyInput).toHaveAttribute('type', 'text');

    const showSecretBtn = screen.getByRole('button', { name: /show secret key/i });
    await userEvent.click(showSecretBtn);
    expect(secretKeyInput).toHaveAttribute('type', 'text');
  });

  it('submits credentials for handshake test and renders verified balance on success', async () => {
    const saveSpy = vi
      .spyOn(botApi, 'saveCredentialsApi')
      .mockResolvedValueOnce(mockCredentialResponse);

    renderWithQuery(<CredentialVaultCard />);

    const apiKeyInput = screen.getByPlaceholderText(/enter binance api key/i);
    const secretKeyInput = screen.getByPlaceholderText(/enter binance secret key/i);

    await userEvent.type(apiKeyInput, 'testApiKeyLongEnough12345');
    await userEvent.type(secretKeyInput, 'testSecretKeyLongEnough67890');

    const submitBtn = screen.getByRole('button', {
      name: /test handshake & save credentials/i,
    });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith({
        api_key: 'testApiKeyLongEnough12345',
        secret_key: 'testSecretKeyLongEnough67890',
        environment: 'TESTNET',
      });
      expect(
        screen.getByText('Handshake Successful & Keys Saved')
      ).toBeInTheDocument();
      expect(screen.getByText('$10,450.50')).toBeInTheDocument();
    });
  });
});

describe('BotSettingsForm Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial settings and updates configuration on submit', async () => {
    vi.spyOn(botApi, 'getSettingsApi').mockResolvedValue(mockSettings);
    const updateSpy = vi
      .spyOn(botApi, 'updateSettingsApi')
      .mockResolvedValueOnce({
        ...mockSettings,
        default_leverage: 50,
      });

    renderWithQuery(<BotSettingsForm />);

    await waitFor(() => {
      expect(
        screen.getByText('Dynamic Bot Configuration & Risk Profile')
      ).toBeInTheDocument();
      expect(screen.getByText('20x')).toBeInTheDocument();
      expect(screen.getByText('2.0% of Equity')).toBeInTheDocument();
    });

    const submitBtn = screen.getByRole('button', { name: /save bot settings/i });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          default_leverage: 20,
          confidence_threshold: 0.7,
          risk_percent_per_trade: 2.0,
          max_daily_loss_percent: 6.0,
          max_open_trades: 3,
        })
      );
    });
  });
});
