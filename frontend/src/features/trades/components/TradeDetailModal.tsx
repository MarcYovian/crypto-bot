import { useTradeDetail } from '@/hooks/useTradeHistory';
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
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { OverviewTab } from './tabs/OverviewTab';
import { RiskParametersTab } from './tabs/RiskParametersTab';
import { OrderLifecycleTab } from './tabs/OrderLifecycleTab';
import { ExecutionsTab } from './tabs/ExecutionsTab';
import { FinancialSummaryTab } from './tabs/FinancialSummaryTab';
import { FileText, AlertCircle } from 'lucide-react';

export interface TradeDetailModalProps {
  tradeId: number | null;
  isOpen: boolean;
  onClose: () => void;
}

export function TradeDetailModal({
  tradeId,
  isOpen,
  onClose,
}: TradeDetailModalProps) {
  const { data: trade, isLoading, isError } = useTradeDetail(tradeId);

  return (
    <Modal open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <ModalContent className="max-w-3xl">
        <ModalHeader className="border-b border-border/50 pb-3 pr-8">
          <ModalTitle className="flex items-center gap-2 text-base text-white">
            <FileText className="w-4 h-4 text-brand-400" />
            Trade Deep Drilldown #{tradeId}
          </ModalTitle>
          <ModalDescription className="text-xs text-slate-400">
            5-Level institutional audit trail: Overview, Risk, Orders, Executions, and Financial Summary
          </ModalDescription>
        </ModalHeader>

        <div className="py-3">
          {isLoading ? (
            <div className="space-y-4 py-4">
              <div className="flex gap-2">
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-8 w-24" />
              </div>
              <Skeleton className="h-28 w-full rounded-lg" />
              <Skeleton className="h-20 w-full rounded-lg" />
            </div>
          ) : isError || !trade ? (
            <div className="py-8 text-center space-y-3">
              <div className="w-10 h-10 rounded-full bg-rose-500/20 text-rose-400 mx-auto flex items-center justify-center">
                <AlertCircle className="w-5 h-5" />
              </div>
              <p className="text-xs text-slate-400">
                Failed to load trade detail for ID #{tradeId}.
              </p>
            </div>
          ) : (
            <Tabs defaultValue="overview" className="w-full">
              <TabsList className="w-full grid grid-cols-2 sm:grid-cols-5 h-auto p-1 gap-1">
                <TabsTrigger value="overview" className="text-[11px] py-1.5 font-mono">
                  1. Overview
                </TabsTrigger>
                <TabsTrigger value="risk" className="text-[11px] py-1.5 font-mono">
                  2. Risk
                </TabsTrigger>
                <TabsTrigger value="orders" className="text-[11px] py-1.5 font-mono">
                  3. Orders ({trade.orders?.length || 0})
                </TabsTrigger>
                <TabsTrigger value="executions" className="text-[11px] py-1.5 font-mono">
                  4. Fills ({trade.executions?.length || 0})
                </TabsTrigger>
                <TabsTrigger value="summary" className="text-[11px] py-1.5 font-mono">
                  5. Financials
                </TabsTrigger>
              </TabsList>

              <div className="mt-4">
                <TabsContent value="overview">
                  <OverviewTab trade={trade} />
                </TabsContent>

                <TabsContent value="risk">
                  <RiskParametersTab trade={trade} />
                </TabsContent>

                <TabsContent value="orders">
                  <OrderLifecycleTab trade={trade} />
                </TabsContent>

                <TabsContent value="executions">
                  <ExecutionsTab trade={trade} />
                </TabsContent>

                <TabsContent value="summary">
                  <FinancialSummaryTab trade={trade} />
                </TabsContent>
              </div>
            </Tabs>
          )}
        </div>

        <ModalFooter className="border-t border-border/50 pt-3">
          <ModalClose asChild>
            <Button variant="secondary" size="sm">
              Close Detail
            </Button>
          </ModalClose>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
