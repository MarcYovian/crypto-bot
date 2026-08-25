import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getWatchlistApi,
  toggleWatchlistApi,
  getInstrumentsApi,
  syncInstrumentsApi,
} from '@/api/endpoints/watchlist';
import {
  WatchlistItemDTO,
  InstrumentDTO,
  SyncInstrumentsResponseDTO,
} from '@/types/watchlist';

export function useWatchlist() {
  return useQuery<WatchlistItemDTO[]>({
    queryKey: ['watchlist'],
    queryFn: getWatchlistApi,
    staleTime: 30000,
  });
}

export function useInstruments() {
  return useQuery<InstrumentDTO[]>({
    queryKey: ['instruments'],
    queryFn: getInstrumentsApi,
    staleTime: 300000, // 5 minutes
  });
}

export function useToggleWatchlistMutation() {
  const queryClient = useQueryClient();

  return useMutation<
    WatchlistItemDTO,
    Error,
    { symbol: string; enabled: boolean },
    { previousList?: WatchlistItemDTO[] }
  >({
    mutationFn: ({ symbol, enabled }) => toggleWatchlistApi(symbol, enabled),
    onMutate: async ({ symbol, enabled }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['watchlist'] });

      // Snapshot the previous value
      const previousList = queryClient.getQueryData<WatchlistItemDTO[]>(['watchlist']);

      // Optimistically update to the new value
      if (previousList) {
        queryClient.setQueryData<WatchlistItemDTO[]>(
          ['watchlist'],
          previousList.map((item) =>
            item.symbol === symbol ? { ...item, enabled } : item
          )
        );
      }

      return { previousList };
    },
    onError: (_err, _variables, context) => {
      // Rollback to previous state on error
      if (context?.previousList) {
        queryClient.setQueryData(['watchlist'], context.previousList);
      }
    },
    onSettled: () => {
      // Refetch and invalidate
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      queryClient.invalidateQueries({ queryKey: ['signals'] });
    },
  });
}

export function useSyncInstrumentsMutation() {
  const queryClient = useQueryClient();

  return useMutation<SyncInstrumentsResponseDTO, Error, void>({
    mutationFn: syncInstrumentsApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['instruments'] });
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });
}
