/**
 * Precision numerical and financial formatting utilities.
 * Avoids JavaScript floating-point distortions and handles edge cases (null, undefined, NaN, zero-division).
 */

/**
 * Safely parse a value (number, string, null, undefined) to a valid finite number.
 */
export function safeNumber(val: unknown, fallback = 0): number {
  if (val === null || val === undefined || val === '') {
    return fallback;
  }
  const parsed = typeof val === 'number' ? val : Number(val);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Format numeric value as USDT currency string with thousand separators.
 * Example: 10450.5 -> "$10,450.50"
 */
export function formatUSDT(val: unknown, decimals = 2): string {
  if (val === null || val === undefined) {
    return '$0.00';
  }
  const num = safeNumber(val, 0);
  const isNegative = num < 0;
  const absFormatted = Math.abs(num).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return isNegative ? `-$${absFormatted}` : `$${absFormatted}`;
}

/**
 * Format crypto coin quantity with custom precision and optional symbol.
 * Example: (0.02456, 4, "BTC") -> "0.0246 BTC"
 */
export function formatCrypto(val: unknown, precision = 4, symbol?: string): string {
  if (val === null || val === undefined) {
    return symbol ? `0 ${symbol}` : '0';
  }
  const num = safeNumber(val, 0);
  const formatted = num.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: precision,
  });
  return symbol ? `${formatted} ${symbol}` : formatted;
}

/**
 * Format numeric value as a percentage with optional positive sign prefix (+).
 * Example: 2.45 -> "+2.45%", -1.2 -> "-1.20%"
 */
export function formatPercent(val: unknown, includeSign = true, decimals = 2): string {
  if (val === null || val === undefined) {
    return '0.00%';
  }
  const num = safeNumber(val, 0);
  const formatted = Math.abs(num).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  if (num > 0 && includeSign) {
    return `+${formatted}%`;
  }
  if (num < 0) {
    return `-${formatted}%`;
  }
  return `${formatted}%`;
}

/**
 * Format an ISO date-time string into a clean, human-readable format.
 * Example: "2026-08-24T14:30:15Z" -> "2026-08-24 14:30:15"
 */
export function formatDateTime(isoString: unknown): string {
  if (!isoString || typeof isoString !== 'string') {
    return '-';
  }
  try {
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) {
      return '-';
    }
    const pad = (n: number) => n.toString().padStart(2, '0');
    const year = d.getFullYear();
    const month = pad(d.getMonth() + 1);
    const day = pad(d.getDate());
    const hours = pad(d.getHours());
    const minutes = pad(d.getMinutes());
    const seconds = pad(d.getSeconds());
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  } catch {
    return '-';
  }
}

/**
 * Format duration in seconds to compact human-readable string.
 * Example: 8130 -> "2h 15m 30s"
 */
export function formatDuration(seconds: unknown): string {
  const sec = Math.floor(safeNumber(seconds, 0));
  if (sec <= 0) {
    return '0s';
  }

  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;

  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  if (s > 0 || parts.length === 0) parts.push(`${s}s`);

  return parts.join(' ');
}
