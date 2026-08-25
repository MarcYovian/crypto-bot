import { useWebSocketStore } from '@/stores/wsStore';
import { useAuthStore } from '@/stores/authStore';
import {
  WebSocketEventEnvelope,
  WebSocketEventType,
} from '@/types/websocket';

type EventHandler<T = unknown> = (data: T) => void;

class WebSocketService {
  private socket: WebSocket | null = null;
  private token: string | null = null;
  private pingIntervalId: ReturnType<typeof setInterval> | null = null;
  private reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null;
  private isManualClose = false;
  private listeners: Map<string, Set<EventHandler<unknown>>> = new Map();

  constructor() {
    if (typeof window !== 'undefined') {
      document.addEventListener('visibilitychange', this.handleVisibilityChange);
    }
  }

  private handleVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
      const isAuthenticated = useAuthStore.getState().isAuthenticated;
      if (
        isAuthenticated &&
        (!this.socket || this.socket.readyState !== WebSocket.OPEN)
      ) {
        this.reconnectImmediate();
      }
    }
  };

  public connect(token: string): void {
    this.token = token;
    this.isManualClose = false;

    // Clear any pending reconnects
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }

    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    useWebSocketStore.getState().setStatus('CONNECTING');

    try {
      const isSecure =
        typeof window !== 'undefined' && window.location.protocol === 'https:';
      const host =
        typeof window !== 'undefined' ? window.location.host : 'localhost:3000';
      const wsProtocol = isSecure ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${host}/api/v1/ws?token=${encodeURIComponent(token)}`;

      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = this.handleOpen;
      this.socket.onmessage = this.handleMessage;
      this.socket.onerror = this.handleError;
      this.socket.onclose = this.handleClose;
    } catch {
      useWebSocketStore.getState().setStatus('DISCONNECTED');
      this.scheduleReconnect();
    }
  }

  private handleOpen = () => {
    useWebSocketStore.getState().setStatus('CONNECTED');
    useWebSocketStore.getState().resetAttempts();
    this.startHeartbeat();
  };

  private handleMessage = (event: MessageEvent) => {
    try {
      const parsed: WebSocketEventEnvelope = JSON.parse(event.data);

      if (parsed.event === 'PONG') {
        const lastPing = useWebSocketStore.getState().lastPingTimestamp;
        if (lastPing) {
          const latency = Date.now() - lastPing;
          useWebSocketStore.getState().setLatency(latency);
        }
        return;
      }

      this.dispatch(parsed.event as WebSocketEventType, parsed.data);
      this.dispatch('*' as WebSocketEventType, parsed);
    } catch {
      // Non-JSON or raw text message
    }
  };

  private handleError = () => {
    // Error will trigger onclose where reconnect logic is handled
  };

  private handleClose = async (event: CloseEvent) => {
    this.stopHeartbeat();
    this.socket = null;

    if (this.isManualClose) {
      useWebSocketStore.getState().setStatus('DISCONNECTED');
      return;
    }

    // Code 1008: Policy Violation (Token Expired)
    if (event.code === 1008) {
      try {
        await useAuthStore.getState().checkAuth();
        const freshToken = useAuthStore.getState().accessToken;
        if (freshToken) {
          this.token = freshToken;
          this.connect(freshToken);
          return;
        }
      } catch {
        useWebSocketStore.getState().setStatus('DISCONNECTED');
        return;
      }
    }

    this.scheduleReconnect();
  };

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.pingIntervalId = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        useWebSocketStore.getState().setLastPing(Date.now());
        this.socket.send('ping');
      }
    }, 30000);
  }

  private stopHeartbeat(): void {
    if (this.pingIntervalId) {
      clearInterval(this.pingIntervalId);
      this.pingIntervalId = null;
    }
  }

  private scheduleReconnect(): void {
    useWebSocketStore.getState().incrementAttempts();
    const attempts = useWebSocketStore.getState().reconnectAttempts;

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s + jitter
    const delay = Math.min(1000 * Math.pow(2, Math.min(attempts - 1, 5)), 30000) + Math.random() * 500;

    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
    }

    this.reconnectTimeoutId = setTimeout(() => {
      const currentToken = this.token || useAuthStore.getState().accessToken;
      if (currentToken && !this.isManualClose) {
        this.connect(currentToken);
      }
    }, delay);
  }

  public reconnectImmediate(): void {
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
    const currentToken = this.token || useAuthStore.getState().accessToken;
    if (currentToken && !this.isManualClose) {
      this.connect(currentToken);
    }
  }

  public disconnect(): void {
    this.isManualClose = true;
    this.token = null;
    this.stopHeartbeat();

    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }

    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }

    useWebSocketStore.getState().setStatus('DISCONNECTED');
    useWebSocketStore.getState().resetAttempts();
  }

  public on<T = unknown>(event: WebSocketEventType | string, handler: EventHandler<T>): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    const set = this.listeners.get(event)!;
    set.add(handler as EventHandler<unknown>);

    return () => {
      this.off(event, handler);
    };
  }

  public off<T = unknown>(event: WebSocketEventType | string, handler: EventHandler<T>): void {
    const set = this.listeners.get(event);
    if (set) {
      set.delete(handler as EventHandler<unknown>);
      if (set.size === 0) {
        this.listeners.delete(event);
      }
    }
  }

  public dispatch(event: WebSocketEventType | string, data: unknown): void {
    const set = this.listeners.get(event);
    if (set) {
      set.forEach((handler) => {
        try {
          handler(data);
        } catch {
          // Prevent handler error from halting listener dispatch loop
        }
      });
    }
  }
}

export const wsService = new WebSocketService();
