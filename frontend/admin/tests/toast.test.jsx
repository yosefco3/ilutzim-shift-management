import { describe, it, expect } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider, useToast } from '../src/components/Toast';

// Test harness: buttons that trigger toasts via the hook.
function Harness() {
  const toast = useToast();
  return (
    <div>
      <button onClick={() => toast.success('נשמר')}>ok</button>
      <button onClick={() => toast.error('נכשל')}>err</button>
    </div>
  );
}

function renderWithProvider() {
  return render(
    <ToastProvider>
      <Harness />
    </ToastProvider>,
  );
}

describe('Toast', () => {
  it('shows a success toast when triggered', async () => {
    const user = userEvent.setup();
    renderWithProvider();
    await user.click(screen.getByText('ok'));
    expect(screen.getByText('נשמר')).toBeInTheDocument();
    expect(screen.getByText('נשמר').closest('.toast')).toHaveClass('toast-success');
  });

  it('shows an error toast with the error variant', async () => {
    const user = userEvent.setup();
    renderWithProvider();
    await user.click(screen.getByText('err'));
    expect(screen.getByText('נכשל').closest('.toast')).toHaveClass('toast-error');
  });

  it('dismisses a toast when its close button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProvider();
    await user.click(screen.getByText('ok'));
    await user.click(screen.getByLabelText('סגור'));
    expect(screen.queryByText('נשמר')).not.toBeInTheDocument();
  });

  it('throws if useToast is used outside a provider', () => {
    const Bare = () => { useToast(); return null; };
    // Silence the expected React error boundary log noise.
    expect(() => render(<Bare />)).toThrow(/ToastProvider/);
  });
});
