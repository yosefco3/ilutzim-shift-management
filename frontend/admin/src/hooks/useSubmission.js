/**
 * Hook to load, edit, and submit a weekly constraints form.
 * Each day holds a shifts map { morning, afternoon, night } → { active, from_hour, to_hour }.
 *
 * Default hours come from the server (editable by admin via /admin/settings),
 * falling back to SHIFT_DEFAULTS from guardMessages.js.
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { get, post } from "../api/guardApiClient.js";
import {
  SHIFT_DEFAULTS,
  SHIFT_TYPES,
  messages,
  validateShiftHours,
} from "../utils/guardMessages.js";

/** Longest run of consecutive day_index values that have any active shift. */
function maxConsecutiveActiveDays(days) {
  const sorted = [...days].sort((a, b) => a.day_index - b.day_index);
  let run = 0;
  let max = 0;
  for (const d of sorted) {
    const any = SHIFT_TYPES.some((t) => d.shifts?.[t]?.active);
    run = any ? run + 1 : 0;
    if (run > max) max = run;
  }
  return max;
}

/** Build soft (non-blocking) warnings from the form state vs. admin thresholds. */
export function computeWarnings(days, rules) {
  if (!rules) return [];
  const out = [];
  const total = days.reduce(
    (n, d) => n + SHIFT_TYPES.filter((t) => d.shifts?.[t]?.active).length,
    0,
  );
  const nights = days.filter((d) => d.shifts?.night?.active).length;
  const evenings = days.filter((d) => d.shifts?.afternoon?.active).length; // afternoon = ערב
  const consec = maxConsecutiveActiveDays(days);

  if (total < rules.min_shifts_per_guard)
    out.push(messages.WARN_MIN_SHIFTS(total, rules.min_shifts_per_guard));
  if (nights < rules.min_nights)
    out.push(messages.WARN_MIN_NIGHTS(nights, rules.min_nights));
  if (evenings < rules.min_evenings)
    out.push(messages.WARN_MIN_EVENINGS(evenings, rules.min_evenings));
  if (consec > rules.max_consecutive_days)
    out.push(messages.WARN_MAX_CONSEC(consec, rules.max_consecutive_days));
  return out;
}

/** Create a default shifts map using supplied defaults. */
function makeShifts(defaults) {
  const map = {};
  for (const st of SHIFT_TYPES) {
    const d = defaults[st] || { from_hour: "", to_hour: "" };
    map[st] = { active: false, from_hour: d.from_hour, to_hour: d.to_hour };
  }
  return map;
}

/**
 * @param {string} initData - Telegram initData for auth
 */
