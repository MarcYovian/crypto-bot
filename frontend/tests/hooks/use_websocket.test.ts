import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useAuthStore } from '@/stores/authStore';
import { wsService } from '@/services/websocketService';

describe('useWebSocket Hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.spyOn(wsService, 'connect').mockImplementation(() => {});
    vi.spyOn(wsService, 'disconnect').mockImplementation(() => {});
    useAuthStore.getState().clearAuth();
  });

  const createWrapper = () => {
    return ({ children }: { children: React.ReactNode }) => (
      React.createElement(QueryClientProvider, { client: queryClient }, children)
    );
  };

  it('connects when authenticated and disconnects when unauthenticated', () => {
    useAuthStore.setState({
      isAuthenticated: true,
      accessToken: 'sample-access-token',
    });

    const { rerender } = renderHook(() => useWebSocket(), {
      wrapper: createWrapper(),
    });

    expect(wsService.connect).toHaveBeenCalledWith('sample-access-token');

    // Simulate logout
    act(() => {
      useAuthStore.setState({
        isAuthenticated: false,
        accessToken: null,
      });
    });
    rerender();

    expect(wsService.disconnect).toHaveBeenCalled();
  });

  it('invalidates queries when trading events are dispatched', () => {
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    renderHook(() => useWebSocket(), {
      wrapper: createWrapper(),
    });

    // Dispatch TRADE_OPENED
    wsService.dispatch('TRADE_OPENED', { trade_id: 1, symbol: 'BTCUSDT' });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['trades', 'active'],
    });

    // Dispatch TP_HIT
    wsService.dispatch('TP_HIT', { trade_id: 1, tp_index: 1 });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['analytics', 'summary'],
    });

    // Dispatch TRADE_CLOSED
    wsService.dispatch('TRADE_CLOSED', { trade_id: 1 });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['trades', 'history'],
    });
  });
});
