import { apiClient } from '@/api/client';
import { AnalyticsSummaryDTO, EquityPointDTO, TimeframeOption } from '@/types/analytics';

/**
 * Fetch portfolio executive analytics summary.
 */
export async function getAnalyticsSummaryApi(
  accountId: number = 1
): Promise<AnalyticsSummaryDTO> {
  const res = await apiClient.get<AnalyticsSummaryDTO>('/analytics/summary', {
    params: { account_id: accountId },
  });
  return res.data;
}

/**
 * Fetch historical equity growth curve points.
 */
export async function getEquityCurveApi(
  timeframe: TimeframeOption = '30d'
): Promise<EquityPointDTO[]> {
  const res = await apiClient.get<EquityPointDTO[]>('/analytics/equity-curve', {
    params: { timeframe },
  });
  return res.data;
}
