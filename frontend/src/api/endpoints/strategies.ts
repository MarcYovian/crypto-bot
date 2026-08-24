import { apiClient } from '@/api/client';
import { StrategyDTO, StrategyUpdateRequestDTO } from '@/types/strategies';

/**
 * Fetch all configured trading strategies and TP scaling configurations.
 */
export async function getStrategiesApi(): Promise<StrategyDTO[]> {
  const res = await apiClient.get<StrategyDTO[]>('/strategies');
  return res.data;
}

/**
 * Update TP allocation percentages and BEP/Trailing trigger levels (Admin only).
 */
export async function updateStrategyApi(
  id: number,
  payload: StrategyUpdateRequestDTO
): Promise<StrategyDTO> {
  const res = await apiClient.put<StrategyDTO>(`/strategies/${id}`, payload);
  return res.data;
}
