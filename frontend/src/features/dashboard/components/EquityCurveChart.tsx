import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
} from 'lightweight-charts';
import { EquityPointDTO, TimeframeOption } from '@/types/analytics';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { formatUSDT, formatDateTime } from '@/utils/format';
import { Activity, Calendar } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface EquityCurveChartProps {
  points?: EquityPointDTO[];
  timeframe: TimeframeOption;
  onTimeframeChange: (tf: TimeframeOption) => void;
  isLoading?: boolean;
}

const TIMEFRAMES: { label: string; value: TimeframeOption }[] = [
  { label: '7D', value: '7d' },
  { label: '30D', value: '30d' },
  { label: '90D', value: '90d' },
  { label: 'ALL', value: 'all' },
];

export function EquityCurveChart({
  points = [],
  timeframe,
  onTimeframeChange,
  isLoading = false,
}: EquityCurveChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const pointsRef = useRef<EquityPointDTO[]>(points);

  useEffect(() => {
    pointsRef.current = points;
  }, [points]);

  const [hoveredPoint, setHoveredPoint] = useState<{
    time: string;
    balance: number;
    pnl: number;
  } | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // 1. Initialize Lightweight Chart instance
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94A3B8',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: 'rgba(51, 65, 85, 0.2)' },
        horzLines: { color: 'rgba(51, 65, 85, 0.2)' },
      },
      crosshair: {
        vertLine: {
          color: 'rgba(56, 189, 248, 0.5)',
          width: 1,
          style: 3, // dashed
          labelBackgroundColor: '#0F172A',
        },
        horzLine: {
          color: 'rgba(56, 189, 248, 0.5)',
          width: 1,
          style: 3,
          labelBackgroundColor: '#0F172A',
        },
      },
      rightPriceScale: {
        borderColor: 'rgba(51, 65, 85, 0.4)',
        scaleMargins: {
          top: 0.15,
          bottom: 0.15,
        },
      },
      timeScale: {
        borderColor: 'rgba(51, 65, 85, 0.4)',
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: {
        vertTouchDrag: false,
      },
    });

    // 2. Add Area Series with Cyan Neon Gradient
    const areaSeries = chart.addAreaSeries({
      lineColor: '#38BDF8',
      topColor: 'rgba(56, 189, 248, 0.35)',
      bottomColor: 'rgba(56, 189, 248, 0.01)',
      lineWidth: 2,
      priceFormat: {
        type: 'custom',
        formatter: (price: number) => `$${price.toFixed(2)}`,
      },
    });

    chartRef.current = chart;
    seriesRef.current = areaSeries;

    // 3. Subscribe to Crosshair Hover
    chart.subscribeCrosshairMove((param) => {
      if (
        !param.point ||
        !param.time ||
        param.point.x < 0 ||
        param.point.y < 0
      ) {
        setHoveredPoint(null);
        return;
      }

      const price = param.seriesData.get(areaSeries) as
        | { value?: number }
        | undefined;

      if (price && typeof price.value === 'number') {
        const timeStr = typeof param.time === 'string'
          ? param.time
          : new Date((param.time as number) * 1000).toISOString();

        // Find matching point for PnL delta using ref
        const found = pointsRef.current.find((p) => {
          const ptTime = Math.floor(new Date(p.timestamp).getTime() / 1000);
          return ptTime === param.time;
        });

        setHoveredPoint({
          time: timeStr,
          balance: price.value,
          pnl: found ? found.pnl : 0,
        });
      }
    });

    // 4. ResizeObserver for Auto-Responsive Canvas
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !entries[0].contentRect) return;
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    });

    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // 5. Update chart data when points change
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return;

    if (points && points.length > 0) {
      // Sort and map to Lightweight Chart time/value format
      const formattedData = [...points]
        .sort(
          (a, b) =>
            new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
        )
        .map((pt) => ({
          time: Math.floor(
            new Date(pt.timestamp).getTime() / 1000
          ) as UTCTimestamp,
          value: pt.balance,
        }));

      // Filter out duplicate timestamps (Lightweight Charts requires strictly ascending time)
      const uniqueData = formattedData.filter(
        (item, index, self) =>
          index === 0 || item.time > self[index - 1].time
      );

      seriesRef.current.setData(uniqueData);
      chartRef.current.timeScale().fitContent();
    } else {
      seriesRef.current.setData([]);
    }
  }, [points]);

  const latestPoint = points[points.length - 1];
  const displayBalance = hoveredPoint?.balance ?? latestPoint?.balance ?? 0;
  const displayPnL = hoveredPoint?.pnl ?? latestPoint?.pnl ?? 0;
  const displayTime = hoveredPoint?.time ?? latestPoint?.timestamp;

  return (
    <Card className="glass-card w-full">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-brand-400" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              Portfolio Equity Curve
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Historical portfolio balance and closed performance curve
          </CardDescription>
        </div>

        {/* Timeframe Selector Pills */}
        <div className="flex items-center gap-1.5 bg-surface/80 p-1 rounded-lg border border-border/80">
          <Calendar className="w-3.5 h-3.5 text-slate-400 ml-1.5 mr-0.5 hidden sm:block" />
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => onTimeframeChange(tf.value)}
              className={cn(
                'px-2.5 py-1 text-xs font-mono rounded-md font-medium transition-all duration-150',
                timeframe === tf.value
                  ? 'bg-brand-500 text-white shadow-glow-brand'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              )}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {/* Dynamic Metric Hover Header */}
        <div className="flex flex-wrap items-center justify-between gap-4 px-2 py-1.5 rounded-lg bg-surface/40 border border-border/40 text-xs">
          <div className="flex items-center gap-3 font-mono">
            <span className="text-slate-400">Equity:</span>
            <span className="text-base font-bold text-white">
              {formatUSDT(displayBalance)}
            </span>
            <span
              className={cn(
                'text-xs font-medium',
                displayPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'
              )}
            >
              {displayPnL >= 0 ? '+' : ''}
              {formatUSDT(displayPnL)} PnL
            </span>
          </div>

          {displayTime && (
            <div className="text-slate-400 font-mono text-[11px]">
              {formatDateTime(displayTime)}
            </div>
          )}
        </div>

        {/* Chart Canvas Area */}
        <div className="relative w-full h-[320px] rounded-lg overflow-hidden">
          {isLoading && (
            <div className="absolute inset-0 bg-surface/60 backdrop-blur-xs flex items-center justify-center z-10">
              <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping" />
                Loading equity points...
              </div>
            </div>
          )}

          {points.length === 0 && !isLoading ? (
            <div className="w-full h-full flex flex-col items-center justify-center text-slate-500 space-y-2 border border-dashed border-border/50 rounded-lg">
              <Activity className="w-8 h-8 text-slate-600" />
              <p className="text-xs font-mono">
                No equity curve data available for timeframe ({timeframe.toUpperCase()})
              </p>
            </div>
          ) : (
            <div
              ref={chartContainerRef}
              className="w-full h-full"
              data-testid="equity-chart-container"
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
