import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

vi.mock('../src/api/adminApiClient', () => ({
  fetchProcedure: vi.fn(),
  addProcedureQuestion: vi.fn(),
  updateProcedureQuestion: vi.fn(),
  deleteProcedureQuestion: vi.fn(),
  generateProcedureQuestions: vi.fn(),
  publishProcedure: vi.fn(),
  fetchProcedureResults: vi.fn(),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import {
  fetchProcedure,
  addProcedureQuestion,
  updateProcedureQuestion,
  deleteProcedureQuestion,
  generateProcedureQuestions,
  publishProcedure,
  fetchProcedureResults,
} from '../src/api/adminApiClient';
import ProcedureDetailPage from '../src/pages/ProcedureDetailPage';
import messages from '../src/utils/messages';

const m = messages.procedures;

const DRAFT_PROC = {
  id: 'p1',
  title: 'נוהל טיוטה',
  body_text: 'גוף הנוהל לבדיקה',
  status: 'draft',
  created_at: '2026-07-09T10:00:00',
  published_at: null,
  questions: [
    {
      id: 'q1',
      text: 'מה עושים כשהגדר מתריעה?',
      options: ['מזעיקים מוקד', 'מתעלמים', 'בורחים'],
      correct_index: 0,
      display_order: 0,
      is_active: true,
      source: 'ai',
      edited_at: null,
    },
  ],
};

const PUBLISHED_PROC = {
  ...DRAFT_PROC,
  id: 'p2',
  title: 'נוהל מפורסם',
  status: 'published',
  published_at: '2026-07-02T10:00:00',
};

// Draft whose only question is manual — the AI-generate button should still be
// offered (no AI bank exists yet).
const DRAFT_NO_AI = {
  ...DRAFT_PROC,
  questions: [{ ...DRAFT_PROC.questions[0], source: 'manual' }],
};

function renderPage(initial = '/procedures/p1') {
  // Render inside the real route so useParams() resolves :id (mirrors production;
  // without a <Route> the page would read id=null).
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/procedures/:id" element={<ProcedureDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProcedureDetailPage — questions editor', () => {
  beforeEach(() => {
    fetchProcedure.mockReset();
    addProcedureQuestion.mockReset();
    updateProcedureQuestion.mockReset();
    deleteProcedureQuestion.mockReset();
    generateProcedureQuestions.mockReset();
    publishProcedure.mockReset();
    fetchProcedureResults.mockReset();
    toast.success.mockReset();
    toast.error.mockReset();
  });

  it('draft shows an AI-generate button that generates and reloads', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_NO_AI);
    generateProcedureQuestions.mockResolvedValue({
      generated: 16, skipped: 0, total_questions: 17,
    });
    renderPage();
    await screen.findByText('גוף הנוהל לבדיקה');

    fireEvent.click(screen.getByTestId('generate-ai-btn'));
    await waitFor(() => expect(generateProcedureQuestions).toHaveBeenCalledWith('p1'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(m.generateDone(16)));
    // Reloaded after generation (initial load + reload).
    expect(fetchProcedure).toHaveBeenCalledTimes(2);
  });

  it('AI-generate 503 surfaces the unavailable message; no button on published', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_NO_AI);
    const err = new Error('boom');
    err.status = 503;
    generateProcedureQuestions.mockRejectedValue(err);
    renderPage();
    await screen.findByText('גוף הנוהל לבדיקה');

    fireEvent.click(screen.getByTestId('generate-ai-btn'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(m.errGenerateUnavailable),
    );
  });

  it('draft with an existing AI bank hides the generate button', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC); // its question has source 'ai'
    renderPage();
    await screen.findByText('גוף הנוהל לבדיקה');
    expect(screen.queryByTestId('generate-ai-btn')).toBeNull();
  });

  it('published procedure has no AI-generate button', async () => {
    fetchProcedure.mockResolvedValue(PUBLISHED_PROC);
    renderPage('/procedures/p2');
    await screen.findByText('גוף הנוהל לבדיקה');
    expect(screen.queryByTestId('generate-ai-btn')).toBeNull();
  });

  it('shows the quiz-window deadline on a published procedure', async () => {
    // [quiz_availability_window EDGE U2]
    fetchProcedure.mockResolvedValue({
      ...PUBLISHED_PROC,
      quiz_open: true,
      quiz_deadline_at: '2026-07-05T10:00:00',
    });
    renderPage('/procedures/p2');
    await screen.findByText('נוהל מפורסם');
    expect(screen.getByTestId('quiz-window-info')).toHaveTextContent('המבחן פתוח עד');
  });

  it('shows the closed hint when the quiz window expired', async () => {
    fetchProcedure.mockResolvedValue({
      ...PUBLISHED_PROC,
      quiz_open: false,
      quiz_deadline_at: '2026-07-03T10:00:00',
    });
    renderPage('/procedures/p2');
    await screen.findByText('נוהל מפורסם');
    expect(screen.getByTestId('quiz-window-info')).toHaveTextContent(m.quizClosedHint);
  });

  it('shows no window info without a deadline (unlimited setting)', async () => {
    fetchProcedure.mockResolvedValue(PUBLISHED_PROC); // no quiz_deadline_at
    renderPage('/procedures/p2');
    await screen.findByText('נוהל מפורסם');
    expect(screen.queryByTestId('quiz-window-info')).toBeNull();
  });

  it('renders the body text + existing questions with the correct option marked', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    renderPage();

    expect(await screen.findByText('גוף הנוהל לבדיקה')).toBeInTheDocument();
    expect(screen.getByText(/מה עושים כשהגדר מתריעה/)).toBeInTheDocument();
    // Correct option (index 0) is marked with ✓.
    expect(screen.getByTestId('option-0')).toHaveTextContent('✓');
    expect(screen.getByTestId('option-0')).toHaveTextContent('מזעיקים מוקד');
  });

  it('shows delete for draft questions and hides it after publish', async () => {
    // Draft: delete button present.
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    renderPage();
    expect(await screen.findByTestId('delete-q1')).toBeInTheDocument();
  });

  it('hides the delete button for a published procedure (disable instead)', async () => {
    fetchProcedure.mockResolvedValue(PUBLISHED_PROC);
    renderPage();
    await screen.findByText('נוהל מפורסם');
    expect(screen.queryByTestId('delete-q1')).toBeNull();
    // Publish button gone; rebroadcast button shown instead.
    expect(screen.queryByTestId('publish-btn')).toBeNull();
    expect(screen.getByTestId('rebroadcast-btn')).toBeInTheDocument();
    // Disable toggle still available.
    expect(screen.getByTestId('disable-q1')).toBeInTheDocument();
  });

  it('toggles a question active → disable via PATCH', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    updateProcedureQuestion.mockResolvedValue({ ...DRAFT_PROC.questions[0], is_active: false });
    renderPage();
    await screen.findByTestId('disable-q1');

    fireEvent.click(screen.getByTestId('disable-q1'));

    await waitFor(() =>
      expect(updateProcedureQuestion).toHaveBeenCalledWith('p1', 'q1', { is_active: false }),
    );
    expect(toast.success).toHaveBeenCalled();
  });

  it('deletes a draft question after a confirm', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    deleteProcedureQuestion.mockResolvedValue(null);
    renderPage();
    await screen.findByTestId('delete-q1');

    fireEvent.click(screen.getByTestId('delete-q1'));
    // Scope to the modal so we click the confirm button, not the card's own
    // "מחק" button (both share the same label).
    const modal = document.querySelector('.modal-content');
    fireEvent.click(within(modal).getByRole('button', { name: messages.common.delete }));

    await waitFor(() => expect(deleteProcedureQuestion).toHaveBeenCalledWith('p1', 'q1'));
    expect(toast.success).toHaveBeenCalledWith(m.questionDeleted);
  });

  it('adds a manual question with valid input (POST)', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    addProcedureQuestion.mockResolvedValue({ id: 'q2', text: 't', options: ['a', 'b'], correct_index: 0 });
    renderPage();
    await screen.findByTestId('delete-q1');

    fireEvent.click(screen.getByTestId('add-question-btn'));
    fireEvent.change(screen.getByTestId('q-text'), { target: { value: 'שאלה חדשה' } });
    fireEvent.change(screen.getByTestId('option-input-0'), { target: { value: 'תשובה א' } });
    fireEvent.change(screen.getByTestId('option-input-1'), { target: { value: 'תשובה ב' } });
    fireEvent.click(screen.getByTestId('correct-0'));
    fireEvent.click(screen.getByTestId('q-save'));

    await waitFor(() =>
      expect(addProcedureQuestion).toHaveBeenCalledWith('p1', {
        text: 'שאלה חדשה',
        options: ['תשובה א', 'תשובה ב'],
        correct_index: 0,
      }),
    );
    expect(toast.success).toHaveBeenCalledWith(m.questionAdded);
  });

  it('validates: empty text is rejected', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    renderPage();
    await screen.findByTestId('delete-q1');

    fireEvent.click(screen.getByTestId('add-question-btn'));
    fireEvent.change(screen.getByTestId('option-input-0'), { target: { value: 'תשובה א' } });
    fireEvent.change(screen.getByTestId('option-input-1'), { target: { value: 'תשובה ב' } });
    fireEvent.click(screen.getByTestId('q-save'));

    expect(await screen.findByTestId('q-form-error')).toHaveTextContent(m.errQuestionEmpty);
    expect(addProcedureQuestion).not.toHaveBeenCalled();
  });

  it('validates: question text over 300 chars is rejected', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    renderPage();
    await screen.findByTestId('delete-q1');

    fireEvent.click(screen.getByTestId('add-question-btn'));
    fireEvent.change(screen.getByTestId('q-text'), { target: { value: 'א'.repeat(301) } });
    fireEvent.change(screen.getByTestId('option-input-0'), { target: { value: 'תשובה א' } });
    fireEvent.change(screen.getByTestId('option-input-1'), { target: { value: 'תשובה ב' } });
    fireEvent.click(screen.getByTestId('q-save'));

    expect(await screen.findByTestId('q-form-error')).toHaveTextContent(m.errQuestionLong(300));
    expect(addProcedureQuestion).not.toHaveBeenCalled();
  });

  it('validates: an option over 100 chars is rejected', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    renderPage();
    await screen.findByTestId('delete-q1');

    fireEvent.click(screen.getByTestId('add-question-btn'));
    fireEvent.change(screen.getByTestId('q-text'), { target: { value: 'שאלה תקינה' } });
    fireEvent.change(screen.getByTestId('option-input-0'), { target: { value: 'א'.repeat(101) } });
    fireEvent.change(screen.getByTestId('option-input-1'), { target: { value: 'קצרה' } });
    fireEvent.click(screen.getByTestId('correct-0'));
    fireEvent.click(screen.getByTestId('q-save'));

    expect(await screen.findByTestId('q-form-error')).toHaveTextContent(m.errOptionLong(100));
    expect(addProcedureQuestion).not.toHaveBeenCalled();
  });
});

