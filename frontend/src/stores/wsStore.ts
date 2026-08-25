import { create } from 'zustand';
import { WebSocketConnectionStatus } from '@/types/websocket';

export interface WebSocketStoreState {
  status: WebSocketConnectionStatus;
  latencyMs: number | null;
  lastPingTimestamp: number | null;
  reconnectAttempts: number;
  isPollingFallback: boolean;

  setStatus: (status: WebSocketConnectionStatus) => void;
  setLatency: (latencyMs: number) => void;
  setLastPing: (timestamp: number) => void;
  incrementAttempts: () => void;
  resetAttempts: () => void;
  setPollingFallback: (isPolling: boolean) => void;
}

export const useWebSocketStore = create<WebSocketStoreState>((set) => ({
  status: 'DISCONNECTED',
  latencyMs: null,
  lastPingTimestamp: null,
  reconnectAttempts: 0,
  isPollingFallback: false,

  setStatus: (status) =>
    set((state) => ({
      status,
      // If connected, turn off polling fallback
      isPollingFallback: status === 'CONNECTED' ? false : state.isPollingFallback,
    })),

  setLatency: (latencyMs) => set({ latencyMs }),

  setLastPing: (timestamp) => set({ lastPingTimestamp: timestamp }),

  incrementAttempts: () =>
    set((state) => {
      const nextAttempts = state.reconnectAttempts + 1;
      return {
        reconnectAttempts: nextAttempts,
        // After 5 attempts, engage polling fallback
        isPollingFallback: nextAttempts >= 5,
        status: 'RECONNECTING',
      };
    }),

  resetAttempts: () =>
    set({
      reconnectAttempts: 0,
      isPollingFallback: false,
    }),

  setPollingFallback: (isPollingFallback) => set({ isPollingFallback }),
}));
