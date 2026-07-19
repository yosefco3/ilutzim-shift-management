import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import useBoardFit from '../src/hooks/useBoardFit';

// Harness: attach the hook's ref to a layout div, like the board pages do.
function Harness({ focusMode }) {
  const ref = useBoardFit(focusMode, []);
  return <div data-testid="layout" ref={ref} />;
}

function mockLayoutTop(el, top) {
  el.getBoundingClientRect = () => ({ top, bottom: top, left: 0, right: 0, width: 0, height: 0 });
}

describe('useBoardFit', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('caps the panes to the viewport space below the layout top', () => {
    vi.stubGlobal('innerHeight', 900);
    const { getByTestId, rerender } = render(<Harness focusMode={false} />);
    const el = getByTestId('layout');
    // jsdom mounts with top 0; re-measure with a realistic header offset.
    mockLayoutTop(el, 400);
    rerender(<Harness focusMode={false} />);
    act(() => window.dispatchEvent(new Event('resize')));
    // 900 viewport − 400 offset − 16 gap = 484
    expect(el.style.getPropertyValue('--board-fit-max')).toBe('484px');
  });

  it('never collapses below the minimum pane height', () => {
    vi.stubGlobal('innerHeight', 500);
    const { getByTestId, rerender } = render(<Harness focusMode={false} />);
    const el = getByTestId('layout');
    mockLayoutTop(el, 450);
    rerender(<Harness focusMode={false} />);
    act(() => window.dispatchEvent(new Event('resize')));
    expect(el.style.getPropertyValue('--board-fit-max')).toBe('240px');
  });

  it('clears the property in focus mode and restores it on exit', () => {
    vi.stubGlobal('innerHeight', 900);
    const { getByTestId, rerender } = render(<Harness focusMode={false} />);
    const el = getByTestId('layout');
    mockLayoutTop(el, 400);
    act(() => window.dispatchEvent(new Event('resize')));
    expect(el.style.getPropertyValue('--board-fit-max')).toBe('484px');

    rerender(<Harness focusMode />);
    expect(el.style.getPropertyValue('--board-fit-max')).toBe('');

    rerender(<Harness focusMode={false} />);
    expect(el.style.getPropertyValue('--board-fit-max')).toBe('484px');
  });

  it('stops refitting on resize after unmount', () => {
    vi.stubGlobal('innerHeight', 900);
    const { getByTestId, unmount } = render(<Harness focusMode={false} />);
    const el = getByTestId('layout');
    mockLayoutTop(el, 400);
    unmount();
    act(() => window.dispatchEvent(new Event('resize')));
    // Value from mount (top 0 → 884), untouched by the post-unmount resize.
    expect(el.style.getPropertyValue('--board-fit-max')).toBe('884px');
  });
});
