import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const closeSpy = vi.fn();

vi.mock('../src/api/guardApiClient', () => ({
  getProcedure: vi.fn(),
  startProcedureQuiz: vi.fn(),
}));

vi.mock('../src/hooks/useTelegram', () => ({
  useTelegram: () => ({
    initData: '__DEV_MODE__',
    isDevMode: true,
    user: { id: 'dev-user' },
    close: closeSpy,
    webApp: null,
  }),
}));

import { getProcedure, startProcedureQuiz } from '../src/api/guardApiClient';
import ProcedureViewPage from '../src/pages/ProcedureViewPage';

function renderPage(procedureId = 'p1') {
  return render(
    <MemoryRouter initialEntries={[`/procedure/${procedureId}`]}>
      <Routes>
        <Route path="/procedure/:procedureId" element={<ProcedureViewPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProcedureViewPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // The page calls window.Telegram.WebApp.close() on quiz success.
    window.Telegram = { WebApp: { close: closeSpy } };
  });
  afterEach(() => {
    delete window.Telegram;
  });

  it('renders the sanitized body_html (heading + bold nodes)', async () => {
    getProcedure.mockResolvedValue({
      data: {
        id: 'p1',
        title: 'נוהל כניסה',
        body_html: '<h1>כותרת ראשית</h1><p>טקסט עם <strong>מילה מודגשת</strong></p>',
        body_text: 'תוכן',
        is_default: false,
        passed: false,
      },
      error: null,
      status: 200,
    });
    renderPage();
    await screen.findByRole('heading', { name: 'כותרת ראשית' });
    expect(screen.getByText('מילה מודגשת').tagName).toBe('STRONG');
    expect(screen.getByRole('heading', { name: 'נוהל כניסה' })).toBeInTheDocument();
  });

  it('falls back to body_text paragraphs + <strong> from *bold* when no body_html', async () => {
    // [EDGE D2]
    getProcedure.mockResolvedValue({
      data: {
        id: 'p1',
        title: 'נוהל',
        body_html: null,
        body_text: 'פסקה ראשונה\nפסקה *מודגשת* שנייה',
        is_default: false,
        passed: false,
      },
      error: null,
      status: 200,
    });
    const { container } = renderPage();
    await screen.findByText('פסקה ראשונה');
    const strongs = container.querySelectorAll('strong');
    expect(strongs.length).toBe(1);
    expect(strongs[0].textContent).toBe('מודגשת');
    // two paragraphs (one per non-empty line)
    expect(container.querySelectorAll('.procedure-body p').length).toBe(2);
  });

  it('shows the passed badge when passed', async () => {
    getProcedure.mockResolvedValue({
      data: {
        id: 'p1', title: 'נוהל', body_html: '<p>x</p>', body_text: 'x',
        is_default: false, passed: true,
      },
      error: null, status: 200,
    });
    renderPage();
    await screen.findByText('✅ עברת את המבחן');
  });

  it('starts the quiz, shows the success text, and closes the WebApp', async () => {
    getProcedure.mockResolvedValue({
      data: {
        id: 'p1', title: 'נוהל', body_html: '<p>x</p>', body_text: 'x',
        is_default: false, passed: false,
      },
      error: null, status: 200,
    });
    startProcedureQuiz.mockResolvedValue({ data: { started: true }, error: null, status: 200 });
    renderPage();
    const btn = await screen.findByRole('button', { name: '▶️ התחל מבחן' });
    fireEvent.click(btn);
    await screen.findByText("המבחן נשלח לצ'אט");
    expect(startProcedureQuiz).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(closeSpy).toHaveBeenCalled());
  });

  it('renders the 401 screen (open via the bot)', async () => {
    // [EDGE A1]
    getProcedure.mockResolvedValue({ data: null, error: 'auth', status: 401 });
    renderPage();
    await screen.findByText('יש לפתוח את הנוהל מתוך הבוט בטלגרם');
  });

  it('renders the 404 screen (no longer available)', async () => {
    // [EDGE D1]
    getProcedure.mockResolvedValue({ data: null, error: 'gone', status: 404 });
    renderPage();
    await screen.findByText('הנוהל אינו זמין יותר');
  });

  it('renders the 503 bot-down screen on quiz start and stays open', async () => {
    // [EDGE I1]
    getProcedure.mockResolvedValue({
      data: {
        id: 'p1', title: 'נוהל', body_html: '<p>x</p>', body_text: 'x',
        is_default: false, passed: false,
      },
      error: null, status: 200,
    });
    startProcedureQuiz.mockResolvedValue({ data: null, error: 'down', status: 503 });
    renderPage();
    const btn = await screen.findByRole('button', { name: '▶️ התחל מבחן' });
    fireEvent.click(btn);
    await screen.findByText('הבוט אינו זמין כרגע — נסו שוב בעוד רגע');
    // page stays open → the button is available again
    expect(screen.getByRole('button', { name: '▶️ התחל מבחן' })).toBeInTheDocument();
    expect(closeSpy).not.toHaveBeenCalled();
  });

  it('ignores a double-click (one API call) while the request is pending', async () => {
    // [EDGE C2]
    getProcedure.mockResolvedValue({
      data: {
        id: 'p1', title: 'נוהל', body_html: '<p>x</p>', body_text: 'x',
        is_default: false, passed: false,
      },
      error: null, status: 200,
    });
    let resolveQuiz;
    startProcedureQuiz.mockReturnValue(
      new Promise((resolve) => {
        resolveQuiz = resolve;
      }),
    );
    renderPage();
    const btn = await screen.findByRole('button', { name: '▶️ התחל מבחן' });
    fireEvent.click(btn);
    fireEvent.click(btn); // second tap while pending → ignored
    expect(startProcedureQuiz).toHaveBeenCalledTimes(1);
    // the button is disabled (shows the sending label) while in flight
    expect(screen.getByRole('button', { name: 'שולח...' })).toBeDisabled();
    resolveQuiz({ data: { started: true }, error: null, status: 200 });
    await screen.findByText("המבחן נשלח לצ'אט");
  });

  it('hides the start button and shows the closed note when quiz_open=false', async () => {
    // Availability window closed: reading stays, only the quiz is blocked.
    // [quiz_availability_window EDGE U1]
    getProcedure.mockResolvedValue({
      data: {
        id: 'p1', title: 'נוהל', body_html: '<p>תוכן הנוהל</p>', body_text: 'x',
        is_default: false, passed: false, quiz_open: false,
      },
      error: null, status: 200,
    });
    renderPage();
    await screen.findByText('המבחן כבר לא זמין — חלון הזמן לביצועו הסתיים');
    expect(screen.getByText('תוכן הנוהל')).toBeInTheDocument(); // reading intact
    expect(
      screen.queryByRole('button', { name: '▶️ התחל מבחן' }),
    ).not.toBeInTheDocument();
    expect(startProcedureQuiz).not.toHaveBeenCalled();
  });

  it('still shows the start button when quiz_open is true or absent', async () => {
    // Backward compat: an older payload without quiz_open behaves as open.
    getProcedure.mockResolvedValue({
      data: {
        id: 'p1', title: 'נוהל', body_html: '<p>x</p>', body_text: 'x',
        is_default: false, passed: false,
      },
      error: null, status: 200,
    });
    renderPage();
    expect(
      await screen.findByRole('button', { name: '▶️ התחל מבחן' }),
    ).toBeInTheDocument();
  });
});
