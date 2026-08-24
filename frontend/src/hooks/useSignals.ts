import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSignalsFeedApi, manualExecuteSignalApi } from '@/api/endpoints/signals';
import {
  PaginatedSignalListDTO,
  SignalQueryParams,
  ManualSignalExecutionRequestDTO,
  TradeExecutionResultDTO,
} from '@/types/signals';

export function useSignalsFeed(params: SignalQueryParams = {}) {
  return useQuery<PaginatedSignalListDTO>({
    queryKey: ['signals', 'feed', params],
    queryFn: () => getSignalsFeedApi(params),
    refetchInterval: 5000,
    staleTime: 3000,
  });
}

export function useManualExecuteSignal() {
  const queryClient = useQueryClient();

  return useMutation<
    TradeExecutionResultDTO,
    Error,
    { payload: ManualSignalExecutionRequestDTO; accountId?: number }
  >({
    mutationFn: ({ payload, accountId = 1 }) =>
      manualExecuteSignalApi(payload, accountId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['signals'] });
      queryClient.invalidateQueries({ queryKey: ['trades', 'active'] });
      queryClient.invalidateQueries({ queryKey: ['trades', 'history'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
    },
  });
}
