import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/api/builderApiClient', () => ({
  exportReinforcementsReport: vi.fn(() => Promise.resolve(new Blob(['x']))),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import { exportReinforcementsReport } from '../src/api/builderApiClient';
import ReinforcementsReportPage, { reportRange } from '../src/pages/ReinforcementsReportPage';
import messages from '../src/utils/messages';

const m = messages.actualBoard.reinforcements;

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/actual/report']}>
      <ReinforcementsReportPage />
    </MemoryRouter>,
  );
}

describe('reportRange (period cuts)', () => {
  it('daily = the anchor day itself', () => {
    expect(reportRange('daily', '2026-07-15')).toEqual(['2026-07-15', '2026-07-15']);
  });

  it('weekly = the Sunday–Saturday week containing the anchor', () => {
    // 2026-07-15 is a Wednesday → week runs Sun 12/07 – Sat 18/07.
    expect(reportRange('weekly', '2026-07-15')).toEqual(['2026-07-12', '2026-07-18']);
    // A Sunday anchors its own week.
    expect(reportRange('weekly', '2026-07-12')).toEqual(['2026-07-12', '2026-07-18']);
  });

  it('monthly = the anchor\'s calendar month', () => {
    expect(reportRange('monthly', '2026-07-15')).toEqual(['2026-07-01', '2026-07-31']);
    expect(reportRange('monthly', '2026-02-10')).toEqual(['2026-02-01', '2026-02-28']);
  });
});

describe('ReinforcementsReportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.URL.createObjectURL = vi.fn(() => 'blob:mock');
    global.URL.revokeObjectURL = vi.fn();
  });

  it('downloads the xlsx for the chosen cut', async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(new RegExp(m.reportCut)), {
      target: { value: 'monthly' },
    });
    fireEvent.change(screen.getByLabelText(new RegExp(m.reportDate)), {
      target: { value: '2026-07-15' },
    });
    fireEvent.click(screen.getByRole('button', { name: new RegExp(m.reportDownload) }));

    await waitFor(() =>
      expect(exportReinforcementsReport).toHaveBeenCalledWith('2026-07-01', '2026-07-31'),
    );
  });

  it('shows the resolved range and links back to the actual board', () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(new RegExp(m.reportCut)), {
      target: { value: 'daily' },
    });
    fireEvent.change(screen.getByLabelText(new RegExp(m.reportDate)), {
      target: { value: '2026-07-15' },
    });
    expect(screen.getByText(/15\/07\/2026 – 15\/07\/2026/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: new RegExp(m.backToBoard.replace('→ ', '')) }))
      .toHaveAttribute('href', '/actual');
  });

  it('surfaces a failed download as a toast', async () => {
    exportReinforcementsReport.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: new RegExp(m.reportDownload) }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('boom'));
  });
});
