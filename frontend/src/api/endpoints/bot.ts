import { apiClient } from '@/api/client';
import {
  BotStatusDTO,
  GenericActionResponseDTO,
  BotSettingsDTO,
  BotSettingsUpdateRequestDTO,
  TradingCredentialCreateRequestDTO,
  CredentialSaveResponseDTO,
  PanicCloseResponseDTO,
} from '@/types/bot';

/**
 * Retrieve runtime state of the bot engine, circuit breaker, and websocket.
 */
export async function getBotStatusApi(): Promise<BotStatusDTO> {
  const res = await apiClient.get<BotStatusDTO>('/bot/status');
  return res.data;
}

/**
 * Manually pause bot trading engine (Admin only).
 */
export async function pauseBotApi(): Promise<GenericActionResponseDTO> {
  const res = await apiClient.post<GenericActionResponseDTO>('/bot/pause');
  return res.data;
}

/**
 * Resume bot trading engine (Admin only).
 */
export async function resumeBotApi(): Promise<GenericActionResponseDTO> {
  const res = await apiClient.post<GenericActionResponseDTO>('/bot/resume');
  return res.data;
}

/**
 * Emergency close all open trades and cancel all pending orders (Admin only).
 */
export async function panicCloseApi(
  confirmation: boolean
): Promise<PanicCloseResponseDTO> {
  const res = await apiClient.post<PanicCloseResponseDTO>('/bot/panic', {
    confirmation,
  });
  return res.data;
}

/**
 * Fetch active configuration settings.
 */
export async function getSettingsApi(): Promise<BotSettingsDTO> {
  const res = await apiClient.get<BotSettingsDTO>('/settings');
  return res.data;
}

/**
 * Update bot configuration settings (Admin only).
 */
export async function updateSettingsApi(
  payload: BotSettingsUpdateRequestDTO
): Promise<BotSettingsDTO> {
  const res = await apiClient.put<BotSettingsDTO>('/settings', payload);
  return res.data;
}

/**
 * Register or rotate trading API credentials with handshake check (Admin only).
 */
export async function saveCredentialsApi(
  payload: TradingCredentialCreateRequestDTO
): Promise<CredentialSaveResponseDTO> {
  const res = await apiClient.post<CredentialSaveResponseDTO>(
    '/settings/credentials',
    payload
  );
  return res.data;
}
