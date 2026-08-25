import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CsvExportCard } from '@/features/logs-reports/components/CsvExportCard';
import * as logsApi from '@/api/endpoints/logs';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('CsvExportCard Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders presets and updates date inputs on click', async () => {
    renderWithQuery(<CsvExportCard />);

    expect(
      screen.getByText('Trade Performance History CSV Exporter')
    ).toBeInTheDocument();

    const last7Btn = screen.getByRole('button', { name: /last 7 days/i });
    await userEvent.click(last7Btn);

    const inputs = screen.getAllByDisplayValue(/\d{4}-\d{2}-\d{2}/);
    expect(inputs.length).toBe(2);
  });

  it('displays validation error and disables submit when start date is after end date', async () => {
    renderWithQuery(<CsvExportCard />);

    const [startDateInput, endDateInput] = [
      screen.getByLabelText(/start date/i),
      screen.getByLabelText(/end date/i),
    ];

    await userEvent.type(startDateInput, '2026-08-20');
    await userEvent.type(endDateInput, '2026-08-10');

    expect(
      screen.getByText(/Invalid Date Range: Start Date cannot be after End Date/i)
    ).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', {
      name: /download csv report/i,
    });
    expect(submitBtn).toBeDisabled();
  });

  it('calls exportTradesCsvApi and downloads CSV on valid submission', async () => {
    const mockBlob = new Blob(['Trade ID,Symbol\n1,BTCUSDT'], {
      type: 'text/csv',
    });
    const exportSpy = vi
      .spyOn(logsApi, 'exportTradesCsvApi')
      .mockResolvedValueOnce(mockBlob);

    // Mock triggerFileDownload to avoid DOM click in jsdom
    const downloadSpy = vi
      .spyOn(logsApi, 'triggerFileDownload')
      .mockImplementation(() => {});

    renderWithQuery(<CsvExportCard />);

    const [startDateInput, endDateInput] = [
      screen.getByLabelText(/start date/i),
      screen.getByLabelText(/end date/i),
    ];

    await userEvent.type(startDateInput, '2026-08-01');
    await userEvent.type(endDateInput, '2026-08-20');

    const submitBtn = screen.getByRole('button', {
      name: /download csv report/i,
    });
    expect(submitBtn).not.toBeDisabled();
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(exportSpy).toHaveBeenCalledWith('2026-08-01', '2026-08-20');
      expect(downloadSpy).toHaveBeenCalled();
      expect(
        screen.getByText(/CSV report successfully generated and downloaded/i)
      ).toBeInTheDocument();
    });
  });
});
