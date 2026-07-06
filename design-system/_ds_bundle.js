/* @ds-bundle: {"format":3,"namespace":"IlutsimDesignSystem_f4254f","components":[{"name":"Alert","sourcePath":"components/core/Alert.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Dialog","sourcePath":"components/feedback/Dialog.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"Field","sourcePath":"components/forms/Field.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"TextInput","sourcePath":"components/forms/TextInput.jsx"},{"name":"Textarea","sourcePath":"components/forms/Textarea.jsx"}],"sourceHashes":{"components/core/Alert.jsx":"98e487e92a81","components/core/Badge.jsx":"cd0ff7010a88","components/core/Button.jsx":"ba9968c2f98f","components/core/Card.jsx":"22f73bbc1f85","components/feedback/Dialog.jsx":"1564fa36b927","components/feedback/Toast.jsx":"55d2ed6b6e07","components/forms/Field.jsx":"f9f734624df6","components/forms/Select.jsx":"f991fa693842","components/forms/TextInput.jsx":"bc057b5299a0","components/forms/Textarea.jsx":"817ecc58f9ba","concepts/schedule-builder/data.js":"13d1647dc696","concepts/schedule-builder/logic.js":"ffe8bbfb6768","ui_kits/admin/GuardsScreen.jsx":"a82bcea1f9bb","ui_kits/admin/LoginScreen.jsx":"387eb8ce8060","ui_kits/admin/Navbar.jsx":"02db87f99281","ui_kits/admin/SubmissionsScreen.jsx":"438f7f230720","ui_kits/admin/WeeksScreen.jsx":"6e0aa0579896","ui_kits/admin/data.js":"f17324838bc4"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.IlutsimDesignSystem_f4254f = window.IlutsimDesignSystem_f4254f || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Alert.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Ilutsim Alert — inline banner for form-level feedback. Soft-tinted, bordered,
 * RTL. Tones: error / success / warning / info.
 */
const TONES = {
  error: {
    bg: 'var(--danger-soft)',
    fg: 'var(--on-danger)',
    bd: 'rgba(239,68,68,.3)'
  },
  success: {
    bg: 'var(--success-soft)',
    fg: 'var(--on-success)',
    bd: 'rgba(34,197,94,.3)'
  },
  warning: {
    bg: 'var(--warning-soft)',
    fg: 'var(--on-warning)',
    bd: 'rgba(245,158,11,.3)'
  },
  info: {
    bg: 'var(--info-soft)',
    fg: 'var(--on-info)',
    bd: 'rgba(56,189,248,.3)'
  }
};
function Alert({
  children,
  tone = 'info',
  style = {},
  ...rest
}) {
  const t = TONES[tone] || TONES.info;
  return /*#__PURE__*/React.createElement("div", _extends({
    role: "alert",
    style: {
      padding: '0.7rem 0.9rem',
      borderRadius: 'var(--radius-sm)',
      fontSize: 'var(--fs-base)',
      fontFamily: 'var(--font-sans)',
      lineHeight: 'var(--lh-snug)',
      border: `1px solid ${t.bd}`,
      background: t.bg,
      color: t.fg,
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Alert });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Alert.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Ilutsim Badge — pill status label. Covers week lifecycle (open/locked/
 * published/closed), guard activity (active/inactive), submission state
 * (submitted/missing) and generic semantic tones. Soft-tinted on dark.
 */

const TONES = {
  open: {
    bg: 'var(--info-soft)',
    fg: 'var(--on-info)',
    bd: 'rgba(56,189,248,.25)'
  },
  locked: {
    bg: 'var(--warning-soft)',
    fg: 'var(--on-warning)',
    bd: 'rgba(245,158,11,.25)'
  },
  published: {
    bg: 'var(--success-soft)',
    fg: 'var(--on-success)',
    bd: 'rgba(34,197,94,.25)'
  },
  closed: {
    bg: 'var(--surface-3)',
    fg: 'var(--text-dim)',
    bd: 'var(--border-strong)'
  },
  active: {
    bg: 'var(--success-soft)',
    fg: 'var(--on-success)',
    bd: 'rgba(34,197,94,.25)'
  },
  inactive: {
    bg: 'var(--surface-3)',
    fg: 'var(--text-dim)',
    bd: 'var(--border-strong)'
  },
  submitted: {
    bg: 'var(--success-soft)',
    fg: 'var(--on-success)',
    bd: 'rgba(34,197,94,.25)'
  },
  missing: {
    bg: 'var(--danger-soft)',
    fg: 'var(--on-danger)',
    bd: 'rgba(239,68,68,.25)'
  },
  success: {
    bg: 'var(--success-soft)',
    fg: 'var(--on-success)',
    bd: 'rgba(34,197,94,.25)'
  },
  warning: {
    bg: 'var(--warning-soft)',
    fg: 'var(--on-warning)',
    bd: 'rgba(245,158,11,.25)'
  },
  danger: {
    bg: 'var(--danger-soft)',
    fg: 'var(--on-danger)',
    bd: 'rgba(239,68,68,.25)'
  },
  info: {
    bg: 'var(--info-soft)',
    fg: 'var(--on-info)',
    bd: 'rgba(56,189,248,.25)'
  },
  secondary: {
    bg: 'var(--surface-3)',
    fg: 'var(--text-muted)',
    bd: 'var(--border-strong)'
  }
};
function Badge({
  children,
  tone = 'secondary',
  icon = null,
  style = {},
  ...rest
}) {
  const t = TONES[tone] || TONES.secondary;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.3rem',
      padding: '0.2rem 0.6rem',
      borderRadius: 'var(--radius-pill)',
      fontSize: 'var(--fs-xs)',
      fontWeight: 'var(--fw-semibold)',
      fontFamily: 'var(--font-sans)',
      lineHeight: 'var(--lh-tight)',
      border: `1px solid ${t.bd}`,
      background: t.bg,
      color: t.fg,
      ...style
    }
  }, rest), icon && /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true"
  }, icon), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
/**
 * Ilutsim Button — the dark-indigo action button used across the admin app.
 * Variants map 1:1 to the live app's .btn-* classes; styling is driven by the
 * design-system CSS custom properties so it renders correctly anywhere
 * styles.css is linked. RTL by default.
 */
