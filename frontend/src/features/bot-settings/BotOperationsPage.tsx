import { useBotStatus } from '@/hooks/useBotOperations';
import { BotStatusHero } from './components/BotStatusHero';
import { BotControlButtons } from './components/BotControlButtons';
import { BotSettingsForm } from './components/BotSettingsForm';
import { CredentialVaultCard } from './components/CredentialVaultCard';

export function BotOperationsPage() {
  const { data: status, isLoading } = useBotStatus();

  return (
    <div className="space-y-4 font-mono">
      {/* 1. Bot Engine Runtime Status Hero */}
      <BotStatusHero status={status} isLoading={isLoading} />

      {/* 2. Operations Command & Emergency Controls */}
      <BotControlButtons status={status} />

      {/* 3. Settings & Credentials 2-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Left Column: Dynamic Settings Form (60%) */}
        <div className="lg:col-span-7 xl:col-span-7 space-y-4">
          <BotSettingsForm />
        </div>

        {/* Right Column: Binance Credential Vault (40%) */}
        <div className="lg:col-span-5 xl:col-span-5 space-y-4">
          <CredentialVaultCard />
        </div>
      </div>
    </div>
  );
}
