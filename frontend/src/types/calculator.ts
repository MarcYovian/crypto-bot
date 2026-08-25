export interface RiskSimulationRequestDTO {
  symbol: string;
  side: 'BUY' | 'SELL';
  entry_price: number;
  sl_price: number;
  wallet_balance: number;
  requested_leverage: number;
  risk_percent: number;
}

export interface RiskSimulationResponseDTO {
  symbol: string;
  side: 'BUY' | 'SELL';
  max_allowed_loss_usdt: number;
  calculated_position_size: number;
  required_margin_usdt: number;
  effective_leverage: number;
  is_leverage_downscaled: boolean;
  estimated_liquidation_price: number;
  stop_distance_usdt: number;
  projected_loss_at_sl_usdt: number;
  is_safe: boolean;
}
