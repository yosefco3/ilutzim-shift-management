import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import StatusGrid from '../src/components/StatusGrid';
import messages from '../src/utils/messages';

const submissions = [
  { user_id: 'g1', full_name: 'בובי ביטון', submitted_at: '2026-06-13T15:20:12' },
  { user_id: 'g2', full_name: 'יוסף כהן', submitted_at: null },
];

function renderGrid(props) {
  return render(
    <MemoryRouter>
      <StatusGrid submissions={submissions} {...props} />
    </MemoryRouter>,
  );
}

describe('StatusGrid — fill-constraints button gating', () => {
  it('shows the fill-constraints button for every guard when the week is editable', () => {
    renderGrid({ canFillConstraints: true });
    const buttons = screen.getAllByRole('button', { name: messages.guards.fillConstraints });
    expect(buttons).toHaveLength(2); // one per guard, incl. the one who has not submitted
    for (const btn of buttons) expect(btn).toBeEnabled();
  });

  it('disables the button (but keeps it and its column) when the week is locked', () => {
    renderGrid({ canFillConstraints: false });
    const buttons = screen.getAllByRole('button', { name: messages.guards.fillConstraints });
    expect(buttons).toHaveLength(2); // one per guard, all present
    for (const btn of buttons) expect(btn).toBeDisabled();
    // The actions column header is still shown.
    expect(screen.getByText(messages.common.actions)).toBeInTheDocument();
  });

  it('defaults to a disabled button when the prop is omitted', () => {
    renderGrid({});
    const buttons = screen.getAllByRole('button', { name: messages.guards.fillConstraints });
    expect(buttons.length).toBeGreaterThan(0);
    for (const btn of buttons) expect(btn).toBeDisabled();
  });

  it('points the button at the guard constraints route', () => {
    renderGrid({ canFillConstraints: true });
    const button = screen.getAllByRole('button', {
      name: messages.guards.fillConstraints,
    })[0];
    expect(button).toBeInTheDocument();
  });
});

describe('StatusGrid — soft constraint-rule warnings', () => {
  const RULES = {
    min_shifts_per_guard: 5,
    min_nights: 2,
    min_evenings: 2,
    max_consecutive_days: 6,
  };
  // One guard who submitted a single morning shift — breaches min shifts/nights/evenings.
  const detailsByUser = {
    g1: {
      user_id: 'g1',
      days: [
        {
          date: '2026-06-21',
          is_available: true,
          shift_windows: [{ shift_type: 'morning', start_time: '07:00', end_time: '16:00' }],
        },
      ],
    },
  };

  it('shows the warnings banner only after the row is expanded', () => {
    renderGrid({ detailsByUser, rules: RULES });
    // Hidden until expanded.
    expect(screen.queryByText(messages.submissions.warningsTitle)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'הצג' }));
    expect(screen.getByText(messages.submissions.warningsTitle)).toBeInTheDocument();
    expect(screen.getByText(/לילות/)).toBeInTheDocument();
  });

  it('shows no banner when rules are not loaded', () => {
    renderGrid({ detailsByUser, rules: null });
    fireEvent.click(screen.getByRole('button', { name: 'הצג' }));
    expect(screen.queryByText(messages.submissions.warningsTitle)).not.toBeInTheDocument();
  });
});
