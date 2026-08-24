/** Common domain and shared interface types */

export type Role = 'ADMIN' | 'VIEWER';

export type TradeSide = 'BUY' | 'SELL';

export type TradeStatus =
  | 'WAITING_ENTRY'
  | 'OPEN'
  | 'PARTIAL'
  | 'CLOSED'
  | 'CANCELLED';

export type TradeResult = 'WIN' | 'LOSS' | 'BREAKEVEN' | 'CANCELLED';

export type BotTradingStatus = 'ACTIVE' | 'PAUSED' | 'CIRCUIT_BREAKER';

export interface PaginationParams {
  page?: number;
  page_size?: number;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface ApiResponse<T = unknown> {
  success?: boolean;
  message?: string;
  data?: T;
  detail?: string;
  code?: string;
}

export interface UserProfile {
  id: number;
  username: string;
  role: Role;
}
