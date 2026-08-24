import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getStrategiesApi, updateStrategyApi } from '@/api/endpoints/strategies';
import { StrategyDTO, StrategyUpdateRequestDTO } from '@/types/strategies';

export function useStrategies() {
  return useQuery<StrategyDTO[]>({
    queryKey: ['strategies'],
    queryFn: getStrategiesApi,
    staleTime: 30000,
  });
}

export function useUpdateStrategyMutation() {
  const queryClient = useQueryClient();

  return useMutation<
    StrategyDTO,
    Error,
    { id: number; payload: StrategyUpdateRequestDTO }
  >({
    mutationFn: ({ id, payload }) => updateStrategyApi(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
  });
}
