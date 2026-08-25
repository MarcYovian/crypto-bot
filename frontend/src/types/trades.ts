export type TradeSide = 'BUY' | 'SELL';
export type TradeStatus = 'WAITING_ENTRY' | 'OPEN' | 'PARTIAL' | 'CLOSED' | 'CANCELLED';
export type TradeOutcome = 'WIN' | 'LOSS' | 'BREAKEVEN' | 'CANCELLED';

export interface ActiveTradeTPLevelDTO {
  level: number;
  price: number;
  is_hit: boolean;
}

export interface ActiveTradeDTO {
  trade_id: number;
  symbol: string;
  side: TradeSide;
  status: TradeStatus;
  entry_price: number | null;
  current_price: number | null;
  sl_price: number | null;
  position_size: number;
  remaining_qty: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  leverage: number;
  margin_mode: 'ISOLATED' | 'CROSSED' | string;
  tp_levels: ActiveTradeTPLevelDTO[];
  opened_at: string | null;
}

export interface CloseTradeRequestDTO {
  reason?: string;
}

export interface GenericActionResponseDTO {
  success: boolean;
  message: string;
  data?: Record<string, unknown>;
}

export interface TradeHistoryItemDTO {
  id: number;
  symbol: string;
  side: TradeSide;
  entry_price: number | null;
  exit_price: number | null;
  position_size: number;
  net_pnl: number | null;
  roi_percent: number | null;
  result: TradeOutcome;
  close_reason: string | null;
  opened_at: string | null;
  closed_at: string | null;
}

export interface PaginatedTradeHistoryDTO {
  total: number;
  page: number;
  page_size: number;
  items: TradeHistoryItemDTO[];
}

export interface TradeHistoryQueryParams {
  account_id?: number;
  page?: number;
  page_size?: number;
  symbol?: string;
  result?: string;
  start_date?: string;
  end_date?: string;
}

export interface TradeRiskDetailDTO {
  risk_amount_usdt: number;
  stop_distance: number;
  required_margin: number;
}

export interface TradeOrderDetailDTO {
  id: number;
  exchange_order_id: string | null;
  purpose: string;
  order_type: string;
  side: TradeSide;
  price: number | null;
  qty: number;
  status: string;
}

export interface TradeExecutionDetailDTO {
  price: number;
  qty: number;
  commission: number;
  realized_pnl: number;
  executed_at: string | null;
}

export interface TradeEventDetailDTO {
  event_type: string;
  payload: string | null;
  created_at: string | null;
}

export interface TradeSummaryDetailDTO {
  gross_pnl: number;
  net_pnl: number;
  commission: number;
  roi: number;
  result: string;
}

export interface TradeDetailDTO {
  trade_id: number;
  symbol: string;
  side: TradeSide;
  status: TradeStatus;
  entry_price: number | null;
  sl_price: number | null;
  position_size: number;
  leverage: number;
  risk_details: TradeRiskDetailDTO | null;
  orders: TradeOrderDetailDTO[];
  executions: TradeExecutionDetailDTO[];
  events: TradeEventDetailDTO[];
  summary: TradeSummaryDetailDTO | null;
}
