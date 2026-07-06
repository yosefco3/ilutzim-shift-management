import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/hooks/useWeeks', () => ({ useWeeks: vi.fn() }));
vi.mock('../src/hooks/useSettings', () => ({ useSettings: vi.fn() }));
vi.mock('../src/api/builderApiClient', () => ({
  listSavedSchedules: vi.fn(() => Promise.resolve([])),
  downloadSavedSchedule: vi.fn(() => Promise.resolve(new Blob(['x']))),
  saveSchedule: vi.fn(() => Promise.resolve({})),
}));
vi.mock('../src/api/adminApiClient', () => ({
  exportExcel: vi.fn(() => Promise.resolve(new Blob(['xlsx']))),
}));
const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import { useWeeks } from '../src/hooks/useWeeks';
import { useSettings } from '../src/hooks/useSettings';
import WeeksPage from '../src/pages/WeeksPage';
import messages from '../src/utils/messages';

const render = (ui) => rtlRender(<MemoryRouter>{ui}</MemoryRouter>);

const disabledSettings = [
  { key: 'auto_open_enabled', value: 'false' },
  { key: 'auto_lock_enabled', value: 'false' },
];

function mockWeeks(weeks) {
  useWeeks.mockReturnValue({
    weeks,
    loading: false,
    setStatus: vi.fn(),
    openForSubmission: vi.fn(),
    publish: vi.fn(),
  });
}

function cardOf(container, startDate) {
  const card = Array.from(container.querySelectorAll('.week-card'))
    .find((c) => c.textContent.includes(startDate));
  expect(card).toBeTruthy();
  return card;
}

describe('WeeksPage card redesign', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSettings.mockReturnValue({ settings: disabledSettings, loading: false });
  });

  it('marks only the current (publishable) week with the chip + highlight class', () => {
    mockWeeks([
      { id: 'w-old', status: 'closed', start_date: '2020-01-05', end_date: '2020-01-11' },
      { id: 'w-next', status: 'closed', start_date: '2099-01-03', end_date: '2099-01-09' },
    ]);
    const { container } = render(<WeeksPage />);

    const current = cardOf(container, '2099-01-03');
    expect(current.className).toContain('week-card-current');
    expect(within(current).getByText(messages.weeks.currentChip)).toBeInTheDocument();

    const old = cardOf(container, '2020-01-05');
    expect(old.className).not.toContain('week-card-current');
    expect(within(old).queryByText(messages.weeks.currentChip)).toBeNull();
  });

  it('shows the published-at meta line only once the week was published', () => {
    mockWeeks([
      { id: 'w1', status: 'closed', start_date: '2099-01-03', end_date: '2099-01-09', published_at: '2026-07-03T21:15:00' },
    ]);
    render(<WeeksPage />);
    expect(screen.getByText(new RegExp(messages.weeks.lastPublished))).toBeInTheDocument();
  });

  it('hides the published-at meta when never published', () => {
    mockWeeks([
      { id: 'w1', status: 'closed', start_date: '2099-01-03', end_date: '2099-01-09', published_at: null },
    ]);
    render(<WeeksPage />);
    expect(screen.queryByText(new RegExp(messages.weeks.lastPublished))).toBeNull();
  });

  it('renders LOCKED weeks compact: badge + links, no meta and no action buttons', () => {
    mockWeeks([
      { id: 'w-locked', status: 'locked', start_date: '2020-01-05', end_date: '2020-01-11', submission_count: 7, published_at: '2020-01-04T10:00:00' },
    ]);
    const { container } = render(<WeeksPage />);
    const card = cardOf(container, '2020-01-05');
    expect(card.className).toContain('week-card-inactive');
    expect(within(card).getByText(/נעול/)).toBeInTheDocument();
    // Archive card: no submissions meta, no publish/open/close buttons…
    expect(within(card).queryByText(new RegExp(messages.weeks.submissionCount))).toBeNull();
    expect(within(card).queryByText(/📢|🔄|פתח להגשה|סגור להגשה/)).toBeNull();
    // …but the quick links are still there.
    expect(within(card).getByRole('link', { name: new RegExp(messages.weeks.links.submissions) }))
      .toHaveAttribute('href', '/submissions?week=w-locked');
  });

  it('shows the submissions count on active weeks', () => {
    mockWeeks([
      { id: 'w1', status: 'closed', start_date: '2099-01-03', end_date: '2099-01-09', submission_count: 12 },
    ]);
    render(<WeeksPage />);
    expect(screen.getByText(new RegExp(`12 ${messages.weeks.submissionCount}`))).toBeInTheDocument();
  });
});