describe('ProcedureDetailPage — back to list', () => {
  beforeEach(() => {
    fetchProcedure.mockReset();
  });

  it('prominent back button navigates to /procedures', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    render(
      <MemoryRouter initialEntries={['/procedures/p1']}>
        <Routes>
          <Route path="/procedures/:id" element={<ProcedureDetailPage />} />
          <Route path="/procedures" element={<div data-testid="procedures-list" />} />
        </Routes>
      </MemoryRouter>,
    );

    const back = await screen.findByTestId('back-to-list');
    expect(back).toHaveTextContent(m.backToList);
    fireEvent.click(back);

    // Navigation actually happened — the /procedures sentinel route rendered.
    expect(await screen.findByTestId('procedures-list')).toBeInTheDocument();
  });
});

describe('ProcedureDetailPage — publish', () => {
  beforeEach(() => {
    fetchProcedure.mockReset();
    publishProcedure.mockReset();
    toast.success.mockReset();
    toast.error.mockReset();
  });

  it('confirms publish with a broadcast warning and shows sent/total counts', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    publishProcedure.mockResolvedValue({ sent: 5, skipped: 1, total: 6, republished: false });
    renderPage();
    await screen.findByTestId('publish-btn');

    fireEvent.click(screen.getByTestId('publish-btn'));
    // Confirm dialog warns about broadcasting to all guards.
    expect(await screen.findByText(/ישודר לכל המאבטחים בטלגרם/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: m.publishLabel }));

    await waitFor(() => expect(publishProcedure).toHaveBeenCalledWith('p1', { rebroadcast: false }));
    expect(toast.success).toHaveBeenCalledWith(m.publishDone(5, 1, 6));
  });

  it('on 409 offers a rebroadcast that skips guards who passed', async () => {
    fetchProcedure.mockResolvedValue(DRAFT_PROC);
    publishProcedure.mockImplementation((_pid, opts = {}) =>
      opts.rebroadcast
        ? Promise.resolve({ sent: 3, skipped: 2, total: 5, republished: true })
        : Promise.reject(Object.assign(new Error('הנוהל כבר פורסם'), { status: 409 })),
    );
    renderPage();
    await screen.findByTestId('publish-btn');

    // First publish attempt (no rebroadcast) → 409.
    fireEvent.click(screen.getByTestId('publish-btn'));
    fireEvent.click(await screen.findByRole('button', { name: m.publishLabel }));

    // 409 → rebroadcast offer appears.
    expect(await screen.findByText(m.publishAlreadyMsg)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: m.rebroadcastLabel }));

    await waitFor(() => expect(publishProcedure).toHaveBeenNthCalledWith(2, 'p1', { rebroadcast: true }));
    expect(toast.success).toHaveBeenCalledWith(m.rebroadcastDone(3, 2, 5));
  });
});

