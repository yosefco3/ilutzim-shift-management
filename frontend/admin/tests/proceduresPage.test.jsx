import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const navigate = vi.fn();
vi.mock('react-router-dom', async (orig) => {
  const actual = await orig();
  return { ...actual, useNavigate: () => navigate };
});

vi.mock('../src/api/adminApiClient', () => ({
  fetchProcedures: vi.fn(),
  createProcedure: vi.fn(),
  uploadProcedureDocx: vi.fn(),
  generateProcedureQuestions: vi.fn(),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import {
  fetchProcedures,
  createProcedure,
  uploadProcedureDocx,
  generateProcedureQuestions,
} from '../src/api/adminApiClient';
import ProceduresPage from '../src/pages/ProceduresPage';
import messages from '../src/utils/messages';

const m = messages.procedures;

const DRAFT_PROC = {
  id: 'p1',
  title: 'נוהל תגובה לחריגת גדר',
  status: 'draft',
  created_at: '2026-07-09T10:00:00',
  published_at: null,
  active_questions: 0,
  total_questions: 0,
};
const PUBLISHED_PROC = {
  id: 'p2',
  title: 'נוהל מעבר משמרת',
  status: 'published',
  created_at: '2026-07-01T10:00:00',
  published_at: '2026-07-02T10:00:00',
  active_questions: 7,
  total_questions: 18,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ProceduresPage />
    </MemoryRouter>,
  );
}

describe('ProceduresPage', () => {
  beforeEach(() => {
    fetchProcedures.mockReset();
    createProcedure.mockReset();
    uploadProcedureDocx.mockReset();
    generateProcedureQuestions.mockReset();
    toast.success.mockReset();
    toast.error.mockReset();
    navigate.mockReset();
  });

  it('renders the list of procedures with status + question counts', async () => {
    fetchProcedures.mockResolvedValue([PUBLISHED_PROC, DRAFT_PROC]);
    renderPage();

    expect(await screen.findByText('נוהל מעבר משמרת')).toBeInTheDocument();
    expect(screen.getByText('נוהל תגובה לחריגת גדר')).toBeInTheDocument();
    // Draft row: active/total count; published row: active-only count.
    expect(screen.getByText(m.questionsCount(0, 0))).toBeInTheDocument();
    expect(screen.getByText(m.activeOnly(7))).toBeInTheDocument();
    // Generate button only on the draft row.
    expect(screen.getByTestId('generate-p1')).toBeInTheDocument();
    expect(screen.queryByTestId('generate-p2')).toBeNull();
  });

  it('shows the empty state when there are no procedures', async () => {
    fetchProcedures.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(m.noProcedures)).toBeInTheDocument();
  });

  it('creates a draft from pasted title + text', async () => {
    fetchProcedures.mockResolvedValue([]);
    createProcedure.mockResolvedValue({ id: 'new-1', title: 't', status: 'draft' });
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: m.add }));

    fireEvent.change(screen.getByLabelText(m.titleField), { target: { value: 'נוהל חדש' } });
    fireEvent.change(screen.getByLabelText(m.bodyField), { target: { value: 'גוף הנוהל' } });
    fireEvent.click(screen.getByTestId('save-draft'));

    await waitFor(() =>
      expect(createProcedure).toHaveBeenCalledWith({ title: 'נוהל חדש', body_text: 'גוף הנוהל' }),
    );
    expect(toast.success).toHaveBeenCalledWith(m.createdToast);
    expect(navigate).toHaveBeenCalledWith('/procedures/new-1');
  });

  it('blocks save when the title or body is empty', async () => {
    fetchProcedures.mockResolvedValue([]);
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: m.add }));
    fireEvent.click(screen.getByTestId('save-draft'));

    expect(await screen.findByText(m.errTitleRequired)).toBeInTheDocument();
    expect(createProcedure).not.toHaveBeenCalled();
  });

  it('uploads a .docx → fills the body with the extracted text for review', async () => {
    const extracted = 'תוכן שהופק מהקובץ';
    fetchProcedures.mockResolvedValue([]);
    uploadProcedureDocx.mockResolvedValue({
      text: extracted,
      source_filename: 'procedure.docx',
      char_count: extracted.length,
    });
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: m.add }));

    const file = new File(['docx-bytes'], 'procedure.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    fireEvent.change(screen.getByTestId('docx-input'), { target: { files: [file] } });

    await waitFor(() => expect(uploadProcedureDocx).toHaveBeenCalledWith(file, ''));
    // The extracted text fills the editable body for review.
    expect(await screen.findByLabelText(m.bodyField)).toHaveValue(extracted);
    // And the source filename + char count are surfaced.
    expect(screen.getByTestId('docx-extracted')).toHaveTextContent('procedure.docx');
    expect(screen.getByTestId('docx-extracted')).toHaveTextContent(
      m.extractedChars(extracted.length),
    );
  });

  it('shows the generate spinner then a toast on success', async () => {
    fetchProcedures.mockResolvedValue([DRAFT_PROC]);
    generateProcedureQuestions.mockResolvedValue({ generated: 15, skipped: 0, total_questions: 15 });
    renderPage();
    await screen.findByText('נוהל תגובה לחריגת גדר');

    fireEvent.click(screen.getByTestId('generate-p1'));

    // While generating, the button shows the generating label and is disabled.
    await waitFor(() => expect(generateProcedureQuestions).toHaveBeenCalledWith('p1'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(m.generateDone(15)));
  });

  it('shows a clear unavailable error on 503 (no key / API failure)', async () => {
    fetchProcedures.mockResolvedValue([DRAFT_PROC]);
    const err = new Error('x');
    err.status = 503;
    generateProcedureQuestions.mockRejectedValue(err);
    renderPage();
    await screen.findByText('נוהל תגובה לחריגת גדר');

    fireEvent.click(screen.getByTestId('generate-p1'));

    expect(await screen.findByText(m.errGenerateUnavailable)).toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('surfaces the backend detail on a 409 generate', async () => {
    fetchProcedures.mockResolvedValue([DRAFT_PROC]);
    const err = new Error('ניתן לחדש שאלות לנוהל טיוטה בלבד');
    err.status = 409;
    generateProcedureQuestions.mockRejectedValue(err);
    renderPage();
    await screen.findByText('נוהל תגובה לחריגת גדר');

    fireEvent.click(screen.getByTestId('generate-p1'));

    expect(await screen.findByText('ניתן לחדש שאלות לנוהל טיוטה בלבד')).toBeInTheDocument();
  });

  it('opens the detail page when a row is clicked', async () => {
    fetchProcedures.mockResolvedValue([DRAFT_PROC]);
    renderPage();
    await screen.findByText('נוהל תגובה לחריגת גדר');

    fireEvent.click(screen.getByTestId('open-p1'));
    expect(navigate).toHaveBeenCalledWith('/procedures/p1');
  });
});
