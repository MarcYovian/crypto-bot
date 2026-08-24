import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getProvidersApi,
  createProviderApi,
  getProviderAnalyticsApi,
} from '@/api/endpoints/providers';
import {
  SignalProviderDTO,
  SignalProviderCreateRequestDTO,
  ProviderPerformanceDTO,
} from '@/types/providers';

export function useProviders() {
  return useQuery<SignalProviderDTO[]>({
    queryKey: ['providers'],
    queryFn: getProvidersApi,
    staleTime: 30000,
  });
}

export function useProviderAnalytics(id: number | null) {
  return useQuery<ProviderPerformanceDTO>({
    queryKey: ['providers', 'analytics', id],
    queryFn: () => getProviderAnalyticsApi(id!),
    enabled: id !== null && id > 0,
    staleTime: 30000,
  });
}

export function useCreateProviderMutation() {
  const queryClient = useQueryClient();

  return useMutation<SignalProviderDTO, Error, SignalProviderCreateRequestDTO>({
    mutationFn: (payload) => createProviderApi(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] });
    },
  });
}
