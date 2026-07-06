import '@testing-library/jest-dom';

// jsdom (through v25) ships no PointerEvent, so fireEvent.pointer* would drop
// clientX/clientY. Polyfill it over MouseEvent so pointer-driven UI (e.g. the
// draggable split divider) is testable. setPointerCapture/release are no-ops.
if (typeof window.PointerEvent === 'undefined') {
  class PointerEvent extends MouseEvent {
    constructor(type, params = {}) {
      super(type, params);
      this.pointerId = params.pointerId;
    }
  }
  window.PointerEvent = PointerEvent;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}

// jsdom does not implement scrollIntoView (used e.g. by GuardForm on mount).
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
