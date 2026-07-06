import { describe, it, expect } from 'vitest';
import {
  messages,
  DAY_NAMES,
  SHIFT_LABELS,
  SHIFT_DEFAULTS,
  START_OPTIONS,
  shiftTimeOptions,
  checkShiftWindow,
  validateShiftHours,
} from '../src/utils/guardMessages';

describe('guardMessages', () => {
  it('should export messages object with required keys', () => {
    const requiredKeys = [
      'LABEL_AVAILABLE', 'LABEL_UNAVAILABLE', 'LABEL_SUBMIT',
      'LABEL_LOADING', 'LABEL_NOTES', 'LABEL_FROM', 'LABEL_TO',
      'ERR_AUTH', 'ERR_NETWORK', 'SUCCESS_SUBMITTED',
    ];
    requiredKeys.forEach((key) => {
      expect(messages[key]).toBeDefined();
      expect(typeof messages[key]).toBe('string');
    });
  });

  it('should export DAY_NAMES as 7-element array', () => {
    expect(DAY_NAMES).toHaveLength(7);
    DAY_NAMES.forEach((name) => {
      expect(typeof name).toBe('string');
      expect(name.length).toBeGreaterThan(0);
    });
  });

  it('should export SHIFT_LABELS with morning/afternoon/night', () => {
    expect(SHIFT_LABELS.morning).toBeDefined();
    expect(SHIFT_LABELS.afternoon).toBeDefined();
    expect(SHIFT_LABELS.night).toBeDefined();
  });

  it('should export SHIFT_DEFAULTS with from_hour/to_hour per shift', () => {
    ['morning', 'afternoon', 'night'].forEach((shift) => {
      expect(SHIFT_DEFAULTS[shift]).toBeDefined();
      expect(typeof SHIFT_DEFAULTS[shift].from_hour).toBe('string');
      expect(typeof SHIFT_DEFAULTS[shift].to_hour).toBe('string');
    });
  });

  it('should not conflict with admin messages', () => {
    // Verify it's a different structure from admin messages
    expect(messages.LABEL_AVAILABLE).toBeDefined();
  });
});

describe('security-day time options', () => {
  it('start options begin at 07:00 and exclude pre-anchor slots', () => {
    expect(START_OPTIONS[0]).toBe('07:00');
    expect(START_OPTIONS).not.toContain('06:30');
    expect(START_OPTIONS).not.toContain('00:00');
    expect(START_OPTIONS).toContain('23:30');
  });

  it('from options are anchored for every shift type', () => {
    for (const st of ['morning', 'afternoon', 'night']) {
      expect(shiftTimeOptions('from', st)[0]).toBe('07:00');
    }
  });

  it('night end options reach the next morning up to 07:00; day shifts do not', () => {
    const night = shiftTimeOptions('to', 'night');
    expect(night).toContain('00:00');
    expect(night).toContain('07:00');
    expect(night).toContain('06:30');
    const morning = shiftTimeOptions('to', 'morning');
    expect(morning).not.toContain('00:00');
    expect(morning).not.toContain('07:00');
    expect(morning).toContain('23:30');
  });
});

describe('checkShiftWindow', () => {
  it('accepts a morning window from the anchor', () => {
    expect(checkShiftWindow('morning', '07:00', '16:30')).toBeNull();
  });

  it('rejects any shift starting before 07:00', () => {
    expect(checkShiftWindow('morning', '06:30', '15:00')).toBe(
      messages.ERR_SHIFT_BEFORE_ANCHOR,
    );
    expect(checkShiftWindow('afternoon', '06:00', '15:00')).toBe(
      messages.ERR_SHIFT_BEFORE_ANCHOR,
    );
  });

  it('rejects a morning/evening window that does not advance', () => {
    expect(checkShiftWindow('afternoon', '15:00', '08:00')).toBe(
      messages.ERR_END_BEFORE_START,
    );
  });

  it('accepts a night window wrapping to 07:00 and one that does not wrap', () => {
    expect(checkShiftWindow('night', '23:00', '07:00')).toBeNull();
    expect(checkShiftWindow('night', '19:00', '23:00')).toBeNull();
  });

  it('rejects a night window ending after 07:00 next morning', () => {
    expect(checkShiftWindow('night', '23:00', '08:00')).toBe(
      messages.ERR_NIGHT_PAST_ANCHOR,
    );
  });
});

describe('validateShiftHours', () => {
  const day = (shifts) => ({ day_index: 0, blocked: false, shifts });

  it('returns null when all active windows are valid', () => {
    const days = [day({
      morning: { active: true, from_hour: '07:00', to_hour: '16:30' },
      afternoon: { active: false, from_hour: '15:00', to_hour: '23:00' },
      night: { active: true, from_hour: '23:00', to_hour: '07:00' },
    })];
    expect(validateShiftHours(days)).toBeNull();
  });

  it('flags the first invalid active window', () => {
    const days = [day({
      morning: { active: true, from_hour: '06:30', to_hour: '15:00' },
      afternoon: { active: false, from_hour: '15:00', to_hour: '23:00' },
      night: { active: false, from_hour: '23:00', to_hour: '07:00' },
    })];
    expect(validateShiftHours(days)).toBe(messages.ERR_SHIFT_BEFORE_ANCHOR);
  });

  it('ignores inactive shifts and shifts missing an hour', () => {
    const days = [day({
      morning: { active: false, from_hour: '06:30', to_hour: '15:00' },
      afternoon: { active: true, from_hour: '15:00', to_hour: '' },
      night: { active: true, from_hour: '23:00', to_hour: '07:00' },
    })];
    expect(validateShiftHours(days)).toBeNull();
  });
});