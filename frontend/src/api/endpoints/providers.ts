import { apiClient } from '@/api/client';
import {
  SignalProviderDTO,
  SignalProviderCreateRequestDTO,
  ProviderPerformanceDTO,
} from '@/types/providers';

/**
 * Fetch all configured signal channels and providers.
 */
export async function getProvidersApi(): Promise<SignalProviderDTO[]> {
  const res = await apiClient.get<SignalProviderDTO[]>('/providers');
  return res.data;
}

/**
 * Register a new Telegram signal provider channel (Admin only).
 */
export async function createProviderApi(
  payload: SignalProviderCreateRequestDTO
): Promise<SignalProviderDTO> {
  const res = await apiClient.post<SignalProviderDTO>('/providers', payload);
  return res.data;
}

/**
 * Fetch performance metrics for a specific signal provider.
 */
export async function getProviderAnalyticsApi(
  id: number
): Promise<ProviderPerformanceDTO> {
  const res = await apiClient.get<ProviderPerformanceDTO>(
    `/providers/${id}/analytics`
  );
  return res.data;
}
