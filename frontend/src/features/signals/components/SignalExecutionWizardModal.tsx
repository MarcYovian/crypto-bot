import React, { useState } from 'react';
import { SignalItemDTO, ManualSignalExecutionRequestDTO } from '@/types/signals';
import { useManualExecuteSignal } from '@/hooks/useSignals';
import { RiskCapIndicator } from './RiskCapIndicator';
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
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { formatCrypto } from '@/utils/format';
import { Zap, AlertCircle, CheckCircle2 } from 'lucide-react';

interface WizardFormProps {
  signal: SignalItemDTO;
  onClose: () => void;
  accountBalance: number;
}

function SignalExecutionWizardForm({
  signal,
  onClose,
  accountBalance,
}: WizardFormProps) {
  const [entryPrice, setEntryPrice] = useState<string>(
    signal.entry_price ? String(signal.entry_price) : ''
  );
  const [slPrice, setSlPrice] = useState<string>(
    signal.sl_price ? String(signal.sl_price) : ''
  );
  const [tp1Price, setTp1Price] = useState<string>(
    signal.tp_targets?.[0] ? String(signal.tp_targets[0]) : ''
  );
  const [tp2Price, setTp2Price] = useState<string>(
    signal.tp_targets?.[1] ? String(signal.tp_targets[1]) : ''
  );
  const [tp3Price, setTp3Price] = useState<string>(
    signal.tp_targets?.[2] ? String(signal.tp_targets[2]) : ''
  );
  const [leverage] = useState<number>(20);
  const [autoTpSl, setAutoTpSl] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const executeMutation = useManualExecuteSignal();

  const isBuy = signal.side === 'BUY';
  const numEntry = parseFloat(entryPrice) || 0;
  const numSL = parseFloat(slPrice) || 0;
  const numTP1 = parseFloat(tp1Price) || 0;
  const numTP2 = parseFloat(tp2Price) || 0;
  const numTP3 = parseFloat(tp3Price) || 0;

  // Max 2.0% Risk Cap calculations
  const maxRiskBudget = accountBalance * 0.02; // $200 on $10k
  const stopDistance = Math.abs(numEntry - numSL);
  const calculatedLotSize =
    stopDistance > 0 ? maxRiskBudget / stopDistance : 0;
  const calculatedRiskAmount = calculatedLotSize * stopDistance;
  const isRiskSafe =
    calculatedRiskAmount <= maxRiskBudget * 1.01 &&
    accountBalance > 0 &&
    calculatedRiskAmount / accountBalance <= 0.0201;

  // Local Price Geometry Validation
  let geometryError: string | null = null;
  if (numEntry <= 0) {
    geometryError = 'Entry price must be greater than 0.';
  } else if (numSL <= 0) {
    geometryError = 'Stop loss price must be greater than 0.';
  } else if (isBuy) {
    if (numSL >= numEntry) {
      geometryError = 'For BUY position, Stop Loss must be strictly below Entry price.';
    } else if (numTP1 > 0 && numTP1 <= numEntry) {
      geometryError = 'For BUY position, TP1 must be strictly above Entry price.';
    } else if (numTP2 > 0 && numTP2 <= numTP1) {
      geometryError = 'For BUY position, TP2 must be strictly above TP1.';
    } else if (numTP3 > 0 && numTP3 <= numTP2) {
      geometryError = 'For BUY position, TP3 must be strictly above TP2.';
    }
  } else {
    // SELL
    if (numSL <= numEntry) {
      geometryError = 'For SELL position, Stop Loss must be strictly above Entry price.';
    } else if (numTP1 > 0 && numTP1 >= numEntry) {
      geometryError = 'For SELL position, TP1 must be strictly below Entry price.';
    } else if (numTP2 > 0 && numTP2 >= numTP1) {
      geometryError = 'For SELL position, TP2 must be strictly below TP1.';
    } else if (numTP3 > 0 && numTP3 >= numTP2) {
      geometryError = 'For SELL position, TP3 must be strictly below TP2.';
    }
  }

  const isFormValid = !geometryError && isRiskSafe && numEntry > 0 && numSL > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid) return;

    setError(null);
    setSuccessMessage(null);

    const tpTargets: number[] = [numTP1, numTP2, numTP3].filter((tp) => tp > 0);

    const payload: ManualSignalExecutionRequestDTO = {
      symbol: signal.symbol,
      side: signal.side,
      entry_price: numEntry,
      sl_price: numSL,
      tp_targets: tpTargets.length > 0 ? tpTargets : [numEntry * (isBuy ? 1.02 : 0.98)],
      leverage,
      auto_tp_sl: autoTpSl,
    };

    try {
      const result = await executeMutation.mutateAsync({ payload });
      if (result.is_success) {
        setSuccessMessage(
          `Order executed successfully! Trade ID: #${result.trade_id} (Entry Order: ${result.entry_order_id || 'OK'})`
        );
        setTimeout(() => {
          onClose();
        }, 1200);
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to execute signal. Please check parameters and try again.');
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 py-3 text-xs font-mono">
      {/* Status / Error Alerts */}
      {error && (
        <div
          role="alert"
          className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 text-xs text-rose-300 flex items-start gap-2"
        >
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {successMessage && (
        <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-xs text-emerald-300 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {geometryError && (
        <div
          role="alert"
          className="p-2.5 rounded-lg bg-amber-950/30 border border-amber-800/50 text-[11px] text-amber-300 flex items-start gap-2"
        >
          <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
          <span>{geometryError}</span>
        </div>
      )}

      {/* Symbol Header Summary */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-surface/60 border border-border/60">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-white tracking-wide">
            {signal.symbol}
          </span>
          <Badge variant={isBuy ? 'profit' : 'loss'} size="sm">
            {signal.side}
          </Badge>
          <Badge variant="outline" size="sm" className="text-[10px]">
            Lev: {leverage}x
          </Badge>
        </div>
        <div className="text-[11px] text-slate-400">
          Auto Lot: <strong className="text-white">{formatCrypto(calculatedLotSize, 4)}</strong>
        </div>
      </div>

      {/* Inputs Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-[11px] text-slate-400 block mb-1">
            Entry Price (USDT)
          </label>
          <Input
            type="number"
            step="any"
            value={entryPrice}
            onChange={(e) => setEntryPrice(e.target.value)}
            className="h-8 text-xs bg-surface/60 border-border/80 font-mono"
            required
          />
        </div>

        <div>
          <label className="text-[11px] text-slate-400 block mb-1">
            Stop Loss (USDT)
          </label>
          <Input
            type="number"
            step="any"
            value={slPrice}
            onChange={(e) => setSlPrice(e.target.value)}
            className="h-8 text-xs bg-surface/60 border-border/80 font-mono text-rose-300"
            required
          />
        </div>
      </div>

      {/* TP Targets */}
      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="text-[10px] text-slate-400 block mb-1">
            TP1 (50%)
          </label>
          <Input
            type="number"
            step="any"
            value={tp1Price}
            onChange={(e) => setTp1Price(e.target.value)}
            className="h-7 text-xs bg-surface/60 border-border/80 font-mono text-emerald-400"
          />
        </div>
        <div>
          <label className="text-[10px] text-slate-400 block mb-1">
            TP2 (30%)
          </label>
          <Input
            type="number"
            step="any"
            value={tp2Price}
            onChange={(e) => setTp2Price(e.target.value)}
            className="h-7 text-xs bg-surface/60 border-border/80 font-mono text-emerald-400"
          />
        </div>
        <div>
          <label className="text-[10px] text-slate-400 block mb-1">
            TP3 (20%)
          </label>
          <Input
            type="number"
            step="any"
            value={tp3Price}
            onChange={(e) => setTp3Price(e.target.value)}
            className="h-7 text-xs bg-surface/60 border-border/80 font-mono text-emerald-400"
          />
        </div>
      </div>

      {/* Hard 2.0% Risk Cap Indicator */}
      <RiskCapIndicator
        riskAmount={calculatedRiskAmount}
        maxRiskBudget={maxRiskBudget}
        totalBalance={accountBalance}
      />

      {/* Switches */}
      <div className="flex items-center justify-between pt-1 text-[11px] text-slate-300">
        <span>Auto Attach TP/SL Bracket Orders</span>
        <Switch checked={autoTpSl} onCheckedChange={setAutoTpSl} />
      </div>

      <ModalFooter className="border-t border-border/50 pt-3">
        <ModalClose asChild>
          <Button
            variant="secondary"
            size="sm"
            type="button"
            disabled={executeMutation.isPending}
          >
            Cancel
          </Button>
        </ModalClose>
        <Button
          variant="primary"
          size="sm"
          type="submit"
          disabled={!isFormValid || executeMutation.isPending}
          isLoading={executeMutation.isPending}
          className="gap-1.5 shadow-glow-brand"
        >
          {!executeMutation.isPending && <Zap className="w-3.5 h-3.5" />}
          Confirm & Execute Order
        </Button>
      </ModalFooter>
    </form>
  );
}

export interface SignalExecutionWizardModalProps {
  signal: SignalItemDTO | null;
  isOpen: boolean;
  onClose: () => void;
  accountBalance?: number;
}

export function SignalExecutionWizardModal({
  signal,
  isOpen,
  onClose,
  accountBalance = 10000.0,
}: SignalExecutionWizardModalProps) {
  if (!signal) return null;

  return (
    <Modal open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <ModalContent className="max-w-xl max-h-[90vh] overflow-y-auto custom-scrollbar">
        <ModalHeader className="border-b border-border/50 pb-3 pr-8">
          <ModalTitle className="flex items-center gap-2 text-base text-white">
            <Zap className="w-4 h-4 text-brand-400" />
            1-Click Signal Execution Wizard
          </ModalTitle>
          <ModalDescription className="text-xs text-slate-400">
            Institutional pre-execution risk check & automatic lot sizing
          </ModalDescription>
        </ModalHeader>

        <SignalExecutionWizardForm
          key={signal.id}
          signal={signal}
          onClose={onClose}
          accountBalance={accountBalance}
        />
      </ModalContent>
    </Modal>
  );
}
