import { apiClient } from '@/api/client';
import {
  WatchlistItemDTO,
  WatchlistToggleRequestDTO,
  InstrumentDTO,
  SyncInstrumentsResponseDTO,
} from '@/types/watchlist';

/**
 * Fetch all trading pairs in the active whitelist.
 */
export async function getWatchlistApi(): Promise<WatchlistItemDTO[]> {
  const res = await apiClient.get<WatchlistItemDTO[]>('/watchlist');
  return res.data;
}

/**
 * Toggle active trading whitelist status for a specific symbol pair.
 */
export async function toggleWatchlistApi(
  symbol: string,
  enabled: boolean
): Promise<WatchlistItemDTO> {
  const payload: WatchlistToggleRequestDTO = { symbol, enabled };
  const res = await apiClient.post<WatchlistItemDTO>('/watchlist/toggle', payload);
  return res.data;
}

/**
 * Fetch synchronized Binance Futures contract specifications and leverage brackets.
 */
export async function getInstrumentsApi(): Promise<InstrumentDTO[]> {
  const res = await apiClient.get<InstrumentDTO[]>('/instruments');
  return res.data;
}

/**
 * Trigger manual on-demand synchronization of exchange metadata & leverage brackets from Binance.
 */
export async function syncInstrumentsApi(): Promise<SyncInstrumentsResponseDTO> {
  const res = await apiClient.post<SyncInstrumentsResponseDTO>('/instruments/sync');
  return res.data;
}
