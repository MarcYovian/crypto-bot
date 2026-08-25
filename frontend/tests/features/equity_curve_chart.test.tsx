import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EquityCurveChart } from '@/features/dashboard/components/EquityCurveChart';
import { EquityPointDTO } from '@/types/analytics';

// Mock lightweight-charts
vi.mock('lightweight-charts', () => {
  return {
    createChart: vi.fn().mockReturnValue({
      addAreaSeries: vi.fn().mockReturnValue({
        setData: vi.fn(),
      }),
      subscribeCrosshairMove: vi.fn(),
      timeScale: vi.fn().mockReturnValue({
        fitContent: vi.fn(),
      }),
      applyOptions: vi.fn(),
      remove: vi.fn(),
    }),
    ColorType: { Solid: 'solid' },
  };
});

// Mock ResizeObserver
class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

describe('EquityCurveChart Component', () => {
  beforeEach(() => {
    (global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver;
    vi.clearAllMocks();
  });

  const mockPoints: EquityPointDTO[] = [
    { timestamp: '2026-08-01T00:00:00Z', balance: 10000.0, pnl: 0.0 },
    { timestamp: '2026-08-05T12:00:00Z', balance: 10250.0, pnl: 250.0 },
    { timestamp: '2026-08-10T15:30:00Z', balance: 10450.5, pnl: 200.5 },
  ];

  it('renders timeframe selector buttons', () => {
    render(
      <EquityCurveChart
        points={mockPoints}
        timeframe="30d"
        onTimeframeChange={vi.fn()}
      />
    );

    expect(screen.getByText('7D')).toBeInTheDocument();
    expect(screen.getByText('30D')).toBeInTheDocument();
    expect(screen.getByText('90D')).toBeInTheDocument();
    expect(screen.getByText('ALL')).toBeInTheDocument();
  });

  it('calls onTimeframeChange when a timeframe pill is clicked', async () => {
    const handleTimeframe = vi.fn();

    render(
      <EquityCurveChart
        points={mockPoints}
        timeframe="30d"
        onTimeframeChange={handleTimeframe}
      />
    );

    const sevenDayBtn = screen.getByText('7D');
    await userEvent.click(sevenDayBtn);

    expect(handleTimeframe).toHaveBeenCalledWith('7d');
  });

  it('renders empty state message when points array is empty', () => {
    render(
      <EquityCurveChart
        points={[]}
        timeframe="7d"
        onTimeframeChange={vi.fn()}
      />
    );

    expect(
      screen.getByText(/no equity curve data available for timeframe \(7D\)/i)
    ).toBeInTheDocument();
  });

  it('renders chart container when data points exist', () => {
    render(
      <EquityCurveChart
        points={mockPoints}
        timeframe="30d"
        onTimeframeChange={vi.fn()}
      />
    );

    expect(screen.getByTestId('equity-chart-container')).toBeInTheDocument();
    expect(screen.getByText('$10,450.50')).toBeInTheDocument();
  });
});