describe('ProcedureDetailPage — results', () => {
  beforeEach(() => {
    fetchProcedure.mockReset();
    fetchProcedureResults.mockReset();
  });

  it('renders per-guard status buckets with red styling for not-passed', async () => {
    fetchProcedure.mockResolvedValue(PUBLISHED_PROC);
    fetchProcedureResults.mockResolvedValue([
      { user_id: 'u1', user_name: 'דנה', status: 'passed', attempts: 1, best_score: 90, passed: true },
      { user_id: 'u2', user_name: 'אבי', status: 'failed', attempts: 2, best_score: 60, passed: false },
      { user_id: 'u3', user_name: 'כרמל', status: 'in_progress', attempts: 1, best_score: null, passed: null },
      { user_id: 'u4', user_name: 'רון', status: 'not_started', attempts: 0, best_score: null, passed: null },
    ]);
    renderPage();
    await screen.findByText('נוהל מפורסם');

    fireEvent.click(screen.getByRole('button', { name: new RegExp(m.tabsResults) }));

    expect(await screen.findByTestId('results-table')).toBeInTheDocument();
    // All four status labels appear.
    expect(screen.getByText(m.statusPassed)).toBeInTheDocument();
    expect(screen.getAllByText(m.statusFailed).length).toBeGreaterThan(0);
    expect(screen.getByText(m.statusInProgress)).toBeInTheDocument();
    expect(screen.getByText(m.statusNotStarted)).toBeInTheDocument();
    // Attempts + best score rendered.
    expect(screen.getByText('90%')).toBeInTheDocument();
    // Failed row is tinted red (red styling for not-passed).
    const failedRow = screen.getByTestId('result-row-u2');
    expect(failedRow.className).toBe(''); // no class; style is inline
    expect(failedRow.style.background).toBe('var(--danger-soft)');
    // Not-started row is also tinted (not passed).
    expect(screen.getByTestId('result-row-u4').style.background).toBe('var(--danger-soft)');
    // Passed row is not tinted.
    expect(screen.getByTestId('result-row-u1').style.background).toBe('');
  });

  it('shows the empty state when there are no results', async () => {
    fetchProcedure.mockResolvedValue(PUBLISHED_PROC);
    fetchProcedureResults.mockResolvedValue([]);
    renderPage();
    await screen.findByText('נוהל מפורסם');
    fireEvent.click(screen.getByRole('button', { name: new RegExp(m.tabsResults) }));
    expect(await screen.findByText(m.noResults)).toBeInTheDocument();
  });

  it('renders the קרא column: ✓+date when read, — when not', async () => {
    fetchProcedure.mockResolvedValue(PUBLISHED_PROC);
    fetchProcedureResults.mockResolvedValue([
      { user_id: 'u1', user_name: 'דנה', status: 'passed', attempts: 1, best_score: 90, passed: true,
        read: true, first_read_at: '2026-07-18T09:30:00' },
      { user_id: 'u2', user_name: 'אבי', status: 'not_started', attempts: 0, best_score: null, passed: null,
        read: false, first_read_at: null },
    ]);
    renderPage();
    await screen.findByText('נוהל מפורסם');
    fireEvent.click(screen.getByRole('button', { name: new RegExp(m.tabsResults) }));
    await screen.findByTestId('results-table');

    const readCell = screen.getByTestId('read-cell-u1');
    expect(readCell.textContent).toContain(m.readYes); // ✓
    // unread guard → dash
    expect(screen.getByTestId('read-cell-u2').textContent.trim()).toBe(m.readNo);
  });
});

