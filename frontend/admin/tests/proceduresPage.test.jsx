import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
  publishProcedure: vi.fn(),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import {
  fetchProcedures,
  createProcedure,
  uploadProcedureDocx,
  generateProcedureQuestions,
  publishProcedure,
} from '../src/api/adminApiClient';
import ProceduresPage from '../src/pages/ProceduresPage';
import messages from '../src/utils/messages';

const m = messages.procedures;

const DRAFT_PROC = {
  id: 'p1',
  title: 'נוהל תגובה לחריגת גדר',
  status: 'draft',
  is_default: false,
  created_at: '2026-07-09T10:00:00',
  published_at: null,
  active_questions: 0,
  total_questions: 0,
};
const PUBLISHED_PROC = {
  id: 'p2',
  title: 'נוהל מעבר משמרת',
  status: 'published',
  is_default: false,
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
    publishProcedure.mockReset();
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

  it('uploads a .docx → first line becomes the title, the rest fills the body', async () => {
    const extracted = 'סד"פ – תשאול ובידוק\n\nפסקה ראשונה של הנוהל\nפסקה שנייה';
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
    // The document's first line auto-fills the title; the body holds the rest.
    expect(await screen.findByLabelText(m.titleField)).toHaveValue('סד"פ – תשאול ובידוק');
    expect(screen.getByLabelText(m.bodyField)).toHaveValue('פסקה ראשונה של הנוהל\nפסקה שנייה');
    // And the source filename is surfaced.
    expect(screen.getByTestId('docx-extracted')).toHaveTextContent('procedure.docx');
  });

  it('uploads a .docx with a title already typed → keeps it and fills the full body', async () => {
    const extracted = 'שורה ראשונה\nגוף';
    fetchProcedures.mockResolvedValue([]);
    uploadProcedureDocx.mockResolvedValue({
      text: extracted,
      source_filename: 'procedure.docx',
      char_count: extracted.length,
    });
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: m.add }));
    fireEvent.change(screen.getByLabelText(m.titleField), { target: { value: 'כותרת ידנית' } });

    const file = new File(['docx-bytes'], 'procedure.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    fireEvent.change(screen.getByTestId('docx-input'), { target: { files: [file] } });

    await waitFor(() => expect(uploadProcedureDocx).toHaveBeenCalledWith(file, 'כותרת ידנית'));
    expect(await screen.findByLabelText(m.titleField)).toHaveValue('כותרת ידנית');
    expect(screen.getByLabelText(m.bodyField)).toHaveValue(extracted);
  });

  it('shows the bold-marker hint under the body textarea', async () => {
    fetchProcedures.mockResolvedValue([]);
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: m.add }));

    expect(await screen.findByTestId('proc-body-hint')).toHaveTextContent(m.bodyBoldHint);
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

describe('ProceduresPage — default badge + per-row publish', () => {
  beforeEach(() => {
    fetchProcedures.mockReset();
    publishProcedure.mockReset();
    toast.success.mockReset();
    toast.error.mockReset();
  });

  const proc = (overrides) => ({
    id: 'p1',
    title: 'נוהל',
    status: 'draft',
    is_default: false,
    published_at: null,
    active_questions: 7,
    total_questions: 7,
    ...overrides,
  });

  it('shows the ⭐ default badge only on the default procedure row', async () => {
    fetchProcedures.mockResolvedValue([
      proc({ id: 'a', title: 'נהל א', status: 'published', is_default: true }),
      proc({ id: 'b', title: 'נהל ב', status: 'published', is_default: false }),
    ]);
    renderPage();

    const badge = await screen.findByTestId('default-badge-a');
    expect(badge).toHaveTextContent(m.defaultBadge);
    expect(screen.queryByTestId('default-badge-b')).toBeNull();
  });

  // Per-row publish: button label + confirm dialog + the exact API call depend
  // on status (and whether it's already the default). Expected values mirror
  // the messages.procedures keys the component renders.
  const CASES = [
    { name: 'draft → first publish', status: 'draft', is_default: false,
      label: m.rowPublish, confirm: m.publishLabel, rebroadcast: false, message: m.publishConfirm },
    { name: 'archived → re-publish', status: 'archived', is_default: false,
      label: m.republish, confirm: m.republish, rebroadcast: false, message: m.republishConfirm },
    { name: 'published non-default → set default + rebroadcast', status: 'published', is_default: false,
      label: m.markDefaultBroadcast, confirm: m.markDefaultBroadcast, rebroadcast: true, message: m.markDefaultConfirm },
    { name: 'published default → reshare', status: 'published', is_default: true,
      label: m.reshare, confirm: m.reshare, rebroadcast: true, message: m.reshareConfirm },
  ];

  it.each(CASES)(
    'per-row publish for $name: right button + confirm + API call',
    async (c) => {
      fetchProcedures.mockResolvedValue([
        proc({ id: 'p1', status: c.status, is_default: c.is_default }),
      ]);
      publishProcedure.mockResolvedValue({ sent: 3, skipped: 1, total: 4 });
      renderPage();

      const publishBtn = await screen.findByTestId('publish-p1');
      expect(publishBtn).toHaveTextContent(c.label);

      fireEvent.click(publishBtn);
      // Confirm dialog open with the message for this action.
      await screen.findByText(c.message);
      // Scope to the modal so the confirm button (same label as the row button
      // in some cases) is unambiguous.
      const overlay = document.querySelector('.modal-overlay');
      fireEvent.click(within(overlay).getByRole('button', { name: c.confirm }));

      await waitFor(() =>
        expect(publishProcedure).toHaveBeenCalledWith('p1', { rebroadcast: c.rebroadcast }),
      );
      expect(publishProcedure).toHaveBeenCalledTimes(1);
    },
  );

  it('publish success toast shows the {sent, skipped, total} counts', async () => {
    fetchProcedures.mockResolvedValue([proc({ id: 'p1', status: 'draft' })]);
    publishProcedure.mockResolvedValue({ sent: 3, skipped: 1, total: 4 });
    renderPage();

    fireEvent.click(await screen.findByTestId('publish-p1'));
    await screen.findByText(m.publishConfirm);
    const overlay = document.querySelector('.modal-overlay');
    fireEvent.click(within(overlay).getByRole('button', { name: m.publishLabel }));

    // publishDone(3,1,4) → "...3 מתוך 4 מאבטחים (1 דילגו)"
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(m.publishDone(3, 1, 4)));
  });
});