export function useSubmission(initData) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [week, setWeek] = useState(null);
  const [days, setDays] = useState([]);
  const [notes, setNotes] = useState("");
  const [shiftDefaults, setShiftDefaults] = useState(SHIFT_DEFAULTS);
  const [rules, setRules] = useState(null);

  // ── Dev mode flag ──────────────────────────────────────────────
  const isDevMode = initData === "__DEV_MODE__";

  // ── Fetch constraint-rule thresholds (soft warnings; silent on failure) ──
  useEffect(() => {
    if (!initData) return;
    get("/submissions/constraint-rules", initData).then(({ data, error: err }) => {
      if (!err && data) setRules(data);
    });
  }, [initData]);

  // ── Fetch shift defaults from server (fallback to static SHIFT_DEFAULTS)
  useEffect(() => {
    if (!initData) return;
    get("/submissions/shift-defaults", initData).then(({ data, error: err }) => {
      if (!err && data) {
        // Server returns { shift_default_morning: {from_hour, to_hour}, ... }
        // Map keys: shift_default_morning → morning
        const mapped = {};
        for (const key of Object.keys(data)) {
          const short = key.replace("shift_default_", "");
          if (SHIFT_TYPES.includes(short)) {
            mapped[short] = data[key];
          }
        }
        if (Object.keys(mapped).length === 3) {
          setShiftDefaults(mapped);
        }
      }
    });
  }, [initData]);

  // ── Load current week + existing submission ──────────────────
  useEffect(() => {
    if (!initData) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      // Fetch shift defaults FIRST so they're available for building initial days
      let finalDefaults = SHIFT_DEFAULTS;
      const defaultsResult = await get("/submissions/shift-defaults", initData);
      if (!defaultsResult.error && defaultsResult.data) {
        const mapped = {};
        for (const key of Object.keys(defaultsResult.data)) {
          const short = key.replace("shift_default_", "");
          if (SHIFT_TYPES.includes(short)) {
            mapped[short] = defaultsResult.data[key];
          }
        }
        if (Object.keys(mapped).length === 3) {
          finalDefaults = mapped;
          setShiftDefaults(mapped);
        }
      }

      const subResult = await get("/submissions/current-week", initData);

      if (subResult.error || !subResult.data) {
        if (isDevMode) {
          setError(
            "No open week found. Open a week from the admin dashboard first, then refresh this page.",
          );
        } else {
          setError(subResult.error || "אין שבוע פתוח כרגע");
        }
        setLoading(false);
        return;
      }

      if (cancelled) return;

      const weekData = subResult.data;
      setWeek(weekData);

      // Get existing submission (may be null)
      const { data: subData } = await get(
        `/submissions/my?week_id=${weekData.id}`,
        initData,
      );

      if (cancelled) return;

      // The existing submission is keyed by `date` + `shift_windows`
      // (start_time/end_time as "HH:MM:SS"), while the form is keyed by
      // `day_index` + a shifts map ("HH:MM"). Bridge the two shapes here.
      const weekStart = weekData.start_date
        ? new Date(weekData.start_date)
        : null;
      const toHHMM = (t) => (typeof t === "string" ? t.slice(0, 5) : "");
      const submittedByIndex = {};
      if (weekStart && Array.isArray(subData?.days)) {
        for (const sd of subData.days) {
          const idx = Math.round(
            (new Date(sd.date) - weekStart) / 86400000,
          );
          submittedByIndex[idx] = sd;
        }
      }

      // Build initial form state — each day gets a shifts map
      const initialDays = (weekData.days || []).map((d) => {
        const shifts = makeShifts(finalDefaults);

        const existingDay = submittedByIndex[d.day_index];
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

        return {
          day_index: d.day_index,
          blocked: d.blocked || false,
          shifts,
        };
      });

      setDays(initialDays);
      setNotes(subData?.notes ?? subData?.general_notes ?? "");
      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [initData]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Toggle a single shift (morning / afternoon / night) ──────
  const toggleShift = useCallback(
    (dayIndex, shiftType) => {
      setDays((prev) =>
        prev.map((d) => {
          if (d.day_index !== dayIndex) return d;
          const shifts = { ...d.shifts };
          const current = shifts[shiftType];
          // When toggling ON, ensure default hours are filled
          const def = shiftDefaults[shiftType] || { from_hour: "", to_hour: "" };
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

  // ── Set custom hours for a specific shift ────────────────────
  const setShiftHours = useCallback((dayIndex, shiftType, from, to) => {
    setDays((prev) =>
      prev.map((d) => {
        if (d.day_index !== dayIndex) return d;
        const shifts = { ...d.shifts };
        shifts[shiftType] = {
          ...shifts[shiftType],
          from_hour: from,
          to_hour: to,
        };
        return { ...d, shifts };
      }),
    );
  }, []);

  // ── Submit the form ──────────────────────────────────────────
  // Returns { ok, error }. Success is declared ONLY when the backend confirms
  // it persisted the submission (a 201 carrying the saved row's id). A 2xx with
  // no submission body is treated as a failure — never a frontend-only "success".
  const submit = useCallback(async () => {
    if (!week || submitting) return { ok: false, error: null };

    // Hard time-range validation — block before hitting the server.
    const timeError = validateShiftHours(days);
    if (timeError) {
      setError(timeError);
      return { ok: false, error: timeError };
    }

    setError(null);
    setSubmitting(true);

    const payload = {
      week_id: week.id,
      general_notes: notes || null,
      days: days
        .filter((d) => !d.blocked)
        .map((d) => ({
          day_index: d.day_index,
          shifts: SHIFT_TYPES.filter(
            (st) =>
              d.shifts[st].active &&
              d.shifts[st].from_hour &&
              d.shifts[st].to_hour,
          ).map((st) => ({
            shift_type: st,
            from_hour: d.shifts[st].from_hour,
            to_hour: d.shifts[st].to_hour,
          })),
        })),
    };

    const { data, error: submitErr } = await post("/submissions", payload, initData);
    setSubmitting(false);

    if (submitErr) {
      setError(submitErr);
      return { ok: false, error: submitErr };
    }
    // The backend must echo back the saved submission (with an id). Without it
    // we have no proof the data reached the server, so we do NOT show success.
    if (!data || !data.id) {
      setError(messages.ERR_NO_CONFIRM);
      return { ok: false, error: messages.ERR_NO_CONFIRM };
    }
    return { ok: true, error: null };
  }, [week, days, notes, initData, submitting]);

  const weekStatus = week?.status || null;
  const canSubmit = weekStatus === "open";
  const isLocked = !canSubmit;

  // Soft warnings — informational only, never block submit.
  const warnings = useMemo(() => computeWarnings(days, rules), [days, rules]);

  return {
    loading,
    submitting,
    error,
    week,
    days,
    notes,
    setNotes,
    weekStatus,
    canSubmit,
    isLocked,
    warnings,
    toggleShift,
    setShiftHours,
    submit,
  };
}