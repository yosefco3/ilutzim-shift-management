/**
 * Hook for an admin to fill a guard's weekly constraints on their behalf
 * (e.g. guards without Telegram). Mirrors the guard-side useSubmission state
 * shape (days keyed by day_index with a { morning, afternoon, night } shifts
 * map) but talks to the admin API and lets the admin pick any week.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  fetchGuard,
  fetchWeeks,
  fetchGuardSubmission,
  createGuardSubmission,
} from '../api/adminApiClient';
import { get as guardGet } from '../api/guardApiClient.js';
import {
  SHIFT_DEFAULTS,
  SHIFT_TYPES,
  validateShiftHours,
} from '../utils/guardMessages.js';

/** Create a default shifts map (all off) using supplied default hours. */
function makeShifts(defaults) {
  const map = {};
  for (const st of SHIFT_TYPES) {
    const d = defaults[st] || { from_hour: '', to_hour: '' };
    map[st] = { active: false, from_hour: d.from_hour, to_hour: d.to_hour };
  }
  return map;
}

/** Build the 7 empty day rows, pre-filling any existing submission for the week. */
function buildDays(defaults, existingSub, weekStart) {
  const toHHMM = (t) => (typeof t === 'string' ? t.slice(0, 5) : '');
  const byIndex = {};
  if (weekStart && Array.isArray(existingSub?.days)) {
    for (const sd of existingSub.days) {
      const idx = Math.round((new Date(sd.date) - weekStart) / 86400000);
      byIndex[idx] = sd;
    }
  }

  return Array.from({ length: 7 }, (_, dayIndex) => {
    const shifts = makeShifts(defaults);
    const existingDay = byIndex[dayIndex];
    if (existingDay?.shift_windows) {
      for (const sw of existingDay.shift_windows) {
        if (shifts[sw.shift_type]) {
          shifts[sw.shift_type] = {
            active: true,
            from_hour: toHHMM(sw.start_time),
            to_hour: toHHMM(sw.end_time),
          };
        }
      }
    }
    return { day_index: dayIndex, blocked: false, shifts };
  });
}

export function useAdminConstraints(guardId) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [guard, setGuard] = useState(null);
  const [weeks, setWeeks] = useState([]);
  const [selectedWeekId, setSelectedWeekId] = useState('');
  const [days, setDays] = useState([]);
  const [notes, setNotes] = useState('');
  const [shiftDefaults, setShiftDefaults] = useState(SHIFT_DEFAULTS);

  // ── Initial load: guard, weeks, shift defaults ───────────────────
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [guardData, weeksData] = await Promise.all([
          fetchGuard(guardId),
          fetchWeeks(),
        ]);

        // Shift defaults are public; fall back to static defaults on failure.
        let defaults = SHIFT_DEFAULTS;
        const { data: defData } = await guardGet('/submissions/shift-defaults', '');
        if (defData) {
          const mapped = {};
          for (const key of Object.keys(defData)) {
            const short = key.replace('shift_default_', '');
            if (SHIFT_TYPES.includes(short)) mapped[short] = defData[key];
          }
          if (Object.keys(mapped).length === 3) defaults = mapped;
        }

        if (cancelled) return;
        setGuard(guardData);
        setWeeks(weeksData || []);
        setShiftDefaults(defaults);

        // Default to the open week, else the most recent one.
        const open = (weeksData || []).find((w) => w.status === 'open');
        const initial = open || (weeksData || [])[0];
        setSelectedWeekId(initial ? initial.id : '');
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (guardId) load();
    return () => {
      cancelled = true;
    };
  }, [guardId]);

  // ── When the selected week changes, (re)build the day rows ───────
  useEffect(() => {
    let cancelled = false;
    async function loadWeek() {
      if (!selectedWeekId) {
        setDays([]);
        return;
      }
      setSaved(false);
      const week = weeks.find((w) => w.id === selectedWeekId);
      const weekStart = week?.start_date ? new Date(week.start_date) : null;

      let existing = null;
      try {
        existing = await fetchGuardSubmission(guardId, selectedWeekId);
      } catch {
        // No prior submission / fetch error → start blank.
      }
      if (cancelled) return;
      setDays(buildDays(shiftDefaults, existing, weekStart));
      setNotes(existing?.general_notes ?? '');
    }
    loadWeek();
    return () => {
      cancelled = true;
    };
  }, [selectedWeekId, weeks, guardId, shiftDefaults]);

  const toggleShift = useCallback(
    (dayIndex, shiftType) => {
      setDays((prev) =>
        prev.map((d) => {
          if (d.day_index !== dayIndex) return d;
          const shifts = { ...d.shifts };
          const current = shifts[shiftType];
          const def = shiftDefaults[shiftType] || { from_hour: '', to_hour: '' };
          shifts[shiftType] = {
            ...current,
            active: !current.active,
            from_hour: current.from_hour || def.from_hour,
            to_hour: current.to_hour || def.to_hour,
          };
          return { ...d, shifts };
        }),
      );
    },
    [shiftDefaults],
  );

  const setShiftHours = useCallback((dayIndex, shiftType, from, to) => {
    setDays((prev) =>
      prev.map((d) => {
        if (d.day_index !== dayIndex) return d;
        const shifts = { ...d.shifts };
        shifts[shiftType] = { ...shifts[shiftType], from_hour: from, to_hour: to };
        return { ...d, shifts };
      }),
    );
  }, []);

  // A LOCKED week is final — its constraints can no longer be edited (mirrors the
  // backend rule). Admins may still edit while the week is closed/open.
  // (Kept the name ``isPublished`` to match the admin "publish" terminology.)
  const selectedWeek = weeks.find((w) => w.id === selectedWeekId) || null;
  const isPublished = selectedWeek?.status === 'locked';

  const submit = useCallback(async () => {
    if (!selectedWeekId) return false;
    const week = weeks.find((w) => w.id === selectedWeekId);
    if (week?.status === 'locked') return false;

    // Hard time-range validation — block before hitting the server.
    const timeError = validateShiftHours(days);
    if (timeError) {
      setError(timeError);
      return false;
    }

    setError(null);
    setSaved(false);
    setSaving(true);

    const payload = {
      user_id: guardId,
      week_id: selectedWeekId,
      general_notes: notes || null,
      days: days.map((d) => ({
        day_index: d.day_index,
        shifts: SHIFT_TYPES.filter(
          (st) => d.shifts[st].active && d.shifts[st].from_hour && d.shifts[st].to_hour,
        ).map((st) => ({
          shift_type: st,
          from_hour: d.shifts[st].from_hour,
          to_hour: d.shifts[st].to_hour,
        })),
      })),
    };

    try {
      await createGuardSubmission(payload);
      setSaved(true);
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setSaving(false);
    }
  }, [selectedWeekId, guardId, notes, days, weeks]);

  return {
    loading,
    error,
    saving,
    saved,
    guard,
    weeks,
    selectedWeekId,
    setSelectedWeekId,
    selectedWeek,
    isPublished,
    days,
    notes,
    setNotes,
    toggleShift,
    setShiftHours,
    submit,
  };
}
