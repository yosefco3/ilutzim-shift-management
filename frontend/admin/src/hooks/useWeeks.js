import { useState, useEffect, useCallback } from 'react';
import { fetchWeeks, createWeek, updateWeekStatus, sendWeekReminders, openWeek, publishWeek, deleteWeek } from '../api/adminApiClient';

export function useWeeks() {
  const [weeks, setWeeks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchWeeks();
      setWeeks(Array.isArray(data) ? data : data.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async (weekData) => {
    const created = await createWeek(weekData);
    setWeeks((prev) => [...prev, created]);
    return created;
  };

  const setStatus = async (id, status) => {
    const updated = await updateWeekStatus(id, status);
    setWeeks((prev) => prev.map((w) => (w.id === id ? { ...w, ...updated } : w)));
    return updated;
  };

  const remind = async (id) => {
    return sendWeekReminders(id);
  };

  const openForSubmission = async (id) => {
    const updated = await openWeek(id);
    setWeeks((prev) => prev.map((w) => (w.id === id ? { ...w, ...updated } : w)));
    return updated;
  };

  // Silent re-fetch (no loading spinner) — used after publish to pull the
  // updated published_at into the list (which flips the button to "re-publish").
  const refreshSilently = useCallback(async () => {
    try {
      const data = await fetchWeeks();
      setWeeks(Array.isArray(data) ? data : data.items || []);
    } catch {
      // keep current state on failure; the optimistic update still applied
    }
  }, []);

  // Returns the broadcast summary { sent, skipped, total, republished } — NOT a
  // week — so we don't merge it into the week object. The server keeps the week
  // CLOSED and only stamps published_at; refreshSilently pulls it into the list.
  const publish = async (id) => {
    const summary = await publishWeek(id);
    await refreshSilently();
    return summary;
  };

  const removeWeek = async (id) => {
    await deleteWeek(id);
    setWeeks((prev) => prev.filter((w) => w.id !== id));
  };

  return { weeks, loading, error, reload: load, addWeek: add, setStatus, remind, openForSubmission, publish, deleteWeek: removeWeek };
}
