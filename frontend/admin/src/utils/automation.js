/**
 * Helpers for the weeks-page automation UI: derive the auto-open/auto-lock
 * config from the settings list and format it for display.
 */
import messages from './messages';

const A = messages.weeks.automation;

// settings: list of { key, value } (value is a string; booleans are "true"/"false").
export function deriveAutomation(settings) {
  const map = Object.fromEntries((settings || []).map((s) => [s.key, s.value]));
  const block = (prefix) => ({
    enabled: map[`${prefix}_enabled`] === 'true',
    weekday: map[`${prefix}_weekday`] || '',
    time: map[`${prefix}_time`] || '',
  });
  return { autoOpen: block('auto_open'), autoLock: block('auto_lock') };
}

export function hebrewWeekday(weekday) {
  return A.weekdays[weekday] || weekday || '';
}

// "ראשון 07:00"
export function formatSchedule(weekday, time) {
  return `${hebrewWeekday(weekday)} ${time || ''}`.trim();
}
