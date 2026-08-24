import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAnalyticsSummaryApi } from '@/api/endpoints/analytics';
import { useRiskSimulation } from '@/hooks/useRiskSimulation';
import { RiskSimulationRequestDTO } from '@/types/calculator';
import { RiskSimulatorForm } from './components/RiskSimulatorForm';
import { SimulationResultCard } from './components/SimulationResultCard';

interface RiskSimulatorSandboxProps {
  defaultBalance: number;
}

function RiskSimulatorSandbox({ defaultBalance }: RiskSimulatorSandboxProps) {
  const [formData, setFormData] = useState<RiskSimulationRequestDTO>({
    symbol: 'BTCUSDT',
    side: 'BUY',
    entry_price: 50000.0,
    sl_price: 49000.0,
    wallet_balance: defaultBalance > 0 ? defaultBalance : 1000.0,
    requested_leverage: 20,
    risk_percent: 2.0,
  });

  const {
    data: result,
    isLoading,
    isDebouncing,
    geometryValidation,
  } = useRiskSimulation(formData);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
      {/* Left Column: Interactive Simulation Form (50%) */}
      <div className="lg:col-span-6 xl:col-span-6 space-y-4">
        <RiskSimulatorForm formData={formData} onChange={setFormData} />
      </div>

      {/* Right Column: Simulation Results & Visualizer (50%) */}
      <div className="lg:col-span-6 xl:col-span-6 space-y-4">
        <SimulationResultCard
          result={result}
          isLoading={isLoading}
          isDebouncing={isDebouncing}
          geometryError={geometryValidation.error}
          requestedLeverage={formData.requested_leverage}
        />
      </div>
    </div>
  );
}

export function RiskSimulatorPage() {
  const { data: summary } = useQuery({
    queryKey: ['analytics', 'summary', 1],
    queryFn: () => getAnalyticsSummaryApi(1),
    staleTime: 30000,
  });

  const initialBalance = summary?.total_balance_usdt || 1000.0;

  return (
    <div className="space-y-4 font-mono">
      <RiskSimulatorSandbox
        key={summary?.total_balance_usdt ? `balance-${summary.total_balance_usdt}` : 'default-balance'}
        defaultBalance={initialBalance}
      />
    </div>
  );
}
