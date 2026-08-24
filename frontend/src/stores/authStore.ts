import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import axios from 'axios';
import { AuthState, LoginRequestDTO, UserDTO } from '@/types/auth';

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (credentials: LoginRequestDTO): Promise<boolean> => {
        set({ isLoading: true, error: null });
        try {
          const response = await axios.post('/api/v1/auth/login', credentials, {
            headers: { 'Content-Type': 'application/json' },
          });

          const data = response.data;
          const accessToken = data.access_token;
          const user: UserDTO = data.user;
          // In some setups, refresh_token is returned in body or assumed to be access_token fallback
          const refreshToken = data.refresh_token || data.access_token;

          set({
            accessToken,
            refreshToken,
            user,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });

          return true;
        } catch (err: unknown) {
          let errorMessage = 'Invalid username or password';
          if (axios.isAxiosError(err) && err.response?.data?.detail) {
            errorMessage = err.response.data.detail;
          } else if (err instanceof Error) {
            errorMessage = err.message;
          }

          set({
            isLoading: false,
            error: errorMessage,
            isAuthenticated: false,
          });
          return false;
        }
      },

      logout: () => {
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        });
      },

      setAccessToken: (token: string) => {
        set({
          accessToken: token,
          isAuthenticated: true,
        });
      },

      clearAuth: () => {
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        });
      },

      checkAuth: async () => {
        const { refreshToken, accessToken } = get();

        // If we already have active accessToken in memory, verify with /auth/me
        if (accessToken) {
          try {
            const res = await axios.get('/api/v1/auth/me', {
              headers: { Authorization: `Bearer ${accessToken}` },
            });
            set({ user: res.data, isAuthenticated: true });
            return;
          } catch {
            // Token expired, fallthrough to refresh
          }
        }

        // If we have refreshToken, try refreshing
        if (refreshToken) {
          set({ isLoading: true });
          try {
            const refreshRes = await axios.post(
              '/api/v1/auth/refresh',
              { refresh_token: refreshToken },
              { headers: { 'Content-Type': 'application/json' } }
            );
            const newAccessToken = refreshRes.data.access_token;
            set({ accessToken: newAccessToken });

            const meRes = await axios.get('/api/v1/auth/me', {
              headers: { Authorization: `Bearer ${newAccessToken}` },
            });

            set({
              user: meRes.data,
              isAuthenticated: true,
              isLoading: false,
            });
          } catch {
            get().clearAuth();
            set({ isLoading: false });
          }
        } else {
          set({ isAuthenticated: false, isLoading: false });
        }
      },
    }),
    {
      name: 'cryptobot-auth-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    }
  )
);
