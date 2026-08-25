import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from '@/stores/authStore';
import axios from 'axios';

vi.mock('axios');

describe('Auth Store (useAuthStore)', () => {
  beforeEach(() => {
    useAuthStore.getState().clearAuth();
    vi.clearAllMocks();
  });

  it('initializes with unauthenticated empty state', () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.isLoading).toBe(false);
  });

  it('updates state on successful login', async () => {
    const mockResponse = {
      data: {
        access_token: 'mock-access-token',
        refresh_token: 'mock-refresh-token',
        token_type: 'bearer',
        user: {
          id: 1,
          username: 'admin',
          role: 'ADMIN',
        },
      },
    };

    (axios.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockResponse);

    const success = await useAuthStore.getState().login({
      username: 'admin',
      password: 'AdminPassword123!',
    });

    expect(success).toBe(true);
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user?.username).toBe('admin');
    expect(state.user?.role).toBe('ADMIN');
    expect(state.accessToken).toBe('mock-access-token');
    expect(state.refreshToken).toBe('mock-refresh-token');
    expect(state.error).toBeNull();
  });

  it('sets error and remains unauthenticated on failed login', async () => {
    const mockAxiosError = {
      isAxiosError: true,
      response: {
        data: {
          detail: 'Invalid username or password',
        },
      },
    };

    (axios.post as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(mockAxiosError);
    (axios.isAxiosError as unknown as ReturnType<typeof vi.fn>).mockReturnValue(true);

    const success = await useAuthStore.getState().login({
      username: 'wronguser',
      password: 'wrongpassword',
    });

    expect(success).toBe(false);
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
    expect(state.error).toBe('Invalid username or password');
  });

  it('clears state on logout', () => {
    useAuthStore.setState({
      accessToken: 'token',
      refreshToken: 'refresh',
      user: { id: 1, username: 'admin', role: 'ADMIN' },
      isAuthenticated: true,
    });

    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
  });

  it('updates accessToken with setAccessToken', () => {
    useAuthStore.getState().setAccessToken('new-access-token');

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe('new-access-token');
    expect(state.isAuthenticated).toBe(true);
  });
});
