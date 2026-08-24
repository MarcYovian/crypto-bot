import { apiClient } from '@/api/client';
import {
  LoginRequestDTO,
  LoginResponseDTO,
  TokenRefreshRequestDTO,
  TokenRefreshResponseDTO,
  UserDTO,
} from '@/types/auth';

/**
 * Authenticate user with username and password.
 */
export async function loginApi(payload: LoginRequestDTO): Promise<LoginResponseDTO> {
  const res = await apiClient.post<LoginResponseDTO>('/auth/login', payload);
  return res.data;
}

/**
 * Request new JWT access token using a valid refresh token.
 */
export async function refreshApi(refreshToken: string): Promise<TokenRefreshResponseDTO> {
  const payload: TokenRefreshRequestDTO = { refresh_token: refreshToken };
  const res = await apiClient.post<TokenRefreshResponseDTO>('/auth/refresh', payload);
  return res.data;
}

/**
 * Fetch authenticated user profile.
 */
export async function getMeApi(): Promise<UserDTO> {
  const res = await apiClient.get<UserDTO>('/auth/me');
  return res.data;
}
