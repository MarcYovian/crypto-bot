import { useWebSocketStore } from '@/stores/wsStore';
import { wsService } from '@/services/websocketService';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';

export function ConnectionStatusBadge() {
  const { status, latencyMs, reconnectAttempts, isPollingFallback } = useWebSocketStore();

  const handleManualReconnect = () => {
    if (status !== 'CONNECTED') {
      wsService.reconnectImmediate();
    }
  };

  if (status === 'CONNECTED') {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="cursor-default">
            <Badge variant="profit-neon" size="sm" className="font-mono text-[11px] gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <Wifi className="w-3 h-3 text-emerald-400" />
              <span>LIVE</span>
              {latencyMs !== null && (
                <span className="text-emerald-300/80 font-normal">
                  {latencyMs}ms
                </span>
              )}
            </Badge>
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs">
            🟢 Real-Time WebSocket stream connected.{' '}
            {latencyMs !== null ? `Round-trip latency: ${latencyMs}ms` : ''}
          </p>
        </TooltipContent>
      </Tooltip>
    );
  }

  if (status === 'CONNECTING' || status === 'RECONNECTING') {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={handleManualReconnect}
            className="cursor-pointer focus:outline-none"
          >
            <Badge variant="warning" size="sm" className="font-mono text-[11px] gap-1.5">
              <RefreshCw className="w-3 h-3 animate-spin text-amber-400" />
              <span>
                {status === 'RECONNECTING'
                  ? `RECONNECTING (${reconnectAttempts})`
                  : 'CONNECTING...'}
              </span>
            </Badge>
          </button>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs text-amber-300">
            🟡 Attempting to restore WebSocket stream. Click to reconnect immediately.
          </p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={handleManualReconnect}
          className="cursor-pointer focus:outline-none"
        >
          <Badge variant="loss" size="sm" className="font-mono text-[11px] gap-1.5">
            <WifiOff className="w-3 h-3 text-rose-400" />
            <span>{isPollingFallback ? 'OFFLINE (POLLING)' : 'OFFLINE'}</span>
          </Badge>
        </button>
      </TooltipTrigger>
      <TooltipContent>
        <p className="text-xs text-rose-300">
          {isPollingFallback
            ? '🔴 WebSocket disconnected. 10s REST polling fallback active. Click to retry stream.'
            : '🔴 Real-Time stream disconnected. Click to reconnect.'}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}
