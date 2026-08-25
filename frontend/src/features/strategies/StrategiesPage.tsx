import { useState } from 'react';
import { StrategyConfigPanel } from './components/StrategyConfigPanel';
import { SignalProvidersPanel } from './components/SignalProvidersPanel';
import { Sliders, Radio } from 'lucide-react';
import { cn } from '@/utils/cn';

export type StrategiesTab = 'rules' | 'providers';

export function StrategiesPage() {
  const [activeTab, setActiveTab] = useState<StrategiesTab>('rules');

  return (
    <div className="space-y-4 font-mono">
      {/* Tab Navigation Pill Bar */}
      <div className="flex items-center gap-1.5 p-1 bg-surface/60 rounded-xl border border-border/60 w-fit text-xs">
        <button
          onClick={() => setActiveTab('rules')}
          className={cn(
            'flex items-center gap-2 px-3.5 py-2 rounded-lg font-medium transition-all duration-150',
            activeTab === 'rules'
              ? 'bg-brand-500 text-white shadow-glow-brand font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          )}
        >
          <Sliders className="w-3.5 h-3.5" />
          Take Profit & Trailing Rules
        </button>

        <button
          onClick={() => setActiveTab('providers')}
          className={cn(
            'flex items-center gap-2 px-3.5 py-2 rounded-lg font-medium transition-all duration-150',
            activeTab === 'providers'
              ? 'bg-brand-500 text-white shadow-glow-brand font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          )}
        >
          <Radio className="w-3.5 h-3.5" />
          Telegram Signal Providers
        </button>
      </div>

      {/* Tab Contents */}
      {activeTab === 'rules' ? (
        <StrategyConfigPanel />
      ) : (
        <SignalProvidersPanel />
      )}
    </div>
  );
}
