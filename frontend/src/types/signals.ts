import { TradeSide } from './trades';

export type SignalStatus =
  | 'ALL'
  | 'PENDING'
  | 'PROCESSED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'RECEIVED'
  | 'EXECUTED'
  | 'CANCELLED';

export interface SignalItemDTO {
  id: number;
  trace_id: string | null;
  raw_text: string | null;
  symbol: string;
  side: TradeSide;
  entry_price: number | null;
  sl_price: number | null;
  tp_targets: number[];
  confidence_score: number | null;
  status: string;
  created_at: string;
}

export interface PaginatedSignalListDTO {
  total: number;
  page: number;
  page_size: number;
  items: SignalItemDTO[];
}

export interface SignalQueryParams {
  account_id?: number;
  page?: number;
  page_size?: number;
  status?: string;
}

export interface ManualSignalExecutionRequestDTO {
  symbol: string;
  side: TradeSide;
  entry_price: number;
  sl_price: number;
  tp_targets: number[];
  leverage?: number;
  auto_tp_sl?: boolean;
}

export interface TradeExecutionResultDTO {
  is_success: boolean;
  trade_id: number | null;
  symbol: string;
  side: string;
  position_size: number;
  leverage: number | null;
  entry_order_id: string | null;
  sl_order_id: string | null;
  tp_order_ids: string[];
  message: string;
}
