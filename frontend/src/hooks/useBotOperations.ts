import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getBotStatusApi,
  pauseBotApi,
  resumeBotApi,
  panicCloseApi,
  getSettingsApi,
  updateSettingsApi,
  saveCredentialsApi,
} from '@/api/endpoints/bot';
import {
  BotStatusDTO,
  GenericActionResponseDTO,
  BotSettingsDTO,
  BotSettingsUpdateRequestDTO,
  TradingCredentialCreateRequestDTO,
  CredentialSaveResponseDTO,
  PanicCloseResponseDTO,
} from '@/types/bot';

export function useBotStatus() {
  return useQuery<BotStatusDTO>({
    queryKey: ['bot', 'status'],
    queryFn: getBotStatusApi,
    refetchInterval: 5000,
    staleTime: 4000,
  });
}

export function usePauseBotMutation() {
  const queryClient = useQueryClient();

  return useMutation<GenericActionResponseDTO, Error>({
    mutationFn: pauseBotApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bot', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });
}

export function useResumeBotMutation() {
  const queryClient = useQueryClient();

  return useMutation<GenericActionResponseDTO, Error>({
    mutationFn: resumeBotApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bot', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });
}

export function usePanicCloseMutation() {
  const queryClient = useQueryClient();

  return useMutation<PanicCloseResponseDTO, Error, boolean>({
    mutationFn: (confirmation: boolean) => panicCloseApi(confirmation),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bot', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['trades', 'active'] });
      queryClient.invalidateQueries({ queryKey: ['trades', 'history'] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'summary'] });
    },
  });
}

export function useBotSettings() {
  return useQuery<BotSettingsDTO>({
    queryKey: ['settings'],
    queryFn: getSettingsApi,
    staleTime: 30000,
  });
}

export function useUpdateSettingsMutation() {
  const queryClient = useQueryClient();

  return useMutation<BotSettingsDTO, Error, BotSettingsUpdateRequestDTO>({
    mutationFn: (payload: BotSettingsUpdateRequestDTO) => updateSettingsApi(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });
}

export function useSaveCredentialsMutation() {
  const queryClient = useQueryClient();

  return useMutation<CredentialSaveResponseDTO, Error, TradingCredentialCreateRequestDTO>({
    mutationFn: (payload: TradingCredentialCreateRequestDTO) => saveCredentialsApi(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analytics', 'summary'] });
    },
  });
}
