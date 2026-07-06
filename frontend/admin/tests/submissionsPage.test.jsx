import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/hooks/useWeeks', () => ({ useWeeks: vi.fn() }));
vi.mock('../src/hooks/useSubmissions', () => ({ useSubmissions: vi.fn() }));
vi.mock('../src/components/Toast', () => ({ useToast: () => vi.fn() }));
vi.mock('../src/api/adminApiClient', () => ({
  sendWeekReminders: vi.fn(),
  fetchConstraintRules: vi.fn().mockResolvedValue(null),
}));

import { useWeeks } from '../src/hooks/useWeeks';
import { useSubmissions } from '../src/hooks/useSubmissions';
import SubmissionsPage from '../src/pages/SubmissionsPage';
import messages from '../src/utils/messages';

const submissions = [
  { user_id: 'g1', full_name: 'בובי ביטון', submitted_at: '2026-06-13T15:20:12' },
];

// The upcoming Sunday (strictly future) — the week the schedule board targets
// and, now, the reports page's default. Mirrors SubmissionsPage.upcomingSundayIso.
function upcomingSundayIso(now = new Date()) {
  const daysAhead = (7 - now.getDay()) % 7 || 7;
  const sun = new Date(now.getFullYear(), now.getMonth(), now.getDate() + daysAhead);
  const pad = (n) => String(n).padStart(2, '0');
  return `${sun.getFullYear()}-${pad(sun.getMonth() + 1)}-${pad(sun.getDate())}`;
}

function setup(weekStatus, startDate = '2026-06-14') {
  const week = { id: 1, status: weekStatus, week_label: 'שבוע 24', start_date: startDate };
  useWeeks.mockReturnValue({ weeks: [week], loading: false });
  useSubmissions.mockReturnValue({
    submissions,
    detailedData: { submitted: [], pending: [] },
    loading: false,
  });
  render(
    <MemoryRouter>
      <SubmissionsPage />
    </MemoryRouter>,
  );
}

describe('SubmissionsPage — admin fill-constraints gating by week status', () => {
  beforeEach(() => {
    useWeeks.mockReset();
    useSubmissions.mockReset();
  });

  // The week selector auto-defaults only to an 'open' week, so for non-open
  // statuses we pick the week explicitly via the <select>.
  function selectWeek() {
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
  }

  it('shows the fill-constraints button when the week is closed (admin may edit on behalf)', () => {
    setup('closed');
    selectWeek();
    expect(
      screen.getByRole('button', { name: messages.guards.fillConstraints }),
    ).toBeInTheDocument();
  });

  it('shows the fill-constraints button when the week is open', () => {
    setup('open');
    // 'open' auto-selects, no manual pick needed.
    expect(
      screen.getByRole('button', { name: messages.guards.fillConstraints }),
    ).toBeInTheDocument();
  });

  it('hides the fill-constraints button once the week is locked (final)', () => {
    setup('locked');
    selectWeek();
    expect(
      screen.queryByRole('button', { name: messages.guards.fillConstraints }),
    ).not.toBeInTheDocument();
  });

  // The default now tracks the schedule board's week (upcoming Sun→Sat), so a
  // closed board week auto-selects without a manual pick — no "choose week"
  // prompt is shown even though the week isn't 'open'.
  it('auto-selects the board week even when it is closed', () => {
    setup('closed', upcomingSundayIso());
    expect(screen.queryByText(messages.submissions.selectWeekPrompt)).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: messages.guards.fillConstraints }),
    ).toBeInTheDocument();
  });

  it('filters the submission rows by guard name', () => {
    const week = { id: 1, status: 'open', week_label: 'שבוע 24', start_date: '2026-06-14' };
    useWeeks.mockReturnValue({ weeks: [week], loading: false });
    useSubmissions.mockReturnValue({
      submissions: [
        { user_id: 'g1', full_name: 'בובי ביטון', submitted_at: '2026-06-13T15:20:12' },
        { user_id: 'g2', full_name: 'דנה לוי', submitted_at: null },
      ],
      detailedData: { submitted: [], pending: [] },
      loading: false,
    });
    render(
      <MemoryRouter>
        <SubmissionsPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'בובי' } });
    expect(screen.getByText('בובי ביטון')).toBeInTheDocument();
    expect(screen.queryByText('דנה לוי')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'רפאל' } });
    expect(screen.getByText(messages.common.noSearchResults)).toBeInTheDocument();
  });
});

describe('SubmissionsPage — ?week= deep link (from a week card)', () => {
  beforeEach(() => {
    useWeeks.mockReset();
    useSubmissions.mockReset();
  });

  function setupTwoWeeks(initialEntry) {
    useWeeks.mockReturnValue({
      weeks: [
        { id: 1, status: 'open', week_label: 'שבוע 24', start_date: '2026-06-14' },
        { id: 2, status: 'closed', week_label: 'שבוע 25', start_date: '2026-06-21' },
      ],
      loading: false,
    });
    useSubmissions.mockReturnValue({
      submissions,
      detailedData: { submitted: [], pending: [] },
      loading: false,
    });
    render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <SubmissionsPage />
      </MemoryRouter>,
    );
  }

  it('preselects the week from ?week= (beats the default)', () => {
    setupTwoWeeks('/submissions?week=2');
    expect(screen.getByRole('combobox')).toHaveValue('2');
  });

  it('falls back to the default when ?week= is unknown', () => {
    // Unknown id → the open week (default fallback) wins.
    setupTwoWeeks('/submissions?week=does-not-exist');
    expect(screen.getByRole('combobox')).toHaveValue('1');
  });
});
