import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorBoundary } from '@/components/feedback/ErrorBoundary';

function CrashingComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Critical Canvas Rendering Failure');
  }
  return <div>Component Rendered Successfully</div>;
}

describe('ErrorBoundary Component Integration', () => {
  // Suppress console.error in test output for intentional errors
  const originalError = console.error;
  beforeEach(() => {
    console.error = vi.fn();
  });
  afterEach(() => {
    console.error = originalError;
  });

  it('renders children normally when no error is thrown', () => {
    render(
      <ErrorBoundary>
        <CrashingComponent shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(
      screen.getByText('Component Rendered Successfully')
    ).toBeInTheDocument();
  });

  it('catches thrown error, renders isolated fallback UI and provides retry button', async () => {
    const { rerender } = render(
      <ErrorBoundary
        fallbackTitle="Custom Widget Error"
        fallbackMessage="Failed to render trading canvas"
      >
        <CrashingComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom Widget Error')).toBeInTheDocument();
    expect(
      screen.getByText('Failed to render trading canvas')
    ).toBeInTheDocument();

    const retryBtn = screen.getByRole('button', { name: /retry component/i });
    expect(retryBtn).toBeInTheDocument();

    // Rerender with valid state and click retry
    rerender(
      <ErrorBoundary
        fallbackTitle="Custom Widget Error"
        fallbackMessage="Failed to render trading canvas"
      >
        <CrashingComponent shouldThrow={false} />
      </ErrorBoundary>
    );

    await userEvent.click(retryBtn);
    expect(
      screen.getByText('Component Rendered Successfully')
    ).toBeInTheDocument();
  });
});
