import { useAuthStore } from '@/stores/authStore';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { User, LogOut } from 'lucide-react';

export function UserMenuBadge() {
  const { user, logout } = useAuthStore();

  if (!user) {
    return null;
  }

  const roleVariant = user.role === 'ADMIN' ? 'admin' : 'viewer';

  return (
    <div className="flex items-center gap-3 bg-surface/80 border border-border/80 rounded-xl px-3 py-1.5 backdrop-blur-md shadow-sm">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-brand-500/20 border border-brand-500/30 flex items-center justify-center text-brand-400">
          <User className="w-4 h-4" />
        </div>
        <div className="flex flex-col text-left">
          <span className="text-xs font-semibold text-white leading-tight font-mono">
            {user.username}
          </span>
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">
            Operator
          </span>
        </div>
      </div>

      <Badge variant={roleVariant} size="sm">
        {user.role}
      </Badge>

      <div className="h-4 w-px bg-border/80" />

      <Button
        variant="ghost"
        size="sm"
        onClick={logout}
        className="text-slate-400 hover:text-rose-400 hover:bg-rose-950/30 p-1.5 h-auto text-xs"
        aria-label="Logout"
        title="Logout from Terminal"
      >
        <LogOut className="w-3.5 h-3.5" />
      </Button>
    </div>
  );
}
