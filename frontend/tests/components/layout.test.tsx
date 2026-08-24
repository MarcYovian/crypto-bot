import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Navbar } from '@/components/layout/Navbar';
import { Sidebar } from '@/components/layout/Sidebar';
import { AppLayout } from '@/components/layout/AppLayout';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock auth store
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    user: { username: 'admin', role: 'ADMIN' },
    logout: vi.fn(),
  }),
}));

// Mock WebSocket store
vi.mock('@/stores/wsStore', () => ({
  useWebSocketStore: () => ({
    status: 'CONNECTED',
    latencyMs: 15,
  }),
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('Master Layout Shell Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Navbar with logo, live WS status, and user role badge', () => {
    renderWithQuery(<Navbar />);

    expect(screen.getByText(/SMC/i)).toBeInTheDocument();
    expect(screen.getByText('ENGINE RUNNING')).toBeInTheDocument();
    expect(screen.getByText('LIVE')).toBeInTheDocument();
    expect(screen.getByText('ADMIN')).toBeInTheDocument();
    expect(screen.getByText('admin')).toBeInTheDocument();
  });

  it('renders Sidebar with all 9 navigation items', () => {
    const handleRouteChange = vi.fn();

    renderWithQuery(
      <Sidebar currentRoute="overview" onRouteChange={handleRouteChange} />
    );

    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Active Trades')).toBeInTheDocument();
    expect(screen.getByText('Trade History')).toBeInTheDocument();
    expect(screen.getByText('Signal Feed')).toBeInTheDocument();
    expect(screen.getByText('Watchlist')).toBeInTheDocument();
    expect(screen.getByText('Strategies')).toBeInTheDocument();
    expect(screen.getByText('Risk Simulator')).toBeInTheDocument();
    expect(screen.getByText('Bot Operations')).toBeInTheDocument();
    expect(screen.getByText('Logs & Reports')).toBeInTheDocument();
  });

  it('triggers onRouteChange when a sidebar link is clicked', async () => {
    const handleRouteChange = vi.fn();

    renderWithQuery(
      <Sidebar currentRoute="overview" onRouteChange={handleRouteChange} />
    );

    const signalsLink = screen.getByRole('button', { name: /signal feed/i });
    await userEvent.click(signalsLink);

    expect(handleRouteChange).toHaveBeenCalledWith('signals');
  });

  it('toggles collapse state on collapse button click', async () => {
    renderWithQuery(
      <Sidebar currentRoute="overview" onRouteChange={vi.fn()} />
    );

    const collapseBtn = screen.getByRole('button', { name: /collapse rail/i });
    expect(screen.getByText('Collapse Rail')).toBeInTheDocument();

    await userEvent.click(collapseBtn);
    expect(screen.queryByText('Collapse Rail')).not.toBeInTheDocument();
  });

  it('renders AppLayout shell with children content', () => {
    renderWithQuery(
      <AppLayout currentRoute="overview" onRouteChange={vi.fn()}>
        <div data-testid="dashboard-content">Dashboard View Body</div>
      </AppLayout>
    );

    expect(screen.getByTestId('dashboard-content')).toBeInTheDocument();
    expect(screen.getByText('Dashboard View Body')).toBeInTheDocument();
  });
});
