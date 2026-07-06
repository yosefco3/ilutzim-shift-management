import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SubmissionForm from '../src/components/guard/SubmissionForm';

// Mock hooks
vi.mock('../src/hooks/useTelegram', () => ({
  useTelegram: () => ({
    initData: 'test-init-data',
    isDevMode: true,
    user: { id: 'dev-user', first_name: 'Dev' },
    mainButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn() },
    close: vi.fn(),
  }),
}));

vi.mock('../src/hooks/useSubmission', () => ({
  useSubmission: vi.fn(),
}));

import { useSubmission } from '../src/hooks/useSubmission';

describe('SubmissionForm', () => {
  it('should show loading state', () => {
    useSubmission.mockReturnValue({
      loading: true,
      days: [],
      isLocked: false,
      weekStatus: null,
      week: null,
      error: null,
      notes: '',
      toggleShift: vi.fn(),
      setShiftHours: vi.fn(),
      setNotes: vi.fn(),
      submit: vi.fn(),
    });

    render(<SubmissionForm />);
    expect(screen.getByText(/טוען/)).toBeInTheDocument();
  });

  it('should show lock banner when week is locked', () => {
    useSubmission.mockReturnValue({
      loading: false,
      days: [],
      isLocked: true,
      weekStatus: 'locked',
      week: { id: 'w1', week_label: 'שבוע 1', status: 'locked' },
      error: null,
      notes: '',
      toggleShift: vi.fn(),
      setShiftHours: vi.fn(),
      setNotes: vi.fn(),
      submit: vi.fn(),
    });

    render(<SubmissionForm />);
    expect(screen.getByText(/נסגרה|לא נפתח|נעול/)).toBeInTheDocument();
  });

  it('should show form with days when week is open', () => {
    useSubmission.mockReturnValue({
      loading: false,
      days: [
        { day_index: 0, blocked: false, shifts: { morning: { active: false, from_hour: '', to_hour: '' }, afternoon: { active: false, from_hour: '', to_hour: '' }, night: { active: false, from_hour: '', to_hour: '' } } },
        { day_index: 1, blocked: false, shifts: { morning: { active: false, from_hour: '', to_hour: '' }, afternoon: { active: false, from_hour: '', to_hour: '' }, night: { active: false, from_hour: '', to_hour: '' } } },
      ],
      isLocked: false,
      weekStatus: 'open',
      week: { id: 'w1', week_label: 'שבוע 1', status: 'open' },
      error: null,
      notes: '',
      toggleShift: vi.fn(),
      setShiftHours: vi.fn(),
      setNotes: vi.fn(),
      submit: vi.fn(),
    });

    render(<SubmissionForm />);
    expect(screen.getByText('יום ראשון')).toBeInTheDocument();
    expect(screen.getByText('יום שני')).toBeInTheDocument();
    expect(screen.getByText(/שבוע 1/)).toBeInTheDocument();
  });

  it('should show error message on error', () => {
    useSubmission.mockReturnValue({
      loading: false,
      days: [],
      isLocked: false,
      weekStatus: 'open',
      week: { id: 'w1', week_label: 'שבוע 1', status: 'open' },
      error: 'שגיאת תקשורת',
      notes: '',
      toggleShift: vi.fn(),
      setShiftHours: vi.fn(),
      setNotes: vi.fn(),
      submit: vi.fn(),
    });

    render(<SubmissionForm />);
    expect(screen.getByText(/שגיאת תקשורת/)).toBeInTheDocument();
  });

  it('should wrap content in guard-layout div', () => {
    useSubmission.mockReturnValue({
      loading: true,
      days: [],
      isLocked: false,
      weekStatus: null,
      week: null,
      error: null,
      notes: '',
      toggleShift: vi.fn(),
      setShiftHours: vi.fn(),
      setNotes: vi.fn(),
      submit: vi.fn(),
    });

    const { container } = render(<SubmissionForm />);
    expect(container.querySelector('.guard-layout')).toBeInTheDocument();
  });
});