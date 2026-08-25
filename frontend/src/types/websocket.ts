export type WebSocketConnectionStatus =
  | 'CONNECTED'
  | 'CONNECTING'
  | 'RECONNECTING'
  | 'DISCONNECTED';

export type WebSocketEventType =
  | 'CONNECTION_ESTABLISHED'
  | 'PONG'
  | 'TRADE_OPENED'
  | 'ORDER_FILLED'
  | 'TP_HIT'
  | 'SL_HIT'
  | 'TRADE_CLOSED'
  | 'CIRCUIT_BREAKER_TRIGGERED'
  | 'BOT_STATUS_CHANGED'
  | 'TICKER_UPDATE'
  | 'SIGNAL_RECEIVED';

export interface WebSocketEventEnvelope<T = unknown> {
  event: WebSocketEventType | string;
  data: T;
  timestamp?: string;
}

export interface PongPayload {
  status: string;
  client_time?: number;
}

export interface TradeOpenedPayload {
  trade_id: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  entry_price: number;
  quantity: number;
  leverage: number;
  stop_loss: number;
  take_profits: number[];
}

export interface OrderFilledPayload {
  trade_id: number;
  order_id: number;
  symbol: string;
  order_type: string;
  filled_price: number;
  filled_qty: number;
}

export interface TpHitPayload {
  trade_id: number;
  symbol: string;
  tp_index: number;
  tp_price: number;
  realized_pnl: number;
}

export interface SlHitPayload {
  trade_id: number;
  symbol: string;
  sl_price: number;
  realized_pnl: number;
}

export interface TradeClosedPayload {
  trade_id: number;
  symbol: string;
  close_price: number;
  total_realized_pnl: number;
  exit_reason: string;
}

export interface CircuitBreakerPayload {
  reason: string;
  triggered_at: string;
  consecutive_losses?: number;
  daily_drawdown_pct?: number;
}

export interface BotStatusChangedPayload {
  is_running: boolean;
  status: string;
  timestamp: string;
}

export interface TickerUpdatePayload {
  symbol: string;
  mark_price: number;
  index_price?: number;
  funding_rate?: number;
  timestamp: string;
}
