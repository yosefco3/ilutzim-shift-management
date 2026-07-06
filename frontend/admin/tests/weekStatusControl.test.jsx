import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import WeekStatusControl, { WeekStatusBadge } from '../src/components/WeekStatusControl';

const noop = vi.fn();

function renderWeek(
  status, handlers = {}, auto = {}, isCurrent = true,
  isOpenTarget = status === 'closed', publishedAt = null,
) {
  return render(
    <WeekStatusControl
      week={{ id: 'w1', status, published_at: publishedAt }}
      onOpen={handlers.onOpen || noop}
      onLock={handlers.onLock || noop}
      onPublish={handlers.onPublish || noop}
      loading={false}
      autoOpen={auto.autoOpen || { enabled: false }}
      autoLock={auto.autoLock || { enabled: false }}
      isCurrent={isCurrent}
      isOpenTarget={isOpenTarget}
    />,
  );
}

describe('WeekStatusControl', () => {
  it('never shows a delete button — removed to prevent accidental data loss', () => {
    for (const status of ['closed', 'open', 'locked']) {
      const { unmount } = renderWeek(status);
      expect(screen.queryByText(/מחק/)).not.toBeInTheDocument();
      unmount();
    }
  });

  it('offers "open for submission" on the upcoming fresh (open-target) week', () => {
    renderWeek('closed');  // isOpenTarget defaults true for closed here
    expect(screen.getByText(/פתח להגשה/)).toBeInTheDocument();
  });

  it('does NOT offer "open" on a closed week that is not the open-target', () => {
    // e.g. an old CLOSED week that already ran its window (opened_at set), or when
    // another week is already OPEN — the parent computes isOpenTarget=false.
    renderWeek('closed', {}, {}, false, false);
    expect(screen.queryByText(/פתח להגשה/)).not.toBeInTheDocument();
  });

  it('never offers "open"/reopen on a LOCKED week', () => {
    renderWeek('locked', {}, {}, true, false);
    expect(screen.queryByText(/פתח להגשה/)).not.toBeInTheDocument();
  });

  it('badge does not crash on an unknown status (falls back to closed)', () => {
    render(<WeekStatusBadge status="something-weird" />);
    expect(screen.getByText(/סגור/)).toBeInTheDocument();
  });

  it('badge shows the right label per status', () => {
    const { unmount } = render(<WeekStatusBadge status="open" />);
    expect(screen.getByText(/פתוח להגשה/)).toBeInTheDocument();
    unmount();
    render(<WeekStatusBadge status="locked" />);
    expect(screen.getByText(/נעול/)).toBeInTheDocument();
  });

  // ── PUBLISH button (📢) — visible on the current CLOSED week that was never
  // published. Publishing keeps the week CLOSED (never locks) and, via
  // WeeksPage.handlePublish, snapshots the built schedule so it stays
  // downloadable. ────────────────────────────────────────────────────────────
  it('does not publish immediately — asks for confirmation first', () => {
    const onPublish = vi.fn();
    renderWeek('closed', { onPublish });  // publish lives on the current CLOSED week

    // Clicking "פרסם" opens a confirm dialog instead of publishing right away.
    fireEvent.click(screen.getByText(/📢/));
    expect(onPublish).not.toHaveBeenCalled();
    // The confirm explains the week stays CLOSED and can be published again.
    expect(screen.getByText(/יישאר במצב/)).toBeInTheDocument();
  });

  it('publishes only after confirming the irreversible warning', () => {
    const onPublish = vi.fn();
    renderWeek('closed', { onPublish });

    fireEvent.click(screen.getByText(/📢/));
    fireEvent.click(screen.getByText('כן, פרסם'));
    expect(onPublish).toHaveBeenCalledWith('w1');
  });

  it('cancelling the publish confirm does not publish', () => {
    const onPublish = vi.fn();
    renderWeek('closed', { onPublish });

    fireEvent.click(screen.getByText(/📢/));
    fireEvent.click(screen.getByRole('button', { name: 'ביטול' }));
    expect(onPublish).not.toHaveBeenCalled();
  });

  // ── automation gating ──────────────────────────────────────────────────────

  it('hides "open for submission" and shows an indicator when auto-open is on', () => {
    renderWeek('closed', {}, { autoOpen: { enabled: true, weekday: 'sunday', time: '07:00' } });
    expect(screen.queryByText(/פתח להגשה/)).not.toBeInTheDocument();
    expect(screen.getByText(/תיפתח אוטומטית/)).toBeInTheDocument();
    expect(screen.getByText(/ראשון 07:00/)).toBeInTheDocument();
  });

  it('hides "lock" and shows an indicator on an open week when auto-lock is on', () => {
    renderWeek('open', {}, { autoLock: { enabled: true, weekday: 'wednesday', time: '12:00' } });
    expect(screen.queryByText(/^נעל$/)).not.toBeInTheDocument();
    expect(screen.getByText(/תינעל אוטומטית/)).toBeInTheDocument();
    expect(screen.getByText(/רביעי 12:00/)).toBeInTheDocument();
  });

  it('keeps the manual buttons when both switches are off', () => {
    const { unmount } = renderWeek('closed');
    expect(screen.getByText(/פתח להגשה/)).toBeInTheDocument();
    unmount();
    renderWeek('open');
    expect(screen.getByText(/סגור להגשה/)).toBeInTheDocument();
  });

  it('hides the manual open button on a closed week when auto-open is on', () => {
    renderWeek(
      'closed',
      {},
      { autoOpen: { enabled: true, weekday: 'sunday', time: '07:00' },
        autoLock: { enabled: true, weekday: 'wednesday', time: '12:00' } },
    );
    // The manual open button is hidden when auto-open is on. (Publish stays
    // visible on closed weeks regardless of automation.)
    expect(screen.queryByText(/פתח להגשה/)).not.toBeInTheDocument();
  });

  it('shows no action buttons on a non-current LOCKED (history) week', () => {
    renderWeek('locked', {}, {}, false);  // history week — no longer current
    expect(screen.queryByText(/📢/)).not.toBeInTheDocument();   // no publish
    expect(screen.queryByText(/🔄/)).not.toBeInTheDocument();   // no re-publish
    expect(screen.queryByText(/פתח להגשה/)).not.toBeInTheDocument();  // no reopen
    expect(screen.queryByText(/סגור להגשה/)).not.toBeInTheDocument();  // no close
  });

  // ── publish gated to the current week + re-publish once published_at is set ──
  it('hides the publish button on a non-current CLOSED week', () => {
    renderWeek('closed', {}, {}, false);
    expect(screen.queryByText(/📢/)).not.toBeInTheDocument();
  });

  it('shows "publish" (not re-publish) on a current CLOSED week never published', () => {
    renderWeek('closed', {}, {}, true, false, null);  // published_at = null
    expect(screen.getByText(/📢/)).toBeInTheDocument();
    expect(screen.queryByText(/🔄/)).not.toBeInTheDocument();
  });

  it('offers "re-publish" on a current CLOSED week already published, confirms first', () => {
    const onPublish = vi.fn();
    // published_at set → the week was already broadcast, still CLOSED (publish
    // never locks), so the button becomes 🔄 re-publish.
    renderWeek('closed', { onPublish }, {}, true, false, '2026-07-03T09:00:00');

    expect(screen.queryByText(/📢/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/🔄/));
    expect(onPublish).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('כן, פרסם מחדש'));
    expect(onPublish).toHaveBeenCalledWith('w1');
  });

  it('shows no publish/re-publish on a LOCKED week (rollover, terminal)', () => {
    renderWeek('locked', {}, {}, true, false);
    expect(screen.queryByText(/📢/)).not.toBeInTheDocument();
    expect(screen.queryByText(/🔄/)).not.toBeInTheDocument();
  });
});
