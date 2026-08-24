export interface SignalProviderDTO {
  id: number;
  name: string;
  channel_id: string | null;
  is_active: boolean;
  confidence_weight: number;
}

export interface SignalProviderCreateRequestDTO {
  name: string;
  channel_id: string;
  confidence_weight: number;
}

export interface ProviderPerformanceDTO {
  provider_id: number;
  provider_name: string;
  total_signals: number;
  executed_trades: number;
  win_rate: number;
  total_net_pnl_usdt: number;
}
