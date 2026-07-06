import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/api/adminApiClient', () => ({
  previewConstraintsImport: vi.fn(),
  commitConstraintsImport: vi.fn(),
}));
vi.mock('../src/hooks/useWeeks', () => ({
  useWeeks: () => ({ weeks: [], loading: false }),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({
  useToast: () => toast,
}));

import {
  previewConstraintsImport,
  commitConstraintsImport,
} from '../src/api/adminApiClient';
import ImportConstraintsPage from '../src/pages/ImportConstraintsPage';

const SAMPLE_PREVIEW = {
  week_start: '2026-06-14',
  week_end: '2026-06-20',
  errors: [],
  guards: [
    {
      name: 'דנה אזולאי',
      exists: false,
      notes: 'זמינה בכל המשמרות',
      weekly_hours: 60.0,
      days: [
        { day_index: 0, day_name: 'ראשון', segments: ['07:00–23:00'], hours: 16.0,
          shifts: { morning: '07:00–15:00', afternoon: '15:00–23:00', night: null } },
        ...Array.from({ length: 6 }, (_, i) => ({
          day_index: i + 1, day_name: 'x', segments: [], hours: 0,
          shifts: { morning: null, afternoon: null, night: null },
        })),
      ],
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ImportConstraintsPage />
    </MemoryRouter>,
  );
}

function selectFile() {
  const input = screen.getByTestId('file-input');
  const file = new File(['xlsx-bytes'], 'constraints.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

describe('ImportConstraintsPage', () => {
  beforeEach(() => {
    previewConstraintsImport.mockReset();
    commitConstraintsImport.mockReset();
    toast.success.mockReset();
    toast.error.mockReset();
  });

  it('disables preview until a file is chosen', () => {
    renderPage();
    expect(screen.getByRole('button', { name: 'תצוגה מקדימה' })).toBeDisabled();
  });

  it('uploads the file and renders a clean merged table', async () => {
    previewConstraintsImport.mockResolvedValue(SAMPLE_PREVIEW);
    renderPage();
    selectFile();

    fireEvent.click(screen.getByRole('button', { name: 'תצוגה מקדימה' }));

    await waitFor(() => expect(previewConstraintsImport).toHaveBeenCalled());

    // merged union window + weekly hours + notes + new badge are shown
    expect(screen.getByText('07:00–23:00')).toBeInTheDocument();
    expect(screen.getByText('דנה אזולאי')).toBeInTheDocument();
    expect(screen.getByText('זמינה בכל המשמרות')).toBeInTheDocument();
    expect(screen.getByText('חדש')).toBeInTheDocument();
    // week range surfaced
    expect(screen.getByText(/2026-06-14/)).toBeInTheDocument();
  });

  it('shows parse errors prominently', async () => {
    previewConstraintsImport.mockResolvedValue({
      ...SAMPLE_PREVIEW,
      errors: ['אבי כהן · שלישי · בוקר: ערך לא תקין'],
    });
    renderPage();
    selectFile();
    fireEvent.click(screen.getByRole('button', { name: 'תצוגה מקדימה' }));

    await waitFor(() =>
      expect(screen.getByTestId('parse-errors')).toBeInTheDocument(),
    );
    expect(screen.getByText(/ערך לא תקין/)).toBeInTheDocument();
  });

  it('confirms import → commits and shows a summary report', async () => {
    previewConstraintsImport.mockResolvedValue(SAMPLE_PREVIEW);
    commitConstraintsImport.mockResolvedValue({
      summary: {
        week_start: '2026-06-14', week_end: '2026-06-20',
        imported: 5, created_new: 2, errors: [],
      },
      guards: SAMPLE_PREVIEW.guards,
    });
    renderPage();
    const file = selectFile();

    fireEvent.click(screen.getByRole('button', { name: 'תצוגה מקדימה' }));
    await waitFor(() => expect(screen.getByText('07:00–23:00')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'אשר ייבוא' }));

    await waitFor(() => expect(commitConstraintsImport).toHaveBeenCalledWith(file, undefined));
    expect(await screen.findByTestId('summary-report')).toBeInTheDocument();
    expect(screen.getByText(/5/)).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalled();
  });

  it('surfaces an upload error message', async () => {
    previewConstraintsImport.mockRejectedValue(new Error('לא ניתן לקרוא את הקובץ'));
    renderPage();
    selectFile();
    fireEvent.click(screen.getByRole('button', { name: 'תצוגה מקדימה' }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('לא ניתן לקרוא את הקובץ'),
    );
  });
});
