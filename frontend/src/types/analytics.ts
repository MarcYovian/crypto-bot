export interface AnalyticsSummaryDTO {
  total_balance_usdt: number;
  free_margin_usdt: number;
  daily_realized_pnl: number;
  daily_pnl_percent: number;
  daily_risk_budget: number;
  remaining_risk_budget: number;
  win_rate: number;
  total_trades_count: number;
  winning_trades_count: number;
  losing_trades_count: number;
  profit_factor: number;
  active_trades_count: number;
}

export interface EquityPointDTO {
  timestamp: string;
  balance: number;
  pnl: number;
}

export type TimeframeOption = '7d' | '30d' | '90d' | 'all';
