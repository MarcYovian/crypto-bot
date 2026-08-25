export interface BotStatusDTO {
  is_running: boolean;
  is_paused: boolean;
  trading_status: string;
  circuit_breaker_active: boolean;
  binance_ws_connected: boolean;
  telegram_polling_active: boolean;
  scheduler_jobs_count: number;
  last_heartbeat: string;
}

export interface GenericActionResponseDTO {
  success: boolean;
  message: string;
}

export interface BotSettingsDTO {
  default_leverage: number;
  confidence_threshold: number;
  risk_percent_per_trade: number;
  max_daily_loss_percent: number;
  max_open_trades: number;
  is_paused: boolean;
}

export interface BotSettingsUpdateRequestDTO {
  default_leverage?: number;
  confidence_threshold?: number;
  risk_percent_per_trade?: number;
  max_daily_loss_percent?: number;
  max_open_trades?: number;
}

export interface TradingCredentialCreateRequestDTO {
  api_key: string;
  secret_key: string;
  environment: 'TESTNET' | 'LIVE';
}

export interface CredentialSaveResponseDTO {
  success: boolean;
  account_id: number;
  credential_id: number;
  wallet_balance_usdt: number;
  environment: string;
}

export interface PanicCloseResponseDTO {
  success: boolean;
  closed_trades_count: number;
  canceled_orders_count: number;
  timestamp: string;
}
