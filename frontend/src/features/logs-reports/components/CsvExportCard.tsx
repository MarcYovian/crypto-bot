import { useState } from 'react';
import { useExportCsvMutation } from '@/hooks/useLogsAndReports';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  FileSpreadsheet,
  Download,
  Calendar,
  AlertCircle,
  CheckCircle2,
  Table,
} from 'lucide-react';

export function CsvExportCard() {
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [feedback, setFeedback] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  const exportMutation = useExportCsvMutation();

  // Preset Date Handlers
  const handlePreset = (days: number | 'all') => {
    if (days === 'all') {
      setStartDate('');
      setEndDate('');
      return;
    }

    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - days);

    setEndDate(end.toISOString().split('T')[0]);
    setStartDate(start.toISOString().split('T')[0]);
  };

  // Date validation
  const isDateRangeInvalid =
    Boolean(startDate && endDate && startDate > endDate);

  const handleExportCsv = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isDateRangeInvalid || exportMutation.isPending) return;

    setFeedback(null);
    try {
      await exportMutation.mutateAsync({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });

      setFeedback({
        type: 'success',
        text: 'CSV report successfully generated and downloaded (RFC 4180 format).',
      });
      setTimeout(() => setFeedback(null), 5000);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setFeedback({ type: 'error', text: err.message });
      } else {
        setFeedback({ type: 'error', text: 'Failed to export CSV report.' });
      }
    }
  };

  return (
    <Card className="glass-card font-mono text-xs w-full">
      <CardHeader className="pb-3 border-b border-border/50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-brand-400" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              Trade Performance History CSV Exporter
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400 mt-0.5">
            Export closed trades and execution audit data conforming to RFC 4180 standard
          </CardDescription>
        </div>

        {/* Quick Date Presets */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => handlePreset(7)}
            className="px-2.5 py-1 rounded bg-surface/70 border border-border/70 text-slate-300 hover:text-white hover:border-slate-500 text-[11px] font-bold transition-all"
          >
            Last 7 Days
          </button>
          <button
            type="button"
            onClick={() => handlePreset(30)}
            className="px-2.5 py-1 rounded bg-surface/70 border border-border/70 text-slate-300 hover:text-white hover:border-slate-500 text-[11px] font-bold transition-all"
          >
            Last 30 Days
          </button>
          <button
            type="button"
            onClick={() => handlePreset('all')}
            className="px-2.5 py-1 rounded bg-surface/70 border border-border/70 text-slate-300 hover:text-white hover:border-slate-500 text-[11px] font-bold transition-all"
          >
            All Time
          </button>
        </div>
      </CardHeader>

      <CardContent className="pt-4">
        <form onSubmit={handleExportCsv} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Start Date */}
            <div className="space-y-1.5">
              <label htmlFor="start-date-input" className="text-slate-300 font-medium flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-brand-400" /> Start Date
              </label>
              <Input
                id="start-date-input"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="h-9 bg-surface/70 border-border/80 text-white font-mono text-xs"
              />
            </div>

            {/* End Date */}
            <div className="space-y-1.5">
              <label htmlFor="end-date-input" className="text-slate-300 font-medium flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-sky-400" /> End Date
              </label>
              <Input
                id="end-date-input"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="h-9 bg-surface/70 border-border/80 text-white font-mono text-xs"
              />
            </div>
          </div>

          {/* Validation Warning */}
          {isDateRangeInvalid && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs animate-in fade-in-0">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>
                Invalid Date Range: Start Date cannot be after End Date.
              </span>
            </div>
          )}

          {/* Feedback Success/Error */}
          {feedback && (
            <div
              className={`flex items-center gap-2 p-3 rounded-lg border text-xs animate-in fade-in-0 ${
                feedback.type === 'success'
                  ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
                  : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
              }`}
            >
              {feedback.type === 'success' ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              )}
              <span>{feedback.text}</span>
            </div>
          )}

          {/* Export Action Row */}
          <div className="flex items-center justify-between pt-1">
            <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
              <Table className="w-3.5 h-3.5 text-slate-500" />
              <span>Includes Trade ID, Entry, Exit, Net PnL, ROI %, Fees & Reasons</span>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={isDateRangeInvalid || exportMutation.isPending}
              isLoading={exportMutation.isPending}
              className="gap-2 shadow-glow-brand font-bold"
            >
              {!exportMutation.isPending && <Download className="w-4 h-4" />}
              Download CSV Report
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
