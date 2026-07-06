import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import GuardForm from '../src/components/GuardForm';

describe('GuardForm — preferred shift', () => {
  it('renders the optional preferred-shift select with all options', () => {
    render(<GuardForm guard={null} onSave={vi.fn()} onCancel={vi.fn()} />);
    const select = screen.getByRole('combobox');
    expect(select).toHaveValue('');
    const labels = [...select.options].map((o) => o.textContent);
    expect(labels).toEqual(['ללא העדפה', 'בוקר', 'ערב', 'לילה']);
    expect(screen.getByText('משמרת מועדפת')).toBeInTheDocument();
  });

  it('includes the chosen preferred shift in the saved payload', () => {
    const onSave = vi.fn();
    render(<GuardForm guard={null} onSave={onSave} onCancel={vi.fn()} />);

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'night' } });
    // Fill the required fields so the form submits.
    fireEvent.change(document.querySelector('input[name="first_name"]'), { target: { value: 'ישראל' } });
    fireEvent.change(document.querySelector('input[name="last_name"]'), { target: { value: 'ישראלי' } });
    fireEvent.change(document.querySelector('input[name="phone_number"]'), { target: { value: '0521234567' } });
    fireEvent.submit(document.querySelector('form'));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ preferred_shift: 'night' }),
    );
  });

  it('pre-selects the existing guard preference when editing', () => {
    const guard = {
      first_name: 'א',
      last_name: 'ב',
      phone_number: '0521234567',
      roles: [],
      preferred_shift: 'afternoon',
    };
    render(<GuardForm guard={guard} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole('combobox')).toHaveValue('afternoon');
  });
});
