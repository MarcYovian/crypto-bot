import { InstrumentDTO } from '@/types/watchlist';
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
  ModalFooter,
  ModalClose,
} from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatUSDT, formatPercent } from '@/utils/format';
import { Layers, Shield } from 'lucide-react';

export interface InstrumentBracketModalProps {
  instrument: InstrumentDTO | null;
  isOpen: boolean;
  onClose: () => void;
}

export function InstrumentBracketModal({
  instrument,
  isOpen,
  onClose,
}: InstrumentBracketModalProps) {
  if (!instrument) return null;

  const brackets = instrument.brackets || [];

  return (
    <Modal open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <ModalContent className="max-w-2xl max-h-[90vh] overflow-y-auto custom-scrollbar font-mono text-xs">
        <ModalHeader className="border-b border-border/50 pb-3 pr-8">
          <div className="flex flex-wrap items-center gap-2.5">
            <ModalTitle className="flex items-center gap-2 text-base text-white">
              <Layers className="w-4 h-4 text-brand-400" />
              {instrument.symbol} Specifications & Leverage Tiers
            </ModalTitle>
            <Badge variant="outline" size="sm" className="font-bold text-slate-200">
              Max: {instrument.max_leverage}x
            </Badge>
          </div>
          <ModalDescription className="text-xs text-slate-400">
            Binance Futures exchange rules, tick precision, and margin requirements
          </ModalDescription>
        </ModalHeader>

        <div className="py-4 space-y-4">
          {/* Contract Specifications Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3 rounded-lg bg-surface/60 border border-border/60">
            <div>
              <span className="text-slate-500 block text-[10px]">Base / Quote:</span>
              <span className="text-white font-bold">
                {instrument.base_asset} / {instrument.quote_asset}
              </span>
            </div>

            <div>
              <span className="text-slate-500 block text-[10px]">Price Precision:</span>
              <span className="text-slate-200 font-semibold">
                {instrument.price_precision} Decimals ({instrument.tick_size})
              </span>
            </div>

            <div>
              <span className="text-slate-500 block text-[10px]">Qty Precision:</span>
              <span className="text-slate-200 font-semibold">
                {instrument.qty_precision} Decimals ({instrument.step_size})
              </span>
            </div>

            <div>
              <span className="text-slate-500 block text-[10px]">Min Notional:</span>
              <span className="text-emerald-400 font-bold">
                {formatUSDT(instrument.min_notional)}
              </span>
            </div>
          </div>

          {/* Leverage Tier Brackets Table */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-slate-300 flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-brand-400" />
                Binance Leverage Brackets (MMR Scaling)
              </span>
              <span className="text-[10px] text-slate-500">
                {brackets.length} Tiers Configured
              </span>
            </div>

            {brackets.length === 0 ? (
              <div className="p-6 rounded-lg bg-surface/30 border border-dashed border-border/60 text-center text-xs text-slate-500">
                No custom leverage brackets found. Using standard default 125x tier 1 limits.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border/40">
                <table className="w-full text-left border-collapse text-[11px]">
                  <thead>
                    <tr className="border-b border-border/60 bg-surface/70 font-semibold text-slate-400 uppercase tracking-wider select-none">
                      <th className="p-2.5">Tier</th>
                      <th className="p-2.5">Max Leverage</th>
                      <th className="p-2.5">Notional Floor</th>
                      <th className="p-2.5">Notional Cap</th>
                      <th className="p-2.5 text-right">Maint. Margin (MMR)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30 bg-surface/20">
                    {brackets.map((br) => (
                      <tr key={br.bracket} className="hover:bg-surface/50 transition-colors">
                        <td className="p-2.5 font-bold text-brand-400">
                          Tier #{br.bracket}
                        </td>
                        <td className="p-2.5 text-white font-semibold">
                          {br.initial_leverage}x
                        </td>
                        <td className="p-2.5 text-slate-400">
                          {formatUSDT(br.notional_floor ?? 0)}
                        </td>
                        <td className="p-2.5 text-slate-200 font-medium">
                          {formatUSDT(br.notional_cap)}
                        </td>
                        <td className="p-2.5 text-right font-bold text-rose-300">
                          {formatPercent(br.maint_margin_ratio * 100, false, 2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <ModalFooter className="border-t border-border/50 pt-3">
          <ModalClose asChild>
            <Button variant="secondary" size="sm">
              Close Specifications
            </Button>
          </ModalClose>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
