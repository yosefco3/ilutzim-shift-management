import { useEffect, useRef } from 'react';

// Scroll the pane the pointer is currently over with the keyboard. The mouse
// wheel already scrolls whichever overflow container it sits over; this extends
// that same "follow the pointer" feel to the arrow / page keys, which natively
// only move the focused element or the whole page. Attach the returned `ref` to
// the scroll container and spread `handlers` on it — while the pointer is inside,
// Up/Down (and PageUp/PageDown/Home/End) scroll that container instead of the page.
const LINE_STEP = 48; // px per arrow press — about one board row / guard card

// Don't steal keys while the user is typing in a field (e.g. the pool search box).
function isEditable(el) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

export default function useHoverScroll() {
  const ref = useRef(null);
  const hovering = useRef(false);

  useEffect(() => {
    const onKey = (e) => {
      if (!hovering.current) return;
      const el = ref.current;
      if (!el || isEditable(document.activeElement)) return;
      let dy = 0;
      switch (e.key) {
        case 'ArrowDown':
          dy = LINE_STEP;
          break;
        case 'ArrowUp':
          dy = -LINE_STEP;
          break;
        case 'PageDown':
          dy = el.clientHeight * 0.9;
          break;
        case 'PageUp':
          dy = -el.clientHeight * 0.9;
          break;
        case 'Home':
          el.scrollTo({ top: 0 });
          e.preventDefault();
          return;
        case 'End':
          el.scrollTo({ top: el.scrollHeight });
          e.preventDefault();
          return;
        default:
          return;
      }
      el.scrollBy({ top: dy });
      e.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handlers = {
    onMouseEnter: () => {
      hovering.current = true;
    },
    onMouseLeave: () => {
      hovering.current = false;
    },
  };

  return { ref, handlers };
}
