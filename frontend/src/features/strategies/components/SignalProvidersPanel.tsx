import { useState } from 'react';
import { useProviders } from '@/hooks/useProviders';
import { AddProviderModal } from './AddProviderModal';
import { ProviderAnalyticsModal } from './ProviderAnalyticsModal';
import { SignalProviderDTO } from '@/types/providers';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { Radio, Plus, BarChart2, ShieldCheck, Hash } from 'lucide-react';

export function SignalProvidersPanel() {
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<SignalProviderDTO | null>(null);
  const [isAnalyticsOpen, setIsAnalyticsOpen] = useState(false);

  const { data: providers = [], isLoading } = useProviders();

  const handleOpenAnalytics = (provider: SignalProviderDTO) => {
    setSelectedProvider(provider);
    setIsAnalyticsOpen(true);
  };

  return (
    <Card className="glass-card w-full">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-brand-400" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              Telegram Signal Providers & Channels
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Configure Telegram signal sources, channel mappings, and AI confidence weighting multipliers
          </CardDescription>
        </div>

        <RoleGuard requiredRole="ADMIN" mode="disable">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsAddModalOpen(true)}
            className="gap-1.5 text-xs border-brand-500/40 text-brand-400 hover:text-white hover:bg-brand-500/20"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Channel
          </Button>
        </RoleGuard>
      </CardHeader>

      <CardContent className="pt-4">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-36 rounded-lg bg-surface/40 border border-border/40 animate-pulse"
              />
            ))}
          </div>
        ) : providers.length === 0 ? (
          <div className="p-8 text-center rounded-lg bg-surface/30 border border-dashed border-border/50 text-slate-500 text-xs font-mono">
            No signal provider channels configured. Click "Add Channel" to connect a Telegram source.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 font-mono text-xs">
            {providers.map((prov) => (
              <div
                key={prov.id}
                className="p-4 rounded-xl bg-surface/50 border border-border/60 hover:border-slate-600/80 transition-all space-y-3 flex flex-col justify-between"
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-1">
                    <h4 className="font-bold text-white text-sm tracking-tight flex items-center gap-1.5">
                      <Radio className="w-3.5 h-3.5 text-sky-400 shrink-0" />
                      {prov.name}
                    </h4>
                    <div className="flex items-center gap-1 text-[11px] text-slate-400">
                      <Hash className="w-3 h-3 text-slate-500" />
                      <span>{prov.channel_id || 'Webhook / Custom'}</span>
                    </div>
                  </div>

                  <Badge
                    variant={prov.is_active ? 'profit' : 'neutral'}
                    size="sm"
                    className="text-[10px] shrink-0"
                  >
                    {prov.is_active ? 'ACTIVE' : 'INACTIVE'}
                  </Badge>
                </div>

                {/* Body Meta */}
                <div className="flex items-center justify-between p-2 rounded-lg bg-surface/80 border border-border/50 text-[11px]">
                  <span className="text-slate-400 flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-brand-400" />
                    Weight Multiplier
                  </span>
                  <span className="font-bold text-brand-400">
                    {prov.confidence_weight.toFixed(2)}x
                  </span>
                </div>

                {/* Footer Action */}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleOpenAnalytics(prov)}
                  className="w-full gap-1.5 text-xs text-slate-300 hover:text-white"
                >
                  <BarChart2 className="w-3.5 h-3.5 text-brand-400" />
                  View Analytics & Win Rate
                </Button>
              </div>
            ))}
          </div>
        )}

        {/* Add Provider Modal */}
        <AddProviderModal
          isOpen={isAddModalOpen}
          onClose={() => setIsAddModalOpen(false)}
        />

        {/* Provider Performance Modal */}
        <ProviderAnalyticsModal
          providerId={selectedProvider?.id ?? null}
          providerName={selectedProvider?.name}
          isOpen={isAnalyticsOpen}
          onClose={() => {
            setIsAnalyticsOpen(false);
            setSelectedProvider(null);
          }}
        />
      </CardContent>
    </Card>
  );
}
