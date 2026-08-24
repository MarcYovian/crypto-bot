import React, { useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Shield, Lock, User, Eye, EyeOff, AlertCircle } from 'lucide-react';

export interface LoginPageProps {
  onLoginSuccess?: () => void;
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const { login, isLoading, error } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      return;
    }
    const success = await login({ username: username.trim(), password });
    if (success && onLoginSuccess) {
      onLoginSuccess();
    }
  };

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center p-4 selection:bg-brand-500 selection:text-white">
      {/* Background glow ambiance */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[600px] h-[350px] bg-brand-500/10 blur-[120px] rounded-full" />
      </div>

      <Card className="w-full max-w-md glass-card relative z-10 border-border/80 shadow-2xl">
        <CardHeader className="space-y-3 text-center pb-6 border-b border-border/50">
          <div className="mx-auto w-12 h-12 rounded-xl bg-brand-500/20 border border-brand-500/40 flex items-center justify-center text-brand-400 shadow-glow-brand">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <CardTitle className="text-xl font-bold text-white tracking-tight">
              SMC CryptoBot Terminal
            </CardTitle>
            <CardDescription className="text-xs text-slate-400 mt-1">
              Sign in with your trader administrator credentials
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div
                role="alert"
                className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 text-xs text-rose-300 flex items-center gap-2 animate-in fade-in-0 duration-200"
              >
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label
                htmlFor="username"
                className="text-xs font-medium text-slate-300"
              >
                Username
              </label>
              <Input
                id="username"
                type="text"
                placeholder="admin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                prefixNode={<User className="w-4 h-4 text-slate-400" />}
                required
                autoComplete="username"
                disabled={isLoading}
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="text-xs font-medium text-slate-300"
              >
                Password
              </label>
              <div className="relative flex items-center">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  prefixNode={<Lock className="w-4 h-4 text-slate-400" />}
                  required
                  autoComplete="current-password"
                  disabled={isLoading}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 text-slate-400 hover:text-slate-200 transition-colors focus:outline-none"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full mt-2 font-semibold shadow-glow-brand"
              isLoading={isLoading}
              disabled={!username.trim() || !password.trim()}
            >
              Sign In to Terminal
            </Button>
          </form>

          <div className="mt-6 pt-4 border-t border-border/40 text-center">
            <p className="text-[11px] text-slate-500 font-mono">
              Default Admin: <span className="text-slate-400">admin</span> /{' '}
              <span className="text-slate-400">AdminPassword123!</span>
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
