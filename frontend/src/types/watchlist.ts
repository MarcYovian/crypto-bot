export interface WatchlistItemDTO {
  id: number;
  symbol: string;
  enabled: boolean;
  max_leverage: number;
  tick_size: number;
  min_qty: number;
}

export interface WatchlistToggleRequestDTO {
  symbol: string;
  enabled: boolean;
}

export interface LeverageBracketDTO {
  bracket: number;
  initial_leverage: number;
  notional_cap: number;
  notional_floor?: number;
  maint_margin_ratio: number;
  cum?: number;
}

export interface InstrumentDTO {
  symbol: string;
  base_asset: string;
  quote_asset: string;
  price_precision: number;
  qty_precision: number;
  tick_size: number;
  step_size: number;
  min_notional: number;
  max_leverage: number;
  brackets?: LeverageBracketDTO[];
}

export interface SyncInstrumentsResponseDTO {
  synced_instruments: number;
  synced_brackets: number;
  timestamp: string;
}
