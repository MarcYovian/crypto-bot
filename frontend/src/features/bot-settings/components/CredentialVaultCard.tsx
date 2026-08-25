import { useState } from 'react';
import { useSaveCredentialsMutation } from '@/hooks/useBotOperations';
import { CredentialSaveResponseDTO } from '@/types/bot';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { formatUSDT } from '@/utils/format';
import {
  KeyRound,
  Eye,
  EyeOff,
  Radio,
  CheckCircle2,
  AlertTriangle,
  Send,
  Lock,
  Wallet,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export function CredentialVaultCard() {
  const [apiKey, setApiKey] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [environment, setEnvironment] = useState<'TESTNET' | 'LIVE'>('TESTNET');

  const [showApiKey, setShowApiKey] = useState(false);
  const [showSecretKey, setShowSecretKey] = useState(false);

  const [feedback, setFeedback] = useState<{
    type: 'success' | 'error';
    data?: CredentialSaveResponseDTO;
    message?: string;
  } | null>(null);

  const saveMutation = useSaveCredentialsMutation();

  const handleSaveCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim() || !secretKey.trim() || saveMutation.isPending) return;

    setFeedback(null);
    try {
      const res = await saveMutation.mutateAsync({
        api_key: apiKey.trim(),
        secret_key: secretKey.trim(),
        environment,
      });

      setFeedback({
        type: 'success',
        data: res,
        message: `Handshake successful! Connected to Binance ${res.environment} with live balance ${formatUSDT(res.wallet_balance_usdt)}.`,
      });
      // Clear inputs for security
      setApiKey('');
      setSecretKey('');
      setShowApiKey(false);
      setShowSecretKey(false);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setFeedback({ type: 'error', message: err.message });
      } else {
        setFeedback({
          type: 'error',
          message: 'Exchange Authentication Failed: Invalid API Key or IP restriction error.',
        });
      }
    }
  };

  return (
    <Card className="glass-card font-mono text-xs w-full">
      <CardHeader className="pb-3 border-b border-border/50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-brand-400 shrink-0" />
            <CardTitle className="text-base font-bold text-white tracking-tight">
              Binance Credential Vault & Live Handshake
            </CardTitle>
          </div>
          <CardDescription className="text-xs text-slate-400">
            Store AES-256 encrypted exchange API keys and verify live wallet connection
          </CardDescription>
        </div>

        <Badge
          variant={environment === 'LIVE' ? 'loss' : 'warning'}
          size="sm"
          className="font-bold shrink-0 whitespace-nowrap gap-1.5 self-start sm:self-auto py-1 px-2.5"
        >
          <span
            className={`w-1.5 h-1.5 rounded-full shrink-0 ${
              environment === 'LIVE'
                ? 'bg-rose-400 animate-pulse'
                : 'bg-amber-400'
            }`}
          />
          {environment === 'LIVE' ? 'LIVE REAL CAPITAL' : 'TESTNET SIMULATOR'}
        </Badge>
      </CardHeader>

      <CardContent className="pt-4">
        <form onSubmit={handleSaveCredentials} className="space-y-4">
          {/* Environment Switcher */}
          <div className="p-3 rounded-xl bg-surface/50 border border-border/60 flex items-center justify-between">
            <span className="text-slate-300 font-bold flex items-center gap-1.5">
              <Radio className="w-3.5 h-3.5 text-brand-400" /> Target Exchange Network
            </span>

            <div className="flex items-center gap-1 bg-slate-900/80 p-1 rounded-lg border border-border/60">
              <button
                type="button"
                onClick={() => setEnvironment('TESTNET')}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-bold transition-all',
                  environment === 'TESTNET'
                    ? 'bg-brand-500 text-white shadow-glow-brand'
                    : 'text-slate-400 hover:text-white'
                )}
              >
                Binance Testnet
              </button>
              <button
                type="button"
                onClick={() => setEnvironment('LIVE')}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-bold transition-all',
                  environment === 'LIVE'
                    ? 'bg-rose-600 text-white shadow-glow-loss'
                    : 'text-slate-400 hover:text-white'
                )}
              >
                Binance Live Futures
              </button>
            </div>
          </div>

          {/* API Key */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium flex items-center justify-between">
              <span className="flex items-center gap-1">
                <Lock className="w-3.5 h-3.5 text-brand-400" /> Binance API Key
              </span>
              <span className="text-[10px] text-slate-500">64-character public key</span>
            </label>
            <div className="relative">
              <Input
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter Binance API key..."
                className="pr-10 h-9 bg-surface/70 border-border/80 text-white font-mono"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-white transition-colors"
                aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
              >
                {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Secret Key */}
          <div className="space-y-1.5">
            <label className="text-slate-300 font-medium flex items-center justify-between">
              <span className="flex items-center gap-1">
                <Lock className="w-3.5 h-3.5 text-amber-400" /> Binance API Secret Key
              </span>
              <span className="text-[10px] text-slate-500">Encrypted with AES-256</span>
            </label>
            <div className="relative">
              <Input
                type={showSecretKey ? 'text' : 'password'}
                value={secretKey}
                onChange={(e) => setSecretKey(e.target.value)}
                placeholder="Enter Binance Secret key..."
                className="pr-10 h-9 bg-surface/70 border-border/80 text-white font-mono"
              />
              <button
                type="button"
                onClick={() => setShowSecretKey(!showSecretKey)}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-white transition-colors"
                aria-label={showSecretKey ? 'Hide Secret key' : 'Show Secret key'}
              >
                {showSecretKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Feedback & Balance Result Banner */}
          {feedback && feedback.type === 'success' && feedback.data && (
            <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/50 space-y-2 animate-in fade-in-0">
              <div className="flex items-center gap-2 font-bold text-emerald-300">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Handshake Successful & Keys Saved</span>
              </div>
              <div className="p-3 rounded-lg bg-surface/80 border border-emerald-800/40 flex items-center justify-between">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <Wallet className="w-3.5 h-3.5 text-emerald-400" /> Verified Wallet Balance:
                </span>
                <span className="text-emerald-300 font-bold text-sm">
                  {formatUSDT(feedback.data.wallet_balance_usdt)}
                </span>
              </div>
            </div>
          )}

          {feedback && feedback.type === 'error' && (
            <div className="flex items-center gap-2 p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs animate-in fade-in-0">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{feedback.message}</span>
            </div>
          )}

          {/* Submit Handshake Action */}
          <div className="flex justify-end pt-2">
            <RoleGuard requiredRole="ADMIN" mode="disable">
              <Button
                type="submit"
                variant="primary"
                size="md"
                disabled={!apiKey.trim() || !secretKey.trim() || saveMutation.isPending}
                isLoading={saveMutation.isPending}
                className="gap-2 shadow-glow-brand"
              >
                {!saveMutation.isPending && <Send className="w-4 h-4" />}
                Test Handshake & Save Credentials
              </Button>
            </RoleGuard>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
