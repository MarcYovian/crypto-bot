import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuditLogsTerminal } from '@/features/logs-reports/components/AuditLogsTerminal';
import { LogFilterToolbar } from '@/features/logs-reports/components/LogFilterToolbar';
import { LogEntryDTO } from '@/types/logs';

const mockLogs: LogEntryDTO[] = [
  {
    id: 1,
    level: 'INFO',
    module: 'EXECUTION_ENGINE',
    message: 'Market order filled for BTCUSDT: 0.02 BTC @ 50000.00',
    trace_id: 'sig-a1b2c3d4',
    created_at: '2026-08-24T14:30:05Z',
  },
  {
    id: 2,
    level: 'WARNING',
    module: 'RISK_GUARD',
    message: 'Approaching daily loss limit: $120.00 / $150.00 threshold',
    trace_id: 'sig-e5f6g7h8',
    created_at: '2026-08-24T14:31:10Z',
  },
  {
    id: 3,
    level: 'ERROR',
    module: 'BINANCE_REST',
    message: 'Exchange connection timeout retrying order placement',
    trace_id: null,
    created_at: '2026-08-24T14:32:15Z',
  },
];

describe('AuditLogsTerminal Component', () => {
  beforeEach(() => {
    // Mock scrollIntoView
    Element.prototype.scrollIntoView = vi.fn();
    // Mock clipboard
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('renders log messages, severity badges, modules, and trace_ids', () => {
    render(<AuditLogsTerminal logs={mockLogs} />);

    expect(screen.getByText('system_audit_terminal.log')).toBeInTheDocument();
    expect(
      screen.getByText('Market order filled for BTCUSDT: 0.02 BTC @ 50000.00')
    ).toBeInTheDocument();
    expect(screen.getByText('INFO')).toBeInTheDocument();
    expect(screen.getByText('[EXECUTION_ENGINE]')).toBeInTheDocument();
    expect(screen.getByText('sig-a1b2c3d4')).toBeInTheDocument();

    expect(
      screen.getByText('Approaching daily loss limit: $120.00 / $150.00 threshold')
    ).toBeInTheDocument();
    expect(screen.getByText('WARNING')).toBeInTheDocument();

    expect(
      screen.getByText('Exchange connection timeout retrying order placement')
    ).toBeInTheDocument();
    expect(screen.getByText('ERROR')).toBeInTheDocument();
  });

  it('copies trace_id to clipboard when clicked', async () => {
    render(<AuditLogsTerminal logs={mockLogs} />);

    const traceBtn = screen.getByRole('button', { name: /sig-a1b2c3d4/i });
    await userEvent.click(traceBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('sig-a1b2c3d4');
  });
});

describe('LogFilterToolbar Component', () => {
  const defaultParams = { level: 'ALL', trace_id: '', limit: 100 };

  it('triggers onChange when level pills are clicked', async () => {
    const handleChange = vi.fn();
    render(
      <LogFilterToolbar
        params={defaultParams}
        onChange={handleChange}
        isLive={true}
        onToggleLive={vi.fn()}
        autoScroll={true}
        onToggleAutoScroll={vi.fn()}
        totalLogsCount={3}
      />
    );

    const warnBtn = screen.getByRole('button', { name: 'WARNING' });
    await userEvent.click(warnBtn);

    expect(handleChange).toHaveBeenCalledWith(
      expect.objectContaining({ level: 'WARNING' })
    );
  });

  it('triggers onChange on trace_id typing and allows clearing', async () => {
    const handleChange = vi.fn();
    render(
      <LogFilterToolbar
        params={{ ...defaultParams, trace_id: 'sig-test' }}
        onChange={handleChange}
        isLive={true}
        onToggleLive={vi.fn()}
        autoScroll={true}
        onToggleAutoScroll={vi.fn()}
        totalLogsCount={1}
      />
    );

    const clearBtn = screen.getByRole('button', { name: '' });
    await userEvent.click(clearBtn);

    expect(handleChange).toHaveBeenCalledWith(
      expect.objectContaining({ trace_id: '' })
    );
  });
});
