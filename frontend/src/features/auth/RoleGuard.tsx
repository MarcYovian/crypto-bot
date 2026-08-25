import React from 'react';
import { useAuthStore } from '@/stores/authStore';
import { Role } from '@/types/common';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';

export interface RoleGuardProps {
  children: React.ReactNode;
  requiredRole?: Role;
  mode?: 'disable' | 'hide';
  fallback?: React.ReactNode;
}

export function RoleGuard({
  children,
  requiredRole = 'ADMIN',
  mode = 'disable',
  fallback = null,
}: RoleGuardProps) {
  const { user } = useAuthStore();

  const isAllowed = user?.role === requiredRole || (requiredRole === 'VIEWER' && !!user);

  if (isAllowed) {
    return <>{children}</>;
  }

  if (mode === 'hide') {
    return <>{fallback}</>;
  }

  // mode === 'disable': wrap in Tooltip and pass disabled prop to child if valid element
  if (React.isValidElement(children)) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-block cursor-not-allowed">
            {React.cloneElement(children as React.ReactElement<{ disabled?: boolean; className?: string }>, {
              disabled: true,
              className: `${(children.props.className || '')} pointer-events-none opacity-50`,
            })}
          </span>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs text-rose-300">
            🔒 Action restricted to {requiredRole} role.
          </p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return <>{fallback}</>;
}
