import { useLayoutEffect, useRef } from 'react';

// Cap the board's two scroll panes (grid + pool) to the viewport space that is
// actually below them. Their CSS fallback — max-height: calc(100vh - 2rem) —
// assumes the pane top sits at the viewport top, but on the board pages a
// ~400px header block pushes the panes down, so their bottom (and the last
// rows) lands off-screen and internal scrolling can never reveal it. The
// parent .board-layout is exactly as tall as the panes, so the sticky
// positioning that was meant to solve this never engages.
//
// The hook measures the layout's document offset (scroll-invariant, so the
// page never "creeps") and publishes it as --board-fit-max on the layout
// element; admin.css uses it as the panes' max-height. In focus mode the
// property is cleared and the fullscreen CSS fallback takes over.
const BOTTOM_GAP = 16; // px of breathing room above the viewport bottom
const MIN_PANE = 240; // don't collapse into a sliver on short windows

export default function useBoardFit(focusMode, deps = []) {
  const ref = useRef(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (focusMode) {
      el.style.removeProperty('--board-fit-max');
      return undefined;
    }
    const fit = () => {
      const docTop = el.getBoundingClientRect().top + window.scrollY;
      const max = Math.max(MIN_PANE, window.innerHeight - docTop - BOTTOM_GAP);
      el.style.setProperty('--board-fit-max', `${max}px`);
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusMode, ...deps]);

  return ref;
}
