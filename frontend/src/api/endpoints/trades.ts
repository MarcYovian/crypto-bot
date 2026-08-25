import { apiClient } from '@/api/client';
import {
  ActiveTradeDTO,
  CloseTradeRequestDTO,
  GenericActionResponseDTO,
  PaginatedTradeHistoryDTO,
  TradeHistoryQueryParams,
  TradeDetailDTO,
} from '@/types/trades';

/**
 * Fetch all currently open / active positions with live mark price and TP progress.
 */
export async function getActiveTradesApi(
  accountId: number = 1
): Promise<ActiveTradeDTO[]> {
  const res = await apiClient.get<ActiveTradeDTO[]>('/trades/active', {
    params: { account_id: accountId },
  });
  return res.data;
}

/**
 * Execute emergency or manual market close for an active position.
 */
export async function closeTradeApi(
  tradeId: number,
  reason: string = 'UI_MANUAL_CLOSE'
): Promise<GenericActionResponseDTO> {
  const payload: CloseTradeRequestDTO = { reason };
  const res = await apiClient.post<GenericActionResponseDTO>(
    `/trades/${tradeId}/close`,
    payload
  );
  return res.data;
}

/**
 * Fetch paginated trade history with optional symbol, outcome, and date filters.
 */
export async function getTradeHistoryApi(
  params: TradeHistoryQueryParams = {}
): Promise<PaginatedTradeHistoryDTO> {
  const res = await apiClient.get<PaginatedTradeHistoryDTO>('/trades/history', {
    params: {
      account_id: params.account_id ?? 1,
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      symbol: params.symbol || undefined,
      result: params.result && params.result !== 'ALL' ? params.result : undefined,
      start_date: params.start_date || undefined,
      end_date: params.end_date || undefined,
    },
  });
  return res.data;
}

/**
 * Fetch comprehensive deep 5-level detail for a specific trade.
 */
export async function getTradeDetailApi(
  tradeId: number
): Promise<TradeDetailDTO> {
  const res = await apiClient.get<TradeDetailDTO>(`/trades/${tradeId}`);
  return res.data;
}
