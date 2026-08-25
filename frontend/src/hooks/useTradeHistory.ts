import { useQuery } from '@tanstack/react-query';
import { getTradeHistoryApi, getTradeDetailApi } from '@/api/endpoints/trades';
import {
  PaginatedTradeHistoryDTO,
  TradeHistoryQueryParams,
  TradeDetailDTO,
} from '@/types/trades';

export function useTradeHistory(params: TradeHistoryQueryParams = {}) {
  return useQuery<PaginatedTradeHistoryDTO>({
    queryKey: ['trades', 'history', params],
    queryFn: () => getTradeHistoryApi(params),
    staleTime: 10000,
  });
}

export function useTradeDetail(tradeId: number | null) {
  return useQuery<TradeDetailDTO>({
    queryKey: ['trades', 'detail', tradeId],
    queryFn: () => {
      if (!tradeId) throw new Error('Trade ID is required');
      return getTradeDetailApi(tradeId);
    },
    enabled: tradeId !== null && tradeId > 0,
    staleTime: 60000,
  });
}
