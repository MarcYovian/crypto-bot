import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RiskSimulatorForm } from '@/features/calculator/components/RiskSimulatorForm';
import { SimulationResultCard } from '@/features/calculator/components/SimulationResultCard';
import { LiquidationVisualizer } from '@/features/calculator/components/LiquidationVisualizer';
import { validatePriceGeometry } from '@/hooks/useRiskSimulation';
import {
  RiskSimulationRequestDTO,
  RiskSimulationResponseDTO,
} from '@/types/calculator';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockSimulationResult: RiskSimulationResponseDTO = {
  symbol: 'BTCUSDT',
  side: 'BUY',
  max_allowed_loss_usdt: 20.0,
  calculated_position_size: 0.02,
  required_margin_usdt: 50.0,
  effective_leverage: 20,
  is_leverage_downscaled: false,
  estimated_liquidation_price: 47500.0,
  stop_distance_usdt: 1000.0,
  projected_loss_at_sl_usdt: 20.0,
  is_safe: true,
};

const mockDownscaledResult: RiskSimulationResponseDTO = {
  ...mockSimulationResult,
  requested_leverage: 50,
  effective_leverage: 20,
  is_leverage_downscaled: true,
} as unknown as RiskSimulationResponseDTO;

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

describe('validatePriceGeometry logic', () => {
  it('rejects BUY positions when SL >= Entry', () => {
    const res1 = validatePriceGeometry('BUY', 50000, 50000);
    expect(res1.isValid).toBe(false);
    expect(res1.error).toContain('Stop Loss distance cannot be zero');

    const res2 = validatePriceGeometry('BUY', 50000, 51000);
    expect(res2.isValid).toBe(false);
    expect(res2.error).toContain('Stop Loss must be BELOW Entry');
  });

  it('rejects SELL positions when SL <= Entry', () => {
    const res = validatePriceGeometry('SELL', 50000, 49000);
    expect(res.isValid).toBe(false);
    expect(res.error).toContain('Stop Loss must be ABOVE Entry');
  });

  it('accepts valid price geometry for both BUY and SELL', () => {
    const buyRes = validatePriceGeometry('BUY', 50000, 49000);
    expect(buyRes.isValid).toBe(true);
    expect(buyRes.error).toBeNull();

    const sellRes = validatePriceGeometry('SELL', 50000, 51000);
    expect(sellRes.isValid).toBe(true);
    expect(sellRes.error).toBeNull();
  });
});

describe('RiskSimulatorForm Component', () => {
  const initialData: RiskSimulationRequestDTO = {
    symbol: 'BTCUSDT',
    side: 'BUY',
    entry_price: 50000,
    sl_price: 49000,
    wallet_balance: 1000,
    requested_leverage: 20,
    risk_percent: 2.0,
  };

  it('renders form fields with default simulation values', () => {
    renderWithQuery(
      <RiskSimulatorForm formData={initialData} onChange={vi.fn()} />
    );

    expect(screen.getByText('Simulation Parameters')).toBeInTheDocument();
    expect(screen.getByDisplayValue('50000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('49000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('1000')).toBeInTheDocument();
    expect(screen.getByText('2.0% of Balance')).toBeInTheDocument();
  });

  it('triggers onChange when direction button or risk pills are clicked', async () => {
    const handleChange = vi.fn();
    renderWithQuery(
      <RiskSimulatorForm formData={initialData} onChange={handleChange} />
    );

    const sellBtn = screen.getByRole('button', { name: /SELL \/ SHORT/i });
    await userEvent.click(sellBtn);

    expect(handleChange).toHaveBeenCalledWith(
      expect.objectContaining({ side: 'SELL' })
    );

    const risk1Btn = screen.getByRole('button', { name: '1.0%' });
    await userEvent.click(risk1Btn);

    expect(handleChange).toHaveBeenCalledWith(
      expect.objectContaining({ risk_percent: 1.0 })
    );
  });
});

describe('SimulationResultCard Component', () => {
  it('renders simulation metrics and SAFE status badge', () => {
    renderWithQuery(<SimulationResultCard result={mockSimulationResult} />);

    expect(screen.getByText('Position Sizing & Risk Telemetry')).toBeInTheDocument();
    expect(screen.getByText(/0.02/i)).toBeInTheDocument(); // position size
    expect(screen.getByText('$50.00')).toBeInTheDocument(); // required margin
    expect(screen.getAllByText('$20.00').length).toBeGreaterThanOrEqual(1); // loss at SL
    expect(screen.getAllByText('$47,500.00').length).toBeGreaterThanOrEqual(1); // estimated liq
    expect(screen.getByText(/SAFE \(2% RISK CAP\)/i)).toBeInTheDocument();
  });

  it('renders dynamic leverage downscaling banner when is_leverage_downscaled is true', () => {
    renderWithQuery(
      <SimulationResultCard
        result={mockDownscaledResult}
        requestedLeverage={50}
      />
    );

    expect(
      screen.getByText('Dynamic Leverage Downscaling Activated')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Leverage disesuaikan dari/i)
    ).toBeInTheDocument();
  });

  it('renders geometry error banner when geometryError prop is provided', () => {
    renderWithQuery(
      <SimulationResultCard
        result={null}
        geometryError="Stop Loss must be BELOW Entry price"
      />
    );

    expect(screen.getByText('Invalid Simulation Geometry')).toBeInTheDocument();
    expect(
      screen.getByText('Stop Loss must be BELOW Entry price')
    ).toBeInTheDocument();
  });
});

describe('LiquidationVisualizer Component', () => {
  it('renders Entry, Stop Loss, and Liquidation price nodes', () => {
    render(
      <LiquidationVisualizer
        side="BUY"
        entryPrice={50000}
        slPrice={49000}
        liqPrice={47500}
      />
    );

    expect(screen.getByText('1. Entry Price')).toBeInTheDocument();
    expect(screen.getByText('2. Stop Loss (Risk)')).toBeInTheDocument();
    expect(screen.getByText('3. Estimated Liq')).toBeInTheDocument();
    expect(screen.getByText('$50,000.00')).toBeInTheDocument();
    expect(screen.getByText('$49,000.00')).toBeInTheDocument();
    expect(screen.getByText('$47,500.00')).toBeInTheDocument();
  });
});
