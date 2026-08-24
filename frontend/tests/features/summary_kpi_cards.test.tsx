import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SummaryKPICards } from '@/features/dashboard/components/SummaryKPICards';
import { AnalyticsSummaryDTO } from '@/types/analytics';

const mockSummary: AnalyticsSummaryDTO = {
  total_balance_usdt: 10450.5,
  free_margin_usdt: 9800.2,
  daily_realized_pnl: 45.5,
  daily_pnl_percent: 0.45,
  daily_risk_budget: 200.0,
  remaining_risk_budget: 154.5,
  win_rate: 72.5,
  total_trades_count: 40,
  winning_trades_count: 29,
  losing_trades_count: 11,
  profit_factor: 2.85,
  active_trades_count: 2,
};

describe('SummaryKPICards Component', () => {
  it('renders all 6 metric cards with formatted numbers', () => {
    render(<SummaryKPICards summary={mockSummary} />);

    expect(screen.getByText('Total Balance')).toBeInTheDocument();
    expect(screen.getByText('$10,450.50')).toBeInTheDocument();

    expect(screen.getByText('Free Margin')).toBeInTheDocument();
    expect(screen.getByText('$9,800.20')).toBeInTheDocument();

    expect(screen.getByText('Daily Realized PnL')).toBeInTheDocument();
    expect(screen.getByText('+$45.50')).toBeInTheDocument();

    expect(screen.getByText('Win Rate')).toBeInTheDocument();
    expect(screen.getByText('72.50%')).toBeInTheDocument();

    expect(screen.getByText('Profit Factor')).toBeInTheDocument();
    expect(screen.getByText('2.85')).toBeInTheDocument();

    expect(screen.getByText('Remaining Risk')).toBeInTheDocument();
    expect(screen.getByText('$154.50')).toBeInTheDocument();
  });

  it('renders negative PnL in rose color', () => {
    const lossSummary: AnalyticsSummaryDTO = {
      ...mockSummary,
      daily_realized_pnl: -35.25,
      daily_pnl_percent: -0.35,
    };

    render(<SummaryKPICards summary={lossSummary} />);

    const pnlElement = screen.getByText('-$35.25');
    expect(pnlElement).toBeInTheDocument();
    expect(pnlElement).toHaveClass('text-rose-400');
  });

  it('triggers warning style when remaining risk budget is <= 20%', () => {
    const lowBudgetSummary: AnalyticsSummaryDTO = {
      ...mockSummary,
      daily_risk_budget: 200.0,
      remaining_risk_budget: 30.0, // 30 <= 20% of 200 (40)
    };

    const { container } = render(<SummaryKPICards summary={lowBudgetSummary} />);

    const warningCard = container.querySelector('.border-amber-500\\/50');
    expect(warningCard).toBeInTheDocument();
  });

  it('handles zero trades safely without NaN or exceptions', () => {
    const zeroSummary: AnalyticsSummaryDTO = {
      total_balance_usdt: 10000.0,
      free_margin_usdt: 10000.0,
      daily_realized_pnl: 0,
      daily_pnl_percent: 0,
      daily_risk_budget: 200.0,
      remaining_risk_budget: 200.0,
      win_rate: 0,
      total_trades_count: 0,
      winning_trades_count: 0,
      losing_trades_count: 0,
      profit_factor: 0,
      active_trades_count: 0,
    };

    render(<SummaryKPICards summary={zeroSummary} />);

    expect(screen.getAllByText('0.00%').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('0.00')).toBeInTheDocument();
  });
});
