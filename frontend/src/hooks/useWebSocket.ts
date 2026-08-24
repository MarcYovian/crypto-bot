import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/authStore';
import { useWebSocketStore } from '@/stores/wsStore';
import { wsService } from '@/services/websocketService';
import { sound } from '@/utils/sound';
import {
  TradeOpenedPayload,
  OrderFilledPayload,
  TpHitPayload,
  SlHitPayload,
  TradeClosedPayload,
  CircuitBreakerPayload,
  BotStatusChangedPayload,
} from '@/types/websocket';

export function useWebSocket() {
  const queryClient = useQueryClient();
  const { isAuthenticated, accessToken } = useAuthStore();
  const { status, latencyMs, reconnectAttempts, isPollingFallback } = useWebSocketStore();

  useEffect(() => {
    if (isAuthenticated && accessToken) {
      wsService.connect(accessToken);
    } else {
      wsService.disconnect();
    }

    return () => {
      // Don't disconnect on normal re-renders unless unmounting while logged out
    };
  }, [isAuthenticated, accessToken]);

  useEffect(() => {
    // Event 1: TRADE_OPENED
    const unsubTradeOpened = wsService.on<TradeOpenedPayload>('TRADE_OPENED', () => {
      queryClient.invalidateQueries({ queryKey: ['trades', 'active'] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'summary'] });
      sound.playOrderFilledSound();
    });

    // Event 2: ORDER_FILLED
    const unsubOrderFilled = wsService.on<OrderFilledPayload>('ORDER_FILLED', (data) => {
      queryClient.invalidateQueries({ queryKey: ['trades', 'active'] });
      if (data?.trade_id) {
        queryClient.invalidateQueries({ queryKey: ['trades', data.trade_id] });
      }
      sound.playOrderFilledSound();
    });

    // Event 3: TP_HIT
    const unsubTpHit = wsService.on<TpHitPayload>('TP_HIT', () => {
      queryClient.invalidateQueries({ queryKey: ['trades', 'active'] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'summary'] });
      sound.playProfitChime();
    });

    // Event 4: SL_HIT
    const unsubSlHit = wsService.on<SlHitPayload>('SL_HIT', () => {
      queryClient.invalidateQueries({ queryKey: ['trades', 'active'] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'summary'] });
      sound.playWarningTone();
    });

    // Event 5: TRADE_CLOSED
    const unsubTradeClosed = wsService.on<TradeClosedPayload>('TRADE_CLOSED', () => {
      queryClient.invalidateQueries({ queryKey: ['trades', 'active'] });
      queryClient.invalidateQueries({ queryKey: ['trades', 'history'] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'summary'] });
      queryClient.invalidateQueries({ queryKey: ['analytics', 'equity-curve'] });
      sound.playProfitChime();
    });

    // Event 6: CIRCUIT_BREAKER_TRIGGERED
    const unsubCircuitBreaker = wsService.on<CircuitBreakerPayload>(
      'CIRCUIT_BREAKER_TRIGGERED',
      () => {
        queryClient.invalidateQueries({ queryKey: ['bot', 'status'] });
        queryClient.invalidateQueries({ queryKey: ['analytics', 'summary'] });
        sound.playWarningTone();
      }
    );

    // Event 7: BOT_STATUS_CHANGED
    const unsubBotStatus = wsService.on<BotStatusChangedPayload>(
      'BOT_STATUS_CHANGED',
      () => {
        queryClient.invalidateQueries({ queryKey: ['bot', 'status'] });
      }
    );

    return () => {
      unsubTradeOpened();
      unsubOrderFilled();
      unsubTpHit();
      unsubSlHit();
      unsubTradeClosed();
      unsubCircuitBreaker();
      unsubBotStatus();
    };
  }, [queryClient]);

  return {
    status,
    latencyMs,
    reconnectAttempts,
    isPollingFallback,
    wsService,
  };
}
