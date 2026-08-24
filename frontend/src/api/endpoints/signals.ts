import { apiClient } from '@/api/client';
import {
  PaginatedSignalListDTO,
  SignalQueryParams,
  ManualSignalExecutionRequestDTO,
  TradeExecutionResultDTO,
} from '@/types/signals';

/**
 * Fetch incoming Telegram trading signals feed with status filtering and pagination.
 */
export async function getSignalsFeedApi(
  params: SignalQueryParams = {}
): Promise<PaginatedSignalListDTO> {
  const res = await apiClient.get<PaginatedSignalListDTO>('/signals', {
    params: {
      account_id: params.account_id ?? 1,
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      status: params.status && params.status !== 'ALL' ? params.status : undefined,
    },
  });
  return res.data;
}

/**
 * Execute a trading signal with 1-click execution wizard and server-side risk check.
 */
export async function manualExecuteSignalApi(
  payload: ManualSignalExecutionRequestDTO,
  accountId: number = 1
): Promise<TradeExecutionResultDTO> {
  const res = await apiClient.post<TradeExecutionResultDTO>(
    '/signals/manual-execute',
    payload,
    {
      params: { account_id: accountId },
    }
  );
  return res.data;
}
