import { describe, it, expect, beforeEach, vi } from 'vitest';
import { apiClient } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import axios from 'axios';

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>();
  return {
    ...actual,
    default: {
      ...actual.default,
      create: actual.default.create,
      post: vi.fn(),
      get: vi.fn(),
      isAxiosError: actual.default.isAxiosError,
    },
  };
});

describe('Axios Interceptor & Silent Token Refresh (client.ts)', () => {
  beforeEach(() => {
    useAuthStore.getState().clearAuth();
    vi.clearAllMocks();
  });

  it('injects Authorization Bearer header on outgoing requests', async () => {
    useAuthStore.setState({ accessToken: 'valid-test-token' });

    // Mock internal adapter response
    const mockAdapter = vi.fn().mockResolvedValue({
      data: { status: 'ok' },
      status: 200,
      headers: {},
      config: {},
    });

    apiClient.defaults.adapter = mockAdapter;

    await apiClient.get('/test-endpoint');

    expect(mockAdapter).toHaveBeenCalled();
    const requestConfig = mockAdapter.mock.calls[0][0];
    expect(requestConfig.headers.Authorization).toBe('Bearer valid-test-token');
  });

  it('handles 401 with silent token refresh and request replay', async () => {
    useAuthStore.setState({
      accessToken: 'expired-token',
      refreshToken: 'valid-refresh-token',
      isAuthenticated: true,
    });

    // Mock refresh API response
    (axios.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { access_token: 'fresh-new-token', token_type: 'bearer' },
    });

    let callCount = 0;
    const mockAdapter = vi.fn().mockImplementation((config) => {
      callCount++;
      if (callCount === 1) {
        // First call fails with 401
        return Promise.reject({
          response: { status: 401, data: { detail: 'Token expired' } },
          config,
        });
      }
      // Replayed call succeeds with 200
      return Promise.resolve({
        data: { success: true },
        status: 200,
        headers: {},
        config,
      });
    });

    apiClient.defaults.adapter = mockAdapter;

    const res = await apiClient.get('/trades/active');

    expect(axios.post).toHaveBeenCalledWith(
      '/api/v1/auth/refresh',
      { refresh_token: 'valid-refresh-token' },
      expect.anything()
    );
    expect(useAuthStore.getState().accessToken).toBe('fresh-new-token');
    expect(res.data).toEqual({ success: true });
  });

  it('clears auth store when refresh token fails', async () => {
    useAuthStore.setState({
      accessToken: 'expired-token',
      refreshToken: 'expired-refresh-token',
      isAuthenticated: true,
    });

    // Mock refresh API rejection
    (axios.post as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
      response: { status: 401, data: { detail: 'Invalid refresh token' } },
    });

    const mockAdapter = vi.fn().mockImplementation((config) => {
      return Promise.reject({
        response: { status: 401, data: { detail: 'Token expired' } },
        config,
      });
    });

    apiClient.defaults.adapter = mockAdapter;

    await expect(apiClient.get('/trades/active')).rejects.toBeDefined();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().accessToken).toBeNull();
  });
});
