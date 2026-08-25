import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { simulateRiskApi } from '@/api/endpoints/calculator';
import {
  RiskSimulationRequestDTO,
  RiskSimulationResponseDTO,
} from '@/types/calculator';

export function validatePriceGeometry(
  side: 'BUY' | 'SELL',
  entryPrice: number,
  slPrice: number
): { isValid: boolean; error: string | null } {
  if (entryPrice <= 0 || slPrice <= 0) {
    return { isValid: false, error: 'Entry and Stop Loss prices must be greater than 0.' };
  }

  if (Math.abs(entryPrice - slPrice) < 0.00001) {
    return { isValid: false, error: 'Stop Loss distance cannot be zero (SL cannot equal Entry).' };
  }

  if (side === 'BUY' && slPrice >= entryPrice) {
    return {
      isValid: false,
      error: 'Invalid Geometry: Stop Loss must be BELOW Entry price for a BUY (Long) position.',
    };
  }

  if (side === 'SELL' && slPrice <= entryPrice) {
    return {
      isValid: false,
      error: 'Invalid Geometry: Stop Loss must be ABOVE Entry price for a SELL (Short) position.',
    };
  }

  return { isValid: true, error: null };
}

export function useRiskSimulation(payload: RiskSimulationRequestDTO, debounceMs = 300) {
  const [debouncedPayload, setDebouncedPayload] = useState<RiskSimulationRequestDTO>(payload);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedPayload(payload);
    }, debounceMs);

    return () => {
      clearTimeout(handler);
    };
  }, [payload, debounceMs]);

  const geometryValidation = validatePriceGeometry(
    debouncedPayload.side,
    debouncedPayload.entry_price,
    debouncedPayload.sl_price
  );

  const isEnabled =
    geometryValidation.isValid &&
    debouncedPayload.wallet_balance > 0 &&
    debouncedPayload.requested_leverage >= 1;

  const query = useQuery<RiskSimulationResponseDTO>({
    queryKey: [
      'calculator',
      'simulate',
      debouncedPayload.symbol,
      debouncedPayload.side,
      debouncedPayload.entry_price,
      debouncedPayload.sl_price,
      debouncedPayload.wallet_balance,
      debouncedPayload.requested_leverage,
      debouncedPayload.risk_percent,
    ],
    queryFn: () => simulateRiskApi(debouncedPayload),
    enabled: isEnabled,
    staleTime: 30000,
  });

  return {
    ...query,
    geometryValidation,
    isDebouncing: JSON.stringify(payload) !== JSON.stringify(debouncedPayload),
  };
}
