export interface TPAllocationDTO {
  tp_level: number;
  percentage: number;
}

export interface StrategyDTO {
  id: number;
  name: string;
  tp_allocations: TPAllocationDTO[];
  bep_trigger_level: number;
  trailing_trigger_level: number;
  is_active: boolean;
}

export interface StrategyUpdateRequestDTO {
  tp1_percent?: number;
  tp2_percent?: number;
  tp3_percent?: number;
  bep_trigger_level?: number;
  trailing_trigger_level?: number;
}
