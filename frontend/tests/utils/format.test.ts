import { describe, it, expect } from 'vitest';
import {
  safeNumber,
  formatUSDT,
  formatCrypto,
  formatPercent,
  formatDateTime,
  formatDuration,
} from '@/utils/format';

describe('Financial Formatting Utilities (format.ts)', () => {
  describe('safeNumber', () => {
    it('parses numbers and numeric strings accurately', () => {
      expect(safeNumber(123.45)).toBe(123.45);
      expect(safeNumber('123.45')).toBe(123.45);
      expect(safeNumber('0')).toBe(0);
      expect(safeNumber(0)).toBe(0);
    });

    it('handles null, undefined, and NaN with fallback', () => {
      expect(safeNumber(null)).toBe(0);
      expect(safeNumber(undefined)).toBe(0);
      expect(safeNumber('invalid_string', 10)).toBe(10);
      expect(safeNumber(NaN, 5)).toBe(5);
    });
  });

  describe('formatUSDT', () => {
    it('formats positive and zero numbers as USD currency strings', () => {
      expect(formatUSDT(10450.5)).toBe('$10,450.50');
      expect(formatUSDT(0)).toBe('$0.00');
      expect(formatUSDT(50000, 0)).toBe('$50,000');
    });

    it('formats negative numbers properly', () => {
      expect(formatUSDT(-45.5)).toBe('-$45.50');
    });

    it('handles null and undefined gracefully', () => {
      expect(formatUSDT(null)).toBe('$0.00');
      expect(formatUSDT(undefined)).toBe('$0.00');
    });
  });

  describe('formatCrypto', () => {
    it('formats coin sizes with symbol and precision', () => {
      expect(formatCrypto(0.0456, 4, 'BTC')).toBe('0.0456 BTC');
      expect(formatCrypto(12.5, 2, 'ETH')).toBe('12.5 ETH');
      expect(formatCrypto(100)).toBe('100');
    });

    it('handles null and undefined', () => {
      expect(formatCrypto(null, 4, 'BTC')).toBe('0 BTC');
      expect(formatCrypto(undefined)).toBe('0');
    });
  });

  describe('formatPercent', () => {
    it('formats percentage with positive and negative signs', () => {
      expect(formatPercent(2.45, true)).toBe('+2.45%');
      expect(formatPercent(-1.2, true)).toBe('-1.20%');
      expect(formatPercent(0, true)).toBe('0.00%');
      expect(formatPercent(72.5, false)).toBe('72.50%');
    });

    it('handles null and undefined', () => {
      expect(formatPercent(null)).toBe('0.00%');
      expect(formatPercent(undefined)).toBe('0.00%');
    });
  });

  describe('formatDateTime', () => {
    it('formats ISO 8601 strings to readable date time', () => {
      const formatted = formatDateTime('2026-08-24T14:30:15Z');
      expect(formatted).toMatch(/^2026-08-24 \d{2}:30:15$/);
    });

    it('handles invalid dates and non-strings', () => {
      expect(formatDateTime('not-a-date')).toBe('-');
      expect(formatDateTime(null)).toBe('-');
      expect(formatDateTime(undefined)).toBe('-');
    });
  });

  describe('formatDuration', () => {
    it('converts seconds to human-readable duration strings', () => {
      expect(formatDuration(45)).toBe('45s');
      expect(formatDuration(125)).toBe('2m 5s');
      expect(formatDuration(8130)).toBe('2h 15m 30s');
      expect(formatDuration(0)).toBe('0s');
      expect(formatDuration(-10)).toBe('0s');
    });
  });
});
