import React from 'react';
import { Navbar } from './Navbar';
import { Sidebar, NavRoute } from './Sidebar';
import { MobileNav } from './MobileNav';
import { ErrorBoundary } from '@/components/feedback/ErrorBoundary';
import { ToastProvider } from '@/components/feedback/ToastProvider';

export interface AppLayoutProps {
  children: React.ReactNode;
  currentRoute: NavRoute;
  onRouteChange: (route: NavRoute) => void;
}

export function AppLayout({
  children,
  currentRoute,
  onRouteChange,
}: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-canvas text-slate-100 flex flex-col font-sans selection:bg-brand-500/30 selection:text-brand-300">
      {/* Sticky Top Navbar */}
      <Navbar />

      <div className="flex-1 flex w-full">
        {/* Left Sticky Sidebar (Desktop & Tablet) */}
        <div className="hidden md:block">
          <Sidebar currentRoute={currentRoute} onRouteChange={onRouteChange} />
        </div>

        {/* Main View Area */}
        <main className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8 overflow-y-auto pb-24 md:pb-8">
          <div className="max-w-[1600px] mx-auto space-y-6">
            <ErrorBoundary>
              {children}
            </ErrorBoundary>
          </div>
        </main>
      </div>

      {/* Mobile Bottom Navigation Bar (< 768px) */}
      <MobileNav currentRoute={currentRoute} onRouteChange={onRouteChange} />

      {/* Global Toast Notifications Layer */}
      <ToastProvider />
    </div>
  );
}
