import { apiClient } from '@/api/client';
import {
  RiskSimulationRequestDTO,
  RiskSimulationResponseDTO,
} from '@/types/calculator';

/**
 * Execute live position sizing, margin requirement, and liquidation price simulation.
 */
export async function simulateRiskApi(
  payload: RiskSimulationRequestDTO
): Promise<RiskSimulationResponseDTO> {
  const res = await apiClient.post<RiskSimulationResponseDTO>(
    '/calculator/simulate',
    payload
  );
  return res.data;
}
