import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getActiveTradesApi, closeTradeApi } from '@/api/endpoints/trades';
import { ActiveTradeDTO } from '@/types/trades';

export function useActiveTrades(accountId: number = 1) {
  return useQuery<ActiveTradeDTO[]>({
    queryKey: ['trades', 'active'],
    queryFn: () => getActiveTradesApi(accountId),
    refetchInterval: 5000,
    staleTime: 2000,
  });
}

export function useCloseTradeMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      tradeId,
      reason,
    }: {
      tradeId: number;
      reason?: string;
    }) => closeTradeApi(tradeId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trades', 'active'] });
      queryClient.invalidateQueries({ queryKey: ['trades', 'history'] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'summary'] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'equity-curve'] });
    },
  });
}
