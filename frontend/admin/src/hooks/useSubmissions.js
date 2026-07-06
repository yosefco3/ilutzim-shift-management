import { useState, useEffect, useCallback } from 'react';
import {
  fetchSubmissions,
  fetchSubmissionsDetailed,
  acknowledgeSubmissionViolation,
} from '../api/adminApiClient';

export function useSubmissions(weekId, { detailed = false } = {}) {
  const [submissions, setSubmissions] = useState([]);
  const [detailedData, setDetailedData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!weekId) {
      setSubmissions([]);
      setDetailedData(null);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        setError(null);

        const data = await fetchSubmissions(weekId);
        if (!cancelled) {
          setSubmissions(Array.isArray(data) ? data : data.items || []);
        }

        if (detailed) {
          const detailedResult = await fetchSubmissionsDetailed(weekId);
          if (!cancelled) {
            setDetailedData(detailedResult);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [weekId, detailed]);

  // Acknowledge (or clear) a submission's rule violations. Updates the matching
  // row in detailedData in place so the violation marker reflects the new state
  // without a full refetch.
  const acknowledgeViolation = useCallback(
    async (submissionId, acknowledged = true) => {
      const updated = await acknowledgeSubmissionViolation(submissionId, acknowledged);
      setDetailedData((prev) => {
        if (!prev?.submitted) return prev;
        return {
          ...prev,
          submitted: prev.submitted.map((s) =>
            s.id === submissionId
              ? { ...s, violation_acknowledged: updated.violation_acknowledged }
              : s,
          ),
        };
      });
      return updated;
    },
    [],
  );

  return { submissions, detailedData, loading, error, acknowledgeViolation };
}