const SIZES = {
  md: {
    padding: '0.5rem 1rem',
    fontSize: 'var(--fs-base)'
  },
  sm: {
    padding: '0.3rem 0.65rem',
    fontSize: 'var(--fs-sm)'
  }
};
function variantStyle(variant, hovered) {
  switch (variant) {
    case 'primary':
      return {
        background: hovered ? 'var(--primary-hover)' : 'var(--primary)',
        color: '#fff',
        borderColor: 'transparent'
      };
    case 'danger':
      return {
        background: hovered ? 'var(--danger-hover)' : 'var(--danger)',
        color: '#fff',
        borderColor: 'transparent'
      };
    case 'success':
      return {
        background: hovered ? '#2dd46a' : 'var(--success)',
        color: '#0a2e16',
        borderColor: 'transparent'
      };
    case 'secondary':
      return {
        background: hovered ? 'var(--border-strong)' : 'var(--surface-3)',
        color: 'var(--text)',
        borderColor: 'var(--border-strong)'
      };
    case 'outline':
      return {
        background: hovered ? 'rgba(255,255,255,.03)' : 'transparent',
        color: hovered ? 'var(--text)' : 'var(--text-muted)',
        borderColor: hovered ? 'var(--text-dim)' : 'var(--border-strong)'
      };
    case 'ghost':
      return {
        background: hovered ? 'rgba(255,255,255,.05)' : 'transparent',
        color: hovered ? 'var(--text)' : 'var(--text-muted)',
        borderColor: 'transparent'
      };
    default:
      return {
        background: 'var(--primary)',
        color: '#fff',
        borderColor: 'transparent'
      };
  }
}
function Button({
  children,
  variant = 'primary',
  size = 'md',
  block = false,
  disabled = false,
  icon = null,
  style = {},
  ...rest
}) {
  const [hovered, setHovered] = useState(false);
  const [pressed, setPressed] = useState(false);
  const base = {
    display: block ? 'flex' : 'inline-flex',
    width: block ? '100%' : undefined,
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.45rem',
    border: '1px solid transparent',
    borderRadius: 'var(--radius-sm)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontWeight: 'var(--fw-control)',
    fontFamily: 'var(--font-sans)',
    lineHeight: 'var(--lh-tight)',
    opacity: disabled ? 0.45 : 1,
    transform: pressed && !disabled ? 'translateY(1px)' : 'none',
    transition: 'background var(--t-fast), border-color var(--t-fast), color var(--t-fast), transform var(--t-press)',
    ...SIZES[size],
    ...variantStyle(variant, hovered && !disabled),
    ...style
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    disabled: disabled,
    style: base,
    onMouseEnter: () => setHovered(true),
    onMouseLeave: () => {
      setHovered(false);
      setPressed(false);
    },
    onMouseDown: () => setPressed(true),
    onMouseUp: () => setPressed(false)
  }, rest), icon && /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true"
  }, icon), children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Ilutsim Card — the base surface panel used for forms, week cards, settings
 * rows and login. Dark layered surface with a hairline border and soft shadow.
 * Optionally interactive (hover lift), as used by the week cards.
 */
