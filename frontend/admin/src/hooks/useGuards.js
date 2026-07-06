import { useState, useEffect, useCallback } from 'react';
import { fetchGuards, createGuard, updateGuard, deleteGuard } from '../api/adminApiClient';

export function useGuards() {
  const [guards, setGuards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchGuards();
      setGuards(Array.isArray(data) ? data : data.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async (guardData) => {
    const created = await createGuard(guardData);
    setGuards((prev) => [...prev, created]);
    return created;
  };

  const update = async (id, guardData) => {
    const updated = await updateGuard(id, guardData);
    setGuards((prev) => prev.map((g) => (g.id === id ? updated : g)));
    return updated;
  };

  const remove = async (id) => {
    await deleteGuard(id);
    setGuards((prev) => prev.filter((g) => g.id !== id));
  };

  const toggle = async (id, isActive) => {
    const updated = await updateGuard(id, { is_active: isActive });
    setGuards((prev) => prev.map((g) => (g.id === id ? updated : g)));
    return updated;
  };

  return { guards, loading, error, reload: load, createGuard: add, updateGuard: update, deleteGuard: remove, toggleGuard: toggle };
}