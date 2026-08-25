import { Component, ErrorInfo, ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
    };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary] Uncaught component error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
    });
  };

  render() {
    if (this.state.hasError) {
      return (
        <Card className="glass-card p-6 border-dashed border-rose-500/50 bg-rose-950/20 text-slate-200 font-mono text-xs my-3 text-center flex flex-col items-center justify-center space-y-3">
          <div className="w-10 h-10 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5" />
          </div>

          <div>
            <h3 className="text-sm font-bold text-white tracking-tight">
              {this.props.fallbackTitle || 'Component Execution Error'}
            </h3>
            <p className="text-xs text-rose-300/90 mt-1 max-w-md">
              {this.props.fallbackMessage ||
                this.state.error?.message ||
                'An unexpected error occurred while rendering this module.'}
            </p>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={this.handleReset}
            className="gap-1.5 border-rose-500/40 text-rose-300 hover:bg-rose-500/10 hover:text-white"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry Component
          </Button>
        </Card>
      );
    }

    return this.props.children;
  }
}
