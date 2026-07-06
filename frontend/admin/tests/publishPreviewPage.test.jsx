import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock the weeks hook and the API client so we control both.
vi.mock('../src/hooks/useWeeks', () => ({
  useWeeks: vi.fn(),
}));
vi.mock('../src/api/adminApiClient', () => ({
  previewPublish: vi.fn(),
}));

import { useWeeks } from '../src/hooks/useWeeks';
import { previewPublish } from '../src/api/adminApiClient';
import PublishPreviewPage from '../src/pages/PublishPreviewPage';
import messages from '../src/utils/messages';

function renderPage() {
  return render(
    <MemoryRouter>
      <PublishPreviewPage />
    </MemoryRouter>,
  );
}

describe('PublishPreviewPage', () => {
  beforeEach(() => {
    useWeeks.mockReset();
    previewPublish.mockReset();
    // start_date in the future → this is the upcoming, publishable week.
    useWeeks.mockReturnValue({
      weeks: [{ id: 'week-1', week_label: 'שבוע נוכחי', status: 'closed', start_date: '2999-01-05' }],
      loading: false,
    });
  });

  it('auto-loads the closed week and renders each guard message + send flag', async () => {
    previewPublish.mockResolvedValue([
      {
        user_name: 'אבי כהן', phone_number: '0500000111', telegram_id: '111',
        would_send: true, message: '🗓️ הסידור שלך\nראשון · ארנונה',
      },
      {
        user_name: 'דנה לוי', phone_number: '0500000222', telegram_id: null,
        would_send: false, message: 'לא שובצת השבוע.',
      },
    ]);

    renderPage();

    // Defaults to the 'closed' week → fetches its preview.
    await waitFor(() => expect(previewPublish).toHaveBeenCalledWith('week-1'));

    // Both guards' messages are shown...
    expect(await screen.findByText('אבי כהן')).toBeInTheDocument();
    expect(screen.getByText(/ראשון · ארנונה/)).toBeInTheDocument();
    expect(screen.getByText('דנה לוי')).toBeInTheDocument();

    // ...with the correct will-send / won't-send badges.
    expect(screen.getByText('✅ יישלח בטלגרם')).toBeInTheDocument();
    expect(screen.getByText('🚫 לא יישלח — אין מזהה טלגרם')).toBeInTheDocument();

    // Summary counts only the deliverable guard.
    expect(screen.getByText('1 מתוך 2 מאבטחים יקבלו הודעה')).toBeInTheDocument();
  });

  it('defaults to the upcoming publishable week, not the first closed week in the list', async () => {
    // An OLD closed week sorts first in the (unordered) list, but its schedule was
    // wiped (empty). The preview must default to the UPCOMING closed week instead.
    useWeeks.mockReturnValue({
      weeks: [
        { id: 'old-week', week_label: 'שבוע ישן', status: 'closed', start_date: '2000-01-02' },
        { id: 'next-week', week_label: 'שבוע הבא', status: 'closed', start_date: '2999-01-05' },
      ],
      loading: false,
    });
    previewPublish.mockResolvedValue([
      { user_name: 'אבי כהן', phone_number: '0500000111', telegram_id: '111', would_send: true, message: 'a' },
    ]);

    renderPage();

    // Fetches the upcoming week, NOT the stale old one that happens to be first.
    await waitFor(() => expect(previewPublish).toHaveBeenCalledWith('next-week'));
    expect(previewPublish).not.toHaveBeenCalledWith('old-week');
  });

  it('refetches the preview when the refresh button is clicked', async () => {
    previewPublish
      .mockResolvedValueOnce([
        { user_name: 'אבי כהן', phone_number: '0500000111', telegram_id: '111', would_send: true, message: 'a' },
      ])
      .mockResolvedValueOnce([
        { user_name: 'אבי כהן', phone_number: '0500000111', telegram_id: '111', would_send: true, message: 'a' },
        { user_name: 'דנה לוי', phone_number: '0500000222', telegram_id: '222', would_send: true, message: 'b' },
      ]);

    renderPage();
    expect(await screen.findByText('אבי כהן')).toBeInTheDocument();
    expect(screen.queryByText('דנה לוי')).not.toBeInTheDocument();

    // Manual refresh pulls fresh data for the same week — the new guard appears.
    fireEvent.click(screen.getByRole('button', { name: messages.publishPreview.refresh }));
    expect(await screen.findByText('דנה לוי')).toBeInTheDocument();
    expect(previewPublish).toHaveBeenCalledTimes(2);
  });

  it('auto-refreshes when the window regains focus', async () => {
    previewPublish
      .mockResolvedValueOnce([
        { user_name: 'אבי כהן', phone_number: '0500000111', telegram_id: '111', would_send: true, message: 'a' },
      ])
      .mockResolvedValueOnce([
        { user_name: 'אבי כהן', phone_number: '0500000111', telegram_id: '111', would_send: true, message: 'a' },
        { user_name: 'דנה לוי', phone_number: '0500000222', telegram_id: '222', would_send: true, message: 'b' },
      ]);

    renderPage();
    expect(await screen.findByText('אבי כהן')).toBeInTheDocument();
    expect(screen.queryByText('דנה לוי')).not.toBeInTheDocument();

    // Returning to the tab pulls fresh data on its own.
    fireEvent(window, new Event('focus'));
    expect(await screen.findByText('דנה לוי')).toBeInTheDocument();
    expect(previewPublish).toHaveBeenCalledTimes(2);
  });

  it('shows the empty state when no guards are returned', async () => {
    previewPublish.mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(previewPublish).toHaveBeenCalled());
    expect(await screen.findByText('אין מאבטחים פעילים לשבוע זה.')).toBeInTheDocument();
  });

  it('filters the preview cards by guard name', async () => {
    previewPublish.mockResolvedValue([
      { user_name: 'אבי כהן', phone_number: '0500000111', telegram_id: '111', would_send: true, message: 'a' },
      { user_name: 'דנה לוי', phone_number: '0500000222', telegram_id: '222', would_send: true, message: 'b' },
    ]);
    renderPage();
    expect(await screen.findByText('אבי כהן')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'דנה' } });
    expect(screen.getByText('דנה לוי')).toBeInTheDocument();
    expect(screen.queryByText('אבי כהן')).not.toBeInTheDocument();

    // A name nobody matches shows the no-results notice.
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'רפאל' } });
    expect(screen.getByText(messages.common.noSearchResults)).toBeInTheDocument();
  });
});
