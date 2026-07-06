import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import GuardTable from '../src/components/GuardTable';

const noop = () => {};
const guard = (overrides = {}) => ({
  id: 'g1',
  first_name: 'יוסי',
  last_name: 'כהן',
  phone_number: '0501234567',
  roles: [],
  is_active: true,
  ...overrides,
});

describe('GuardTable — GPS consent indicator (stage 3)', () => {
  it('shows the 📍 badge for a guard who consented', () => {
    render(
      <GuardTable
        guards={[guard({ gps_consent_at: '2026-07-04T10:00:00' })]}
        onEdit={noop}
        onToggle={noop}
        onDelete={noop}
      />,
    );
    expect(screen.getByLabelText('הסכמת GPS להחתמת נוכחות')).toBeInTheDocument();
  });

  it('shows nothing for a guard without consent', () => {
    render(
      <GuardTable guards={[guard()]} onEdit={noop} onToggle={noop} onDelete={noop} />,
    );
    expect(screen.queryByLabelText('הסכמת GPS להחתמת נוכחות')).not.toBeInTheDocument();
  });
});
