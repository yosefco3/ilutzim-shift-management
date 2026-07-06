import { useState, useEffect, useCallback, useMemo } from 'react';
import { fetchSettings, updateSettings } from '../api/adminApiClient';

/**
 * Loads system settings as a list of {key, value, description} and keeps a local
 * editable draft. Edits stay client-side until save() PUTs the changed keys.
 */
export function useSettings() {
  const [settings, setSettings] = useState([]);
  const [draft, setDraft] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const applyList = useCallback((data) => {
    const list = Array.isArray(data) ? data : [];
    setSettings(list);
    setDraft(Object.fromEntries(list.map((s) => [s.key, s.value])));
  }, []);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      applyList(await fetchSettings());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [applyList]);

  useEffect(() => { load(); }, [load]);

  const setValue = useCallback((key, value) => {
    setDraft((d) => ({ ...d, [key]: value }));
  }, []);

  const dirty = useMemo(
    () => settings.some((s) => draft[s.key] !== s.value),
    [settings, draft],
  );

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const changed = {};
      for (const s of settings) {
        if (draft[s.key] !== s.value) changed[s.key] = draft[s.key];
      }
      applyList(await updateSettings(changed));
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setSaving(false);
    }
  }, [settings, draft, applyList]);

  return { settings, draft, loading, saving, error, dirty, setValue, save, reload: load };
}