function Card({
  children,
  interactive = false,
  style = {},
  ...rest
}) {
  const [hovered, setHovered] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", _extends({
    onMouseEnter: () => interactive && setHovered(true),
    onMouseLeave: () => interactive && setHovered(false),
    style: {
      background: 'var(--surface)',
      border: `1px solid ${hovered ? 'var(--border-strong)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)',
      padding: 'var(--space-5)',
      boxShadow: hovered ? 'var(--shadow-md)' : 'var(--shadow)',
      color: 'var(--text)',
      fontFamily: 'var(--font-sans)',
      transition: 'border-color var(--t-fast), box-shadow var(--t-fast)',
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Dialog.jsx
try { (() => {
/**
 * Ilutsim Dialog — centered confirm modal over a blurred dark scrim. Used for
 * destructive confirmations (delete guard / delete week).
 */
function Dialog({
  title,
  message,
  children,
  confirmLabel = 'אישור',
  cancelLabel = 'ביטול',
  confirmVariant = 'danger',
  onConfirm,
  onCancel
}) {
  return /*#__PURE__*/React.createElement("div", {
    onClick: onCancel,
    style: {
      position: 'fixed',
      inset: 0,
      zIndex: 200,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'rgba(5,7,12,.65)',
      backdropFilter: 'blur(2px)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    onClick: e => e.stopPropagation(),
    style: {
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: 'var(--space-8)',
      maxWidth: 400,
      width: '90%',
      textAlign: 'center',
      boxShadow: 'var(--shadow-lg)',
      color: 'var(--text)',
      fontFamily: 'var(--font-sans)'
    }
  }, title && /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: '0 0 0.75rem',
      fontSize: 'var(--fs-lg)',
      fontWeight: 'var(--fw-heading)'
    }
  }, title), message && /*#__PURE__*/React.createElement("p", {
    style: {
      marginBottom: 'var(--space-6)',
      fontSize: 'var(--fs-lg)',
      lineHeight: 'var(--lh-snug)'
    }
  }, message), children, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '0.75rem',
      justifyContent: 'center'
    }
  }, onConfirm && /*#__PURE__*/React.createElement(__ds_scope.Button, {
    variant: confirmVariant,
    onClick: onConfirm
  }, confirmLabel), onCancel && /*#__PURE__*/React.createElement(__ds_scope.Button, {
    variant: "secondary",
    onClick: onCancel
  }, cancelLabel))));
}
Object.assign(__ds_scope, { Dialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
const ICONS = {
  success: '✓',
  error: '✕',
  warning: '!',
  info: 'i'
};
const ACCENT = {
  success: 'var(--success)',
  error: 'var(--danger)',
  warning: 'var(--warning)',
  info: 'var(--info)'
};
const ICON_TINT = {
  success: {
    bg: 'var(--success-soft)',
    fg: 'var(--on-success)'
  },
  error: {
    bg: 'var(--danger-soft)',
    fg: 'var(--on-danger)'
  },
  warning: {
    bg: 'var(--warning-soft)',
    fg: 'var(--on-warning)'
  },
  info: {
    bg: 'var(--info-soft)',
    fg: 'var(--on-info)'
  }
};

/**
 * Ilutsim Toast — transient in-app notification (replaces native alert()).
 * Presentational: render inside a fixed top-center container. Variant sets the
 * leading accent border + icon chip.
 */
function Toast({
  children,
  variant = 'info',
  onClose,
  style = {}
}) {
  const tint = ICON_TINT[variant] || ICON_TINT.info;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: '0.65rem',
      minWidth: 260,
      maxWidth: 440,
      padding: '0.7rem 0.85rem',
      background: 'var(--surface-3)',
      color: 'var(--text)',
      border: '1px solid var(--border-strong)',
      borderInlineStart: `3px solid ${ACCENT[variant] || 'var(--text-dim)'}`,
      borderRadius: 'var(--radius)',
      boxShadow: 'var(--shadow-lg)',
      fontSize: 'var(--fs-md)',
      fontFamily: 'var(--font-sans)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 22,
      height: 22,
      borderRadius: 'var(--radius-pill)',
      fontSize: '0.8rem',
      fontWeight: 'var(--fw-bold)',
      flexShrink: 0,
      background: tint.bg,
      color: tint.fg
    }
  }, ICONS[variant]), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      lineHeight: 'var(--lh-snug)'
    }
  }, children), onClose && /*#__PURE__*/React.createElement("button", {
    type: "button",
    "aria-label": "\u05E1\u05D2\u05D5\u05E8",
    onClick: onClose,
    style: {
      background: 'none',
      border: 'none',
      color: 'var(--text-dim)',
      fontSize: '1.15rem',
      lineHeight: 1,
      cursor: 'pointer',
      padding: '0 0.15rem',
      flexShrink: 0
    }
  }, "\xD7"));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/forms/Field.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Ilutsim Field — label + control wrapper with optional hint, matching the
 * app's .form-group. Compose with TextInput / Select / Textarea.
 */
function Field({
  label,
  hint,
  htmlFor,
  children,
  style = {},
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      marginBottom: 'var(--space-4)',
      ...style
    }
  }, rest), label && /*#__PURE__*/React.createElement("label", {
    htmlFor: htmlFor,
    style: {
      display: 'block',
      fontWeight: 'var(--fw-control)',
      marginBottom: '0.35rem',
      fontSize: 'var(--fs-base)',
      color: 'var(--text-muted)',
      fontFamily: 'var(--font-sans)'
    }
  }, label), children, hint && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '0.35rem 0 0',
      fontSize: 'var(--fs-sm)',
      color: 'var(--text-dim)',
      fontFamily: 'var(--font-sans)'
    }
  }, hint));
}
Object.assign(__ds_scope, { Field });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Field.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
const baseControl = focused => ({
  width: '100%',
  padding: '0.55rem 0.75rem',
  background: 'var(--surface-2)',
  color: 'var(--text)',
  border: `1px solid ${focused ? 'var(--primary)' : 'var(--border-strong)'}`,
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--fs-md)',
  fontFamily: 'var(--font-sans)',
  direction: 'rtl',
  outline: 'none',
  boxShadow: focused ? '0 0 0 3px var(--primary-soft)' : 'none',
  transition: 'border-color var(--t-fast), box-shadow var(--t-fast)'
});

/** Ilutsim select — same field treatment as TextInput. */
function Select({
  children,
  style = {},
  onFocus,
  onBlur,
  ...rest
}) {
  const [focused, setFocused] = useState(false);
  return /*#__PURE__*/React.createElement("select", _extends({
    style: {
      ...baseControl(focused),
      cursor: 'pointer',
      ...style
    },
    onFocus: e => {
      setFocused(true);
      onFocus && onFocus(e);
    },
    onBlur: e => {
      setFocused(false);
      onBlur && onBlur(e);
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/TextInput.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
const baseControl = focused => ({
  width: '100%',
  padding: '0.55rem 0.75rem',
  background: 'var(--surface-2)',
  color: 'var(--text)',
  border: `1px solid ${focused ? 'var(--primary)' : 'var(--border-strong)'}`,
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--fs-md)',
  fontFamily: 'var(--font-sans)',
  direction: 'rtl',
  outline: 'none',
  boxShadow: focused ? '0 0 0 3px var(--primary-soft)' : 'none',
  transition: 'border-color var(--t-fast), box-shadow var(--t-fast)'
});

/** Ilutsim text input — dark field with indigo focus ring. */
function TextInput({
  style = {},
  onFocus,
  onBlur,
  ...rest
}) {
  const [focused, setFocused] = useState(false);
  return /*#__PURE__*/React.createElement("input", _extends({
    style: {
      ...baseControl(focused),
      ...style
    },
    onFocus: e => {
      setFocused(true);
      onFocus && onFocus(e);
    },
    onBlur: e => {
      setFocused(false);
      onBlur && onBlur(e);
    }
  }, rest));
}
Object.assign(__ds_scope, { TextInput });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/TextInput.jsx", error: String((e && e.message) || e) }); }

// components/forms/Textarea.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
/** Ilutsim textarea — dark field, vertical resize, indigo focus ring. */
function Textarea({
  style = {},
  onFocus,
  onBlur,
  ...rest
}) {
  const [focused, setFocused] = useState(false);
  return /*#__PURE__*/React.createElement("textarea", _extends({
    style: {
      width: '100%',
      minHeight: 70,
      padding: '0.55rem 0.75rem',
      background: 'var(--surface-2)',
      color: 'var(--text)',
      border: `1px solid ${focused ? 'var(--primary)' : 'var(--border-strong)'}`,
      borderRadius: 'var(--radius-sm)',
      fontSize: 'var(--fs-md)',
      fontFamily: 'var(--font-sans)',
      direction: 'rtl',
      resize: 'vertical',
      outline: 'none',
      boxShadow: focused ? '0 0 0 3px var(--primary-soft)' : 'none',
      transition: 'border-color var(--t-fast), box-shadow var(--t-fast)',
      ...style
    },
    onFocus: e => {
      setFocused(true);
      onFocus && onFocus(e);
    },
    onBlur: e => {
      setFocused(false);
      onBlur && onBlur(e);
    }
  }, rest));
}
Object.assign(__ds_scope, { Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Textarea.jsx", error: String((e && e.message) || e) }); }

// concepts/schedule-builder/data.js
try { (() => {
// Demo data for the schedule-builder concept. Positions per shift, a guard pool
// with weekly availability windows + attributes. Names/positions echo the real
// hand-built sheet (סידור עבודה שבועי).
//
// Day index: 0=ראשון … 6=שבת.  Times "HH:MM"; a night window like "23:00-07:00"
// wraps past midnight (the app adds 24h to the end when end<=start).

window.SB = function () {
  // ── Attribute keys → Hebrew labels ──────────────────────────────
  const ATTRS = {
    armed: 'חמוש',
    roni: 'רוני',
    vehicle: 'רכב עירייה',
    walking: 'הליכה מרובה'
  };

  // ── Positions (עמדות) per shift. requires: attribute keys. ───────
  // activeDays omitted = all 7 days.
  const POSITIONS = {
    morning: [{
      id: 'm_ahmash',
      name: 'א. אחמ"ש',
      hours: '07:00-15:00',
      requires: ['armed']
    }, {
      id: 'm_arnona',
      name: 'ארנונה',
      hours: '07:30-15:00',
      requires: [],
      activeDays: [0, 1, 2, 3, 4]
    }, {
      id: 'm_haml',
      name: 'חמ"ל',
      hours: '07:00-15:00',
      requires: []
    }, {
      id: 'm_floor6',
      name: 'קומה 6',
      hours: '07:00-15:00',
      requires: []
    }, {
      id: 'm_patrol1',
      name: 'סייר 1',
      hours: '07:00-15:00',
      requires: ['walking', 'vehicle']
    }, {
      id: 'm_patrol2',
      name: 'סייר 2',
      hours: '07:00-15:00',
      requires: ['walking']
    }, {
      id: 'm_square',
      name: 'סייר כיכר',
      hours: '07:00-15:00',
      requires: ['walking']
    }, {
      id: 'm_b4',
      name: 'ב-4',
      hours: '08:00-16:30',
      requires: ['armed'],
      activeDays: [0, 1, 2, 3, 4]
    }, {
      id: 'm_b7',
      name: 'ב-7',
      hours: '08:00-16:30',
      requires: []
    }, {
      id: 'm_b8',
      name: 'ב-8',
      hours: '08:00-16:30',
      requires: []
    }, {
      id: 'm_b10',
      name: 'ב-10',
      hours: '08:00-16:30',
      requires: []
    }, {
      id: 'm_mevak',
      name: 'מבקרת',
      hours: '08:00-16:30',
      requires: ['roni']
    }],
    evening: [{
      id: 'e_ahmash',
      name: 'אחמ"ש ערב',
      hours: '15:00-23:00',
      requires: ['armed']
    }, {
      id: 'e_haml',
      name: 'חמ"ל ערב',
      hours: '15:00-23:00',
      requires: []
    }, {
      id: 'e_patrol1',
      name: 'סייר 1 ערב',
      hours: '15:00-23:00',
      requires: ['walking', 'vehicle']
    }, {
      id: 'e_b1',
      name: 'ב-1',
      hours: '17:00-23:00',
      requires: []
    }, {
      id: 'e_sb',
      name: 'ס.ב',
      hours: '17:00-23:00',
      requires: []
    }, {
      id: 'e_scan',
      name: 'צופה סורק',
      hours: '17:00-23:00',
      requires: []
    }],
    night: [{
      id: 'n_haml',
      name: 'חמ"ל לילה',
      hours: '23:00-07:00',
      requires: []
    }, {
      id: 'n_patrol1',
      name: 'סייר 1 לילה',
      hours: '23:00-07:00',
      requires: ['walking']
    }, {
      id: 'n_floor6',
      name: 'קומה 6 לילה',
      hours: '23:00-07:00',
      requires: []
    }, {
      id: 'n_car',
      name: 'רכב סיור',
      hours: '19:00-07:00',
      requires: ['vehicle']
    }]
  };

  // ── Guards (pool). avail: {dayIndex: "HH:MM-HH:MM"}; missing day = off. ──
  const GUARDS = [{
    id: 'g_yosef',
    name: 'יוסף כהן',
    role: 'אחמ"ש',
    attrs: ['armed'],
    avail: {
      0: '07:00-19:00',
      1: '07:00-19:00',
      2: '07:00-19:00',
      3: '07:00-19:00',
      4: '07:00-19:00',
      5: '07:00-14:00'
    }
  }, {
    id: 'g_yehudit',
    name: 'יעל אורן',
    role: 'מאבטח 9 שעות',
    attrs: ['vehicle'],
    avail: {
      0: '07:00-19:00',
      1: '07:00-19:00',
      2: '07:00-19:00',
      3: '07:00-19:00',
      4: '07:00-19:00',
      5: '07:00-15:00'
    }
  }, {
    id: 'g_menahem',
    name: 'נדב שקד',
    role: 'מאבטח בסיסי',
    attrs: [],
    avail: {
      0: '07:00-19:00',
      1: '07:00-19:00',
      2: '07:00-19:00',
      3: '07:00-19:00',
      4: '07:00-17:00'
    }
  }, {
    id: 'g_omer',
    name: 'עידו נחום',
    role: 'מאבטח בסיסי',
    attrs: [],
    avail: {
      0: '06:00-19:00',
      1: '06:00-19:00',
      2: '06:00-19:00',
      3: '06:00-19:00',
      4: '06:00-19:00',
      5: '06:00-14:00'
    }
  }, {
    id: 'g_yaniv',
    name: 'אלון ברק',
    role: "רמה ב'",
    attrs: ['armed'],
    avail: {
      0: '07:00-15:00',
      1: '07:00-15:00',
      2: '07:00-15:00',
      3: '07:00-15:00'
    }
  }, {
    id: 'g_dvorak',
    name: 'דור אלמוג',
    role: 'מאבטח בסיסי',
    attrs: ['roni'],
    avail: {
      0: '08:00-23:00',
      1: '08:00-23:00',
      2: '08:00-23:00',
      3: '08:00-23:00',
      4: '08:00-15:00'
    }
  }, {
    id: 'g_moshe',
    name: 'תומר',
    role: 'מאבטח בסיסי',
    attrs: [],
    avail: {
      0: '15:00-23:00',
      1: '15:00-23:00',
      2: '15:00-23:00',
      3: '15:00-23:00',
      4: '15:00-23:00'
    }
  }, {
    id: 'g_talpeled',
    name: 'גל סער',
    role: 'מאבטח 9 שעות',
    attrs: ['walking', 'vehicle'],
    avail: {
      0: '07:00-16:30',
      1: '07:00-16:30',
      2: '07:00-16:30',
      3: '07:00-16:30',
      4: '07:00-16:30'
    }
  }, {
    id: 'g_sapir',
    name: 'ליאור',
    role: 'מאבטח בסיסי',
    attrs: [],
    avail: {
      0: '16:00-07:00',
      1: '16:00-07:00',
      2: '16:00-07:00',
      3: '16:00-07:00',
      4: '16:00-07:00'
    }
  }, {
    id: 'g_ayalon',
    name: 'אלעד',
    role: 'לא חמוש',
    attrs: [],
    avail: {
      0: '23:00-07:00',
      1: '23:00-07:00',
      2: '23:00-07:00',
      3: '23:00-07:00'
    }
  }, {
    id: 'g_lewis',
    name: 'רותם',
    role: 'מאבטח בסיסי',
    attrs: [],
    avail: {
      0: '16:30-23:00',
      1: '16:30-23:00',
      2: '16:30-23:00',
      3: '16:30-23:00',
      4: '16:30-23:00'
    }
  }, {
    id: 'g_maor',
    name: 'ניר גפן',
    role: "רמה ב'",
    attrs: ['walking'],
    avail: {
      0: '07:00-16:30',
      1: '07:00-16:30',
      2: '07:00-16:30',
      3: '07:00-16:30',
      4: '07:00-16:30'
    }
  }, {
    id: 'g_tzion',
    name: 'אסף כרמל',
    role: 'מאבטח 9 שעות',
    attrs: ['vehicle'],
    avail: {
      0: '07:00-17:00',
      1: '07:00-17:00',
      2: '07:00-17:00',
      3: '07:00-17:00',
      4: '07:00-17:00'
    }
  }, {
    id: 'g_elia',
    name: 'איתן שגב',
    role: 'אחמ"ש',
    attrs: ['armed', 'roni'],
    avail: {
      0: '07:00-15:00',
      1: '07:00-15:00',
      2: '07:00-15:00',
      3: '07:00-15:00',
      4: '07:00-15:00'
    }
  }];
  const DAYS = [{
    name: 'ראשון',
    date: '14.06'
  }, {
    name: 'שני',
    date: '15.06'
  }, {
    name: 'שלישי',
    date: '16.06'
  }, {
    name: 'רביעי',
    date: '17.06'
  }, {
    name: 'חמישי',
    date: '18.06'
  }, {
    name: 'שישי',
    date: '19.06'
  }, {
    name: 'שבת',
    date: '20.06'
  }];
  const SHIFTS = [{
    id: 'morning',
    label: 'בוקר'
  }, {
    id: 'evening',
    label: 'ערב'
  }, {
    id: 'night',
    label: 'לילה'
  }];
  return {
    ATTRS,
    POSITIONS,
    GUARDS,
    DAYS,
    SHIFTS
  };
}();
})(); } catch (e) { __ds_ns.__errors.push({ path: "concepts/schedule-builder/data.js", error: String((e && e.message) || e) }); }

// concepts/schedule-builder/logic.js
try { (() => {
// Pure scheduling helpers for the schedule-builder concept. No React here.
window.SBLogic = function () {
  // "HH:MM" -> minutes from midnight.
  function toMin(hhmm) {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
  }
  // "HH:MM-HH:MM" -> {s, e} in minutes; night windows (end<=start) wrap +24h.
  function win(range) {
    const [a, b] = range.split('-');
    let s = toMin(a),
      e = toMin(b);
    if (e <= s) e += 24 * 60;
    return {
      s,
      e
    };
  }
  function len(range) {
    const w = win(range);
    return (w.e - w.s) / 60;
  }

  // Overlap classification of a guard's day-window against a position window.
  // Returns 'full' (covers whole position), 'partial', or 'none'.
  function coverage(guardRange, posRange) {
    if (!guardRange) return 'none';
    const g = win(guardRange),
      p = win(posRange);
    // align possible midnight-wrap: also test guard shifted +24h
    const variants = [g, {
      s: g.s + 1440,
      e: g.e + 1440
    }, {
      s: g.s - 1440,
      e: g.e - 1440
    }];
    let best = 'none';
    for (const gv of variants) {
      const lo = Math.max(gv.s, p.s),
        hi = Math.min(gv.e, p.e);
      const ov = hi - lo;
      if (ov <= 0) continue;
      if (gv.s <= p.s && gv.e >= p.e) return 'full';
      if (ov > 0) best = 'partial';
    }
    return best;
  }
  function posActive(pos, day) {
    return !pos.activeDays || pos.activeDays.includes(day);
  }

  // Total available hours in the week (sum of daily windows).
  function weeklyBudget(guard) {
    return Object.values(guard.avail).reduce((sum, r) => sum + len(r), 0);
  }

  // Hours assigned to a guard across all current assignments.
  function assignedHours(guardId, assignments, allPositions) {
    let h = 0;
    for (const key in assignments) {
      if (assignments[key] !== guardId) continue;
      const posId = key.split('@')[0];
      const pos = allPositions.find(p => p.id === posId);
      if (pos) h += len(pos.hours);
    }
    return h;
  }

  // Compute soft (non-blocking) warnings for assigning guard to (pos, day).
  function warnings(guard, pos, day, assignments, allPositions) {
    const out = [];
    const cov = coverage(guard.avail[day], pos.hours);
    if (cov === 'none') out.push({
      type: 'avail',
      text: 'מחוץ לזמינות שדיווח'
    });else if (cov === 'partial') out.push({
      type: 'partial',
      text: 'מכסה רק חלק מהשעות'
    });
    for (const req of pos.requires) {
      if (!guard.attrs.includes(req)) out.push({
        type: 'attr',
        text: 'חסר: ' + window.SB.ATTRS[req]
      });
    }

    // double-booking: same guard assigned elsewhere same day with overlapping hours
    for (const key in assignments) {
      if (assignments[key] !== guard.id) continue;
      const [otherPosId, d] = key.split('@');
      if (Number(d) !== day || otherPosId === pos.id) continue;
      const other = allPositions.find(p => p.id === otherPosId);
      if (!other) continue;
      const a = win(pos.hours),
        b = win(other.hours);
      if (Math.max(a.s, b.s) < Math.min(a.e, b.e)) {
        out.push({
          type: 'double',
          text: 'שיבוץ כפול: ' + other.name
        });
      }
    }
    return out;
  }
  return {
    toMin,
    win,
    len,
    coverage,
    posActive,
    weeklyBudget,
    assignedHours,
    warnings
  };
}();
})(); } catch (e) { __ds_ns.__errors.push({ path: "concepts/schedule-builder/logic.js", error: String((e && e.message) || e) }); }

// ui_kits/admin/GuardsScreen.jsx
try { (() => {
// Guards management — table + add/edit form + delete confirm.
const {
  Button: KitBtn_g,
  Badge: KitBadge_g,
  Card: KitCard_g,
  Dialog: KitDialog_g,
  Field: KitField_g,
  TextInput: KitInput_g,
  Select: KitSelect_g
} = window.IlutsimDesignSystem_f4254f;
const ROLE_OPTS = [{
  value: 'AHMASH',
  label: 'אחמ"ש'
}, {
  value: 'BASIC_GUARD',
  label: 'מאבטח בסיסי'
}, {
  value: 'LEVEL_B',
  label: "מאבטח רמה ב'"
}, {
  value: 'NINE_HOURS',
  label: 'מאבטח 9 שעות'
}, {
  value: 'UNARMED',
  label: 'לא חמוש'
}, {
  value: 'CHECKER',
  label: 'בודק'
}];
function GuardForm({
  guard,
  onSave,
  onCancel
}) {
  const [form, setForm] = React.useState({
    first_name: guard?.first_name || '',
    last_name: guard?.last_name || '',
    phone_number: guard?.phone_number || '',
    role: guard?.role || 'AHMASH'
  });
  const set = k => e => setForm(f => ({
    ...f,
    [k]: e.target.value
  }));
  return /*#__PURE__*/React.createElement(KitCard_g, {
    style: {
      marginBottom: '1rem'
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: '0 0 1rem',
      fontSize: 'var(--fs-lg)',
      fontWeight: 'var(--fw-heading)'
    }
  }, guard ? 'עריכת מאבטח' : 'הוספת מאבטח'), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '0 1rem'
    }
  }, /*#__PURE__*/React.createElement(KitField_g, {
    label: "\u05E9\u05DD \u05E4\u05E8\u05D8\u05D9"
  }, /*#__PURE__*/React.createElement(KitInput_g, {
    value: form.first_name,
    onChange: set('first_name')
  })), /*#__PURE__*/React.createElement(KitField_g, {
    label: "\u05E9\u05DD \u05DE\u05E9\u05E4\u05D7\u05D4"
  }, /*#__PURE__*/React.createElement(KitInput_g, {
    value: form.last_name,
    onChange: set('last_name')
  })), /*#__PURE__*/React.createElement(KitField_g, {
    label: "\u05D8\u05DC\u05E4\u05D5\u05DF"
  }, /*#__PURE__*/React.createElement(KitInput_g, {
    value: form.phone_number,
    onChange: set('phone_number')
  })), /*#__PURE__*/React.createElement(KitField_g, {
    label: "\u05EA\u05E4\u05E7\u05D9\u05D3"
  }, /*#__PURE__*/React.createElement(KitSelect_g, {
    value: form.role,
    onChange: set('role')
  }, ROLE_OPTS.map(r => /*#__PURE__*/React.createElement("option", {
    key: r.value,
    value: r.value
  }, r.label))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '0.6rem',
      marginTop: '0.5rem'
    }
  }, /*#__PURE__*/React.createElement(KitBtn_g, {
    variant: "primary",
    onClick: () => onSave(form)
  }, "\u05E9\u05DE\u05D5\u05E8"), /*#__PURE__*/React.createElement(KitBtn_g, {
    variant: "secondary",
    onClick: onCancel
  }, "\u05D1\u05D9\u05D8\u05D5\u05DC")));
}
function GuardsScreen({
  toast
}) {
  const {
    ROLE_LABELS
  } = window.KitData;
  const [guards, setGuards] = React.useState(() => window.KitData.guards.map(g => ({
    ...g
  })));
  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState(null);
  const [confirm, setConfirm] = React.useState(null);
  const save = data => {
    if (editing) {
      setGuards(gs => gs.map(g => g.id === editing.id ? {
        ...g,
        ...data
      } : g));
    } else {
      setGuards(gs => [...gs, {
        id: Date.now(),
        is_active: true,
        ...data
      }]);
    }
    setShowForm(false);
    setEditing(null);
    toast && toast('success', 'הפעולה בוצעה בהצלחה');
  };
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-header"
  }, /*#__PURE__*/React.createElement("h2", null, "\u05E0\u05D9\u05D4\u05D5\u05DC \u05DE\u05D0\u05D1\u05D8\u05D7\u05D9\u05DD"), !showForm && /*#__PURE__*/React.createElement(KitBtn_g, {
    variant: "primary",
    onClick: () => {
      setEditing(null);
      setShowForm(true);
    }
  }, "\u05D4\u05D5\u05E1\u05E4\u05EA \u05DE\u05D0\u05D1\u05D8\u05D7")), showForm && /*#__PURE__*/React.createElement(GuardForm, {
    guard: editing,
    onSave: save,
    onCancel: () => {
      setShowForm(false);
      setEditing(null);
    }
  }), /*#__PURE__*/React.createElement("table", {
    className: "data-table"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "\u05E9\u05DD \u05DE\u05DC\u05D0"), /*#__PURE__*/React.createElement("th", null, "\u05D8\u05DC\u05E4\u05D5\u05DF"), /*#__PURE__*/React.createElement("th", null, "\u05EA\u05E4\u05E7\u05D9\u05D3"), /*#__PURE__*/React.createElement("th", null, "\u05E4\u05E2\u05D9\u05DC"), /*#__PURE__*/React.createElement("th", null, "\u05E4\u05E2\u05D5\u05DC\u05D5\u05EA"))), /*#__PURE__*/React.createElement("tbody", null, guards.map(g => /*#__PURE__*/React.createElement("tr", {
    key: g.id
  }, /*#__PURE__*/React.createElement("td", null, g.first_name, " ", g.last_name), /*#__PURE__*/React.createElement("td", null, g.phone_number || '—'), /*#__PURE__*/React.createElement("td", null, ROLE_LABELS[g.role] || g.role), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement(KitBadge_g, {
    tone: g.is_active ? 'active' : 'inactive'
  }, g.is_active ? 'פעיל' : 'לא פעיל')), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("div", {
    className: "actions-cell"
  }, /*#__PURE__*/React.createElement(KitBtn_g, {
    variant: "primary",
    size: "sm",
    onClick: () => {
      setEditing(g);
      setShowForm(true);
    }
  }, "\u05E2\u05E8\u05D5\u05DA"), /*#__PURE__*/React.createElement(KitBtn_g, {
    variant: "secondary",
    size: "sm"
  }, "\u05DE\u05D9\u05DC\u05D5\u05D9 \u05D0\u05D9\u05DC\u05D5\u05E6\u05D9\u05DD"), /*#__PURE__*/React.createElement(KitBtn_g, {
    variant: "secondary",
    size: "sm",
    onClick: () => {
      setGuards(gs => gs.map(x => x.id === g.id ? {
        ...x,
        is_active: !x.is_active
      } : x));
    }
  }, g.is_active ? 'השבת' : 'הפעל'), /*#__PURE__*/React.createElement(KitBtn_g, {
    variant: "danger",
    size: "sm",
    onClick: () => setConfirm(g)
  }, "\u05DE\u05D7\u05E7"))))))), confirm && /*#__PURE__*/React.createElement(KitDialog_g, {
    message: "\u05D4\u05D0\u05DD \u05DC\u05DE\u05D7\u05D5\u05E7 \u05D0\u05EA \u05D4\u05DE\u05D0\u05D1\u05D8\u05D7 \u05DC\u05E6\u05DE\u05D9\u05EA\u05D5\u05EA? \u05E4\u05E2\u05D5\u05DC\u05D4 \u05D6\u05D5 \u05D0\u05D9\u05E0\u05D4 \u05E0\u05D9\u05EA\u05E0\u05EA \u05DC\u05D1\u05D9\u05D8\u05D5\u05DC.",
    confirmLabel: "\u05DE\u05D7\u05E7",
    onConfirm: () => {
      setGuards(gs => gs.filter(x => x.id !== confirm.id));
      setConfirm(null);
      toast && toast('success', 'המאבטח נמחק');
    },
    onCancel: () => setConfirm(null)
  }));
}
window.GuardsScreen = GuardsScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/GuardsScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/admin/LoginScreen.jsx
try { (() => {
// Admin login — centered card with indigo radial glow behind it.
const {
  Card: KitCard_l,
  Button: KitBtn_l,
  Field: KitField_l,
  TextInput: KitInput_l,
  Alert: KitAlert_l
} = window.IlutsimDesignSystem_f4254f;
function LoginScreen({
  onLogin
}) {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');
  const submit = () => {
    if (!username || !password) {
      setError('שם משתמש או סיסמה שגויים');
      return;
    }
    setError('');
    onLogin && onLogin();
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "login-page"
  }, /*#__PURE__*/React.createElement(KitCard_l, {
    className: "login-card",
    style: {
      padding: '2.5rem'
    }
  }, /*#__PURE__*/React.createElement("h2", null, "\u05DB\u05E0\u05D9\u05E1\u05EA \u05DE\u05E0\u05D4\u05DC"), error && /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: '1rem'
    }
  }, /*#__PURE__*/React.createElement(KitAlert_l, {
    tone: "error"
  }, error)), /*#__PURE__*/React.createElement(KitField_l, {
    label: "\u05E9\u05DD \u05DE\u05E9\u05EA\u05DE\u05E9"
  }, /*#__PURE__*/React.createElement(KitInput_l, {
    value: username,
    onChange: e => setUsername(e.target.value)
  })), /*#__PURE__*/React.createElement(KitField_l, {
    label: "\u05E1\u05D9\u05E1\u05DE\u05D4"
  }, /*#__PURE__*/React.createElement(KitInput_l, {
    type: "password",
    value: password,
    onChange: e => setPassword(e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: '0.5rem'
    }
  }, /*#__PURE__*/React.createElement(KitBtn_l, {
    variant: "primary",
    block: true,
    onClick: submit
  }, "\u05D4\u05EA\u05D7\u05D1\u05E8"))));
}
window.LoginScreen = LoginScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/LoginScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/admin/Navbar.jsx
try { (() => {
// Admin navbar — brand wordmark + nav links + logout.
const {
  Button: KitButton_nav
} = window.IlutsimDesignSystem_f4254f;
function KitNavbar({
  current,
  onNavigate
}) {
  const links = [{
    id: 'guards',
    label: 'מאבטחים'
  }, {
    id: 'weeks',
    label: 'שבועות'
  }, {
    id: 'submissions',
    label: 'דיווחים'
  }, {
    id: 'events',
    label: 'אירועים'
  }, {
    id: 'export',
    label: 'ייצוא'
  }, {
    id: 'settings',
    label: 'הגדרות'
  }];
  return /*#__PURE__*/React.createElement("nav", {
    className: "navbar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "navbar-brand"
  }, "\u05E0\u05D9\u05D4\u05D5\u05DC \u05DE\u05E2\u05E8\u05DB\u05EA \u05D0\u05D9\u05DC\u05D5\u05E6\u05D9\u05DD"), /*#__PURE__*/React.createElement("div", {
    className: "navbar-links"
  }, links.map(l => /*#__PURE__*/React.createElement("a", {
    key: l.id,
    className: current === l.id ? 'active' : '',
    onClick: () => onNavigate(l.id)
  }, l.label)), /*#__PURE__*/React.createElement(KitButton_nav, {
    variant: "secondary",
    size: "sm",
    onClick: () => onNavigate('login')
  }, "\u05D4\u05EA\u05E0\u05EA\u05E7")));
}
window.KitNavbar = KitNavbar;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/Navbar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/admin/SubmissionsScreen.jsx
try { (() => {
// Submissions overview — who submitted for the open week, expandable per-guard
// availability detail.
const {
  Badge: KitBadge_s,
  Select: KitSelect_s,
  Button: KitBtn_s
} = window.IlutsimDesignSystem_f4254f;
function SubmissionsScreen() {
  const {
    submissions,
    DAY_NAMES,
    SHIFT_LABELS
  } = window.KitData;
  const [expanded, setExpanded] = React.useState(1);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-header"
  }, /*#__PURE__*/React.createElement("h2", null, "\u05D3\u05D9\u05D5\u05D5\u05D7\u05D9\u05DD \u05E9\u05D4\u05EA\u05E7\u05D1\u05DC\u05D5")), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 280,
      marginBottom: '1rem'
    }
  }, /*#__PURE__*/React.createElement(KitSelect_s, {
    defaultValue: "24"
  }, /*#__PURE__*/React.createElement("option", {
    value: "24"
  }, "\u05E9\u05D1\u05D5\u05E2 25 (\u05E4\u05EA\u05D5\u05D7)"), /*#__PURE__*/React.createElement("option", {
    value: "23"
  }, "\u05E9\u05D1\u05D5\u05E2 24 (\u05E0\u05E2\u05D5\u05DC)"))), /*#__PURE__*/React.createElement("table", {
    className: "data-table"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "\u05E9\u05DD \u05DE\u05DC\u05D0"), /*#__PURE__*/React.createElement("th", null, "\u05E1\u05D8\u05D8\u05D5\u05E1"), /*#__PURE__*/React.createElement("th", null, "\u05EA\u05D0\u05E8\u05D9\u05DA \u05D4\u05D2\u05E9\u05D4"), /*#__PURE__*/React.createElement("th", null, "\u05E6\u05E4\u05D4 \u05D1\u05E4\u05D9\u05E8\u05D5\u05D8"))), /*#__PURE__*/React.createElement("tbody", null, submissions.map(s => {
    const isOpen = expanded === s.user_id;
    const hasDetail = s.submitted_at && s.days.length > 0;
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: s.user_id
    }, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", null, s.full_name), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement(KitBadge_s, {
      tone: s.submitted_at ? 'submitted' : 'missing'
    }, s.submitted_at ? 'שלח' : 'לא שלח')), /*#__PURE__*/React.createElement("td", null, s.submitted_at ? new Date(s.submitted_at).toLocaleString('he-IL') : '—'), /*#__PURE__*/React.createElement("td", null, hasDetail ? /*#__PURE__*/React.createElement(KitBtn_s, {
      variant: "ghost",
      size: "sm",
      onClick: () => setExpanded(isOpen ? null : s.user_id)
    }, isOpen ? 'הסתר' : 'הצג') : /*#__PURE__*/React.createElement("span", {
      className: "text-muted"
    }, "\u2014"))), isOpen && hasDetail && /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
      colSpan: 4
    }, /*#__PURE__*/React.createElement("div", {
      className: "detail-content"
    }, s.days.map((day, idx) => /*#__PURE__*/React.createElement("div", {
      className: "detail-day",
      key: idx
    }, /*#__PURE__*/React.createElement("strong", null, DAY_NAMES[idx]), day.shift_windows.length > 0 ? /*#__PURE__*/React.createElement("ul", null, day.shift_windows.map((sw, i) => /*#__PURE__*/React.createElement("li", {
      key: i
    }, SHIFT_LABELS[sw.shift_type], ": ", sw.start_time, "\u2013", sw.end_time))) : /*#__PURE__*/React.createElement("span", {
      className: "text-muted",
      style: {
        fontSize: 'var(--fs-xs)'
      }
    }, " \u05DC\u05D0 \u05D6\u05DE\u05D9\u05DF")))), s.general_notes && /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: '0.6rem',
        fontSize: 'var(--fs-sm)',
        color: 'var(--text-muted)'
      }
    }, /*#__PURE__*/React.createElement("strong", null, "\u05D4\u05E2\u05E8\u05D5\u05EA:"), " ", s.general_notes))));
  }))));
}
window.SubmissionsScreen = SubmissionsScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/SubmissionsScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/admin/WeeksScreen.jsx
try { (() => {
// Weeks management — lifecycle cards (closed → open → locked → published).
const {
  Button: KitBtn_w,
  Badge: KitBadge_w,
  Card: KitCard_w,
  Dialog: KitDialog_w
} = window.IlutsimDesignSystem_f4254f;
const WEEK_CFG = {
  closed: {
    tone: 'closed',
    icon: '⏳',
    label: 'סגור'
  },
  open: {
    tone: 'open',
    icon: '🔓',
    label: 'פתוח להגשה'
  },
  locked: {
    tone: 'locked',
    icon: '🔒',
    label: 'סגור להגשה'
  },
  published: {
    tone: 'published',
    icon: '📢',
    label: 'פורסם'
  }
};
function WeekActions({
  status,
  onAction
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "week-card-buttons"
  }, (status === 'locked' || status === 'closed') && /*#__PURE__*/React.createElement(KitBtn_w, {
    variant: "primary",
    size: "sm",
    icon: "\uD83D\uDFE2",
    onClick: () => onAction('open')
  }, "\u05E4\u05EA\u05D7 \u05DC\u05D4\u05D2\u05E9\u05D4"), status === 'open' && /*#__PURE__*/React.createElement(KitBtn_w, {
    variant: "secondary",
    size: "sm",
    icon: "\uD83D\uDD12",
    onClick: () => onAction('lock')
  }, "\u05E0\u05E2\u05DC"), status === 'locked' && /*#__PURE__*/React.createElement(KitBtn_w, {
    variant: "success",
    size: "sm",
    icon: "\uD83D\uDCE2",
    onClick: () => onAction('publish')
  }, "\u05E4\u05E8\u05E1\u05DD"), status !== 'published' && /*#__PURE__*/React.createElement(KitBtn_w, {
    variant: "danger",
    size: "sm",
    icon: "\uD83D\uDDD1\uFE0F",
    onClick: () => onAction('delete')
  }, "\u05DE\u05D7\u05E7"));
}
function WeeksScreen({
  toast
}) {
  const [weeks, setWeeks] = React.useState(() => window.KitData.weeks.map(w => ({
    ...w
  })));
  const [confirm, setConfirm] = React.useState(null);
  const setStatus = (id, status, msg) => {
    setWeeks(ws => ws.map(w => w.id === id ? {
      ...w,
      status
    } : w));
    toast && toast('success', msg);
  };
  const handleAction = (week, action) => {
    if (action === 'open') setStatus(week.id, 'open', 'השבוע נפתח להגשה בהצלחה');
    if (action === 'lock') setStatus(week.id, 'locked', 'השבוע ננעל בהצלחה');
    if (action === 'publish') setStatus(week.id, 'published', 'השבוע פורסם בהצלחה — שבוע חדש נוצר אוטומטית');
    if (action === 'delete') setConfirm(week);
  };
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-header"
  }, /*#__PURE__*/React.createElement("h2", null, "\u05E0\u05D9\u05D4\u05D5\u05DC \u05E9\u05D1\u05D5\u05E2\u05D5\u05EA"), /*#__PURE__*/React.createElement(KitBtn_w, {
    variant: "outline",
    size: "sm"
  }, "\u05E8\u05E2\u05E0\u05D5\u05DF")), /*#__PURE__*/React.createElement("div", {
    className: "week-cards"
  }, weeks.map(w => {
    const cfg = WEEK_CFG[w.status];
    return /*#__PURE__*/React.createElement(KitCard_w, {
      key: w.id,
      interactive: true
    }, /*#__PURE__*/React.createElement("div", {
      className: "week-card-header"
    }, /*#__PURE__*/React.createElement("span", {
      className: "week-card-date"
    }, "\uD83D\uDCC5 ", w.start_date, " \u2014 ", w.end_date), /*#__PURE__*/React.createElement("span", {
      className: "week-card-label"
    }, w.week_label)), /*#__PURE__*/React.createElement("span", {
      className: "week-card-submissions"
    }, w.submission_count, " \u05D4\u05D2\u05E9\u05D5\u05EA"), /*#__PURE__*/React.createElement("div", {
      className: "week-card-actions"
    }, /*#__PURE__*/React.createElement(KitBadge_w, {
      tone: cfg.tone,
      icon: cfg.icon
    }, cfg.label), /*#__PURE__*/React.createElement(WeekActions, {
      status: w.status,
      onAction: a => handleAction(w, a)
    })));
  })), confirm && /*#__PURE__*/React.createElement(KitDialog_w, {
    title: "\u05DE\u05D7\u05E7 \u05E9\u05D1\u05D5\u05E2",
    message: "\u05D4\u05D0\u05DD \u05DC\u05DE\u05D7\u05D5\u05E7 \u05D0\u05EA \u05D4\u05E9\u05D1\u05D5\u05E2? \u05E4\u05E2\u05D5\u05DC\u05D4 \u05D6\u05D5 \u05D0\u05D9\u05E0\u05D4 \u05E0\u05D9\u05EA\u05E0\u05EA \u05DC\u05D1\u05D9\u05D8\u05D5\u05DC.",
    confirmLabel: "\u05DE\u05D7\u05E7",
    onConfirm: () => {
      setWeeks(ws => ws.filter(w => w.id !== confirm.id));
      setConfirm(null);
      toast && toast('success', 'השבוע נמחק בהצלחה');
    },
    onCancel: () => setConfirm(null)
  }));
}
window.WeeksScreen = WeeksScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/WeeksScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/admin/data.js
try { (() => {
// Mock data for the Ilutsim admin UI kit — Hebrew, realistic shapes mirroring
// the live API (weeks lifecycle, guards with roles, weekly submissions).
window.KitData = {
  weeks: [{
    id: 24,
    start_date: '15.06.2026',
    end_date: '21.06.2026',
    week_label: 'שבוע 25',
    status: 'open',
    submission_count: 9
  }, {
    id: 23,
    start_date: '08.06.2026',
    end_date: '14.06.2026',
    week_label: 'שבוע 24',
    status: 'locked',
    submission_count: 12
  }, {
    id: 22,
    start_date: '01.06.2026',
    end_date: '07.06.2026',
    week_label: 'שבוע 23',
    status: 'published',
    submission_count: 12
  }, {
    id: 25,
    start_date: '22.06.2026',
    end_date: '28.06.2026',
    week_label: 'שבוע 26',
    status: 'closed',
    submission_count: 0
  }],
  guards: [{
    id: 1,
    first_name: 'יוסף',
    last_name: 'כהן',
    phone_number: '052-1234567',
    role: 'AHMASH',
    is_active: true
  }, {
    id: 2,
    first_name: 'דניאל',
    last_name: 'לוי',
    phone_number: '054-7654321',
    role: 'BASIC_GUARD',
    is_active: true
  }, {
    id: 3,
    first_name: 'מאיה',
    last_name: 'פרץ',
    phone_number: '050-9988776',
    role: 'LEVEL_B',
    is_active: true
  }, {
    id: 4,
    first_name: 'אבי',
    last_name: 'מזרחי',
    phone_number: '058-4455667',
    role: 'NINE_HOURS',
    is_active: false
  }, {
    id: 5,
    first_name: 'נועה',
    last_name: 'ביטון',
    phone_number: '053-2233445',
    role: 'CHECKER',
    is_active: true
  }, {
    id: 6,
    first_name: 'איתי',
    last_name: 'אזולאי',
    phone_number: '050-1122334',
    role: 'UNARMED',
    is_active: true
  }],
  // submissions for the open week (24)
  submissions: [{
    user_id: 1,
    full_name: 'יוסף כהן',
    submitted_at: '2026-06-12T09:14:00',
    days: [{
      shift_windows: [{
        shift_type: 'morning',
        start_time: '07:00',
        end_time: '16:30'
      }]
    }, {
      shift_windows: [{
        shift_type: 'morning',
        start_time: '07:00',
        end_time: '16:30'
      }]
    }, {
      shift_windows: []
    }, {
      shift_windows: [{
        shift_type: 'night',
        start_time: '23:00',
        end_time: '07:00'
      }]
    }, {
      shift_windows: [{
        shift_type: 'afternoon',
        start_time: '15:00',
        end_time: '23:00'
      }]
    }, {
      shift_windows: []
    }, {
      shift_windows: []
    }],
    general_notes: 'מעדיף בקרים בתחילת השבוע'
  }, {
    user_id: 2,
    full_name: 'דניאל לוי',
    submitted_at: '2026-06-12T18:02:00',
    days: [],
    general_notes: ''
  }, {
    user_id: 3,
    full_name: 'מאיה פרץ',
    submitted_at: '2026-06-13T07:40:00',
    days: [],
    general_notes: ''
  }, {
    user_id: 5,
    full_name: 'נועה ביטון',
    submitted_at: null,
    days: [],
    general_notes: ''
  }, {
    user_id: 6,
    full_name: 'איתי אזולאי',
    submitted_at: null,
    days: [],
    general_notes: ''
  }],
  ROLE_LABELS: {
    AHMASH: 'אחמ"ש',
    BASIC_GUARD: 'מאבטח בסיסי',
    LEVEL_B: "מאבטח רמה ב'",
    NINE_HOURS: 'מאבטח 9 שעות',
    UNARMED: 'לא חמוש',
    CHECKER: 'בודק'
  },
  DAY_NAMES: ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'],
  SHIFT_LABELS: {
    morning: 'בוקר',
    afternoon: 'ערב',
    night: 'לילה'
  }
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/data.js", error: String((e && e.message) || e) }); }

__ds_ns.Alert = __ds_scope.Alert;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.Field = __ds_scope.Field;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.TextInput = __ds_scope.TextInput;

__ds_ns.Textarea = __ds_scope.Textarea;

})();
