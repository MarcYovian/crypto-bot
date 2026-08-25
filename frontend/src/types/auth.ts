import { Role } from '@/types/common';

export interface UserDTO {
  id: number;
  username: string;
  role: Role;
}

export interface LoginRequestDTO {
  username: string;
  password: string;
}

export interface LoginResponseDTO {
  access_token: string;
  token_type: string;
  refresh_token?: string;
  user: UserDTO;
}

export interface TokenRefreshRequestDTO {
  refresh_token: string;
}

export interface TokenRefreshResponseDTO {
  access_token: string;
  token_type: string;
}

export interface AuthState {
  user: UserDTO | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (credentials: LoginRequestDTO) => Promise<boolean>;
  logout: () => void;
  setAccessToken: (token: string) => void;
  clearAuth: () => void;
  checkAuth: () => Promise<void>;
}
