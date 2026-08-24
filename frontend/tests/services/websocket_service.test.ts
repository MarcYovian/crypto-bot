import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { wsService } from '@/services/websocketService';
import { useWebSocketStore } from '@/stores/wsStore';
import { useAuthStore } from '@/stores/authStore';

// Mock WebSocket
class MockWebSocket {
  public static instances: MockWebSocket[] = [];
  public url: string;
  public readyState: number = WebSocket.CONNECTING;
  public onopen: (() => void) | null = null;
  public onmessage: ((e: MessageEvent) => void) | null = null;
  public onerror: (() => void) | null = null;
  public onclose: ((e: CloseEvent) => void) | null = null;
  public send = vi.fn();
  public close = vi.fn().mockImplementation(() => {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code: 1000, reason: 'Normal' }));
    }
  });

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = WebSocket.OPEN;
      if (this.onopen) this.onopen();
    }, 10);
  }
}

describe('WebSocketService', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    (global as unknown as { WebSocket: typeof MockWebSocket }).WebSocket = MockWebSocket;
    useWebSocketStore.getState().resetAttempts();
    useWebSocketStore.getState().setStatus('DISCONNECTED');
    useAuthStore.getState().clearAuth();
  });

  afterEach(() => {
    wsService.disconnect();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('connects to WebSocket endpoint with token in query params', () => {
    wsService.connect('my-test-jwt-token');

    expect(MockWebSocket.instances.length).toBe(1);
    expect(MockWebSocket.instances[0].url).toContain('/api/v1/ws?token=my-test-jwt-token');
    expect(useWebSocketStore.getState().status).toBe('CONNECTING');

    // Fast-forward to open event
    vi.advanceTimersByTime(20);
    expect(useWebSocketStore.getState().status).toBe('CONNECTED');
  });

  it('handles PONG heartbeat and calculates latency', () => {
    wsService.connect('my-test-jwt-token');
    vi.advanceTimersByTime(20);

    const socket = MockWebSocket.instances[0];

    // Simulate 30s ping
    useWebSocketStore.getState().setLastPing(Date.now() - 45); // 45ms ago

    if (socket.onmessage) {
      socket.onmessage(
        new MessageEvent('message', {
          data: JSON.stringify({ event: 'PONG', data: { status: 'alive' } }),
        })
      );
    }

    expect(useWebSocketStore.getState().latencyMs).toBeGreaterThanOrEqual(45);
  });

  it('registers event listeners and dispatches events', () => {
    wsService.connect('my-test-jwt-token');
    vi.advanceTimersByTime(20);

    const socket = MockWebSocket.instances[0];
    const tradeListener = vi.fn();

    const unsubscribe = wsService.on('TRADE_OPENED', tradeListener);

    const mockPayload = {
      event: 'TRADE_OPENED',
      data: { trade_id: 101, symbol: 'BTCUSDT', side: 'BUY' },
    };

    if (socket.onmessage) {
      socket.onmessage(
        new MessageEvent('message', {
          data: JSON.stringify(mockPayload),
        })
      );
    }

    expect(tradeListener).toHaveBeenCalledTimes(1);
    expect(tradeListener).toHaveBeenCalledWith(mockPayload.data);

    // Test unsubscribe
    unsubscribe();
    if (socket.onmessage) {
      socket.onmessage(
        new MessageEvent('message', {
          data: JSON.stringify(mockPayload),
        })
      );
    }
    expect(tradeListener).toHaveBeenCalledTimes(1);
  });

  it('schedules reconnect with exponential backoff on unexpected close', () => {
    wsService.connect('my-test-jwt-token');
    vi.advanceTimersByTime(20);

    const socket = MockWebSocket.instances[0];

    // Trigger unexpected close (not manual)
    if (socket.onclose) {
      socket.onclose(new CloseEvent('close', { code: 1006, reason: 'Abnormal' }));
    }

    expect(useWebSocketStore.getState().status).toBe('RECONNECTING');
    expect(useWebSocketStore.getState().reconnectAttempts).toBe(1);

    // Fast forward backoff timer (~1.5s)
    vi.advanceTimersByTime(2000);

    expect(MockWebSocket.instances.length).toBe(2);
  });

  it('disconnect cleanly stops connections and heartbeat', () => {
    wsService.connect('my-test-jwt-token');
    vi.advanceTimersByTime(20);

    wsService.disconnect();

    expect(useWebSocketStore.getState().status).toBe('DISCONNECTED');
    expect(useWebSocketStore.getState().reconnectAttempts).toBe(0);
  });
});
