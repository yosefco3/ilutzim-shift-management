/**
 * ReinforcementsReportPage — "דוח מתגברים" (/actual/report).
 *
 * Its own route (user feedback 5/7 — not inside the reinforcement creation
 * dialog): pick a cut (daily / weekly / monthly) and an anchor date, download
 * the xlsx — names, work dates and hours of every external reinforcement,
 * read from the actual board (they don't punch).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { exportReinforcementsReport } from '../api/builderApiClient';
import { useToast } from '../components/Toast';
import { triggerBlobDownload } from '../utils/download';
import messages from '../utils/messages';

// [startIso, endIso] for a report cut anchored on a date: the day itself, its
// Sunday-Saturday week, or its calendar month.
export function reportRange(mode, anchorIso) {
  const anchor = new Date(`${anchorIso}T00:00:00`);
  const iso = (d) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  };
  if (mode === 'daily') return [anchorIso, anchorIso];
  if (mode === 'weekly') {
    const sunday = new Date(anchor);
    sunday.setDate(anchor.getDate() - anchor.getDay()); // getDay(): Sunday = 0
    const saturday = new Date(sunday);
    saturday.setDate(sunday.getDate() + 6);
    return [iso(sunday), iso(saturday)];
  }
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  return [iso(first), iso(last)];
}

const fmtDate = (iso) => {
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
};

export default function ReinforcementsReportPage() {
  const m = messages.actualBoard.reinforcements;
  const toast = useToast();
  const [mode, setMode] = useState('monthly');
  const [anchor, setAnchor] = useState(() => new Date().toISOString().slice(0, 10));
  const [downloading, setDownloading] = useState(false);

  const [start, end] = reportRange(mode, anchor);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const blob = await exportReinforcementsReport(start, end);
      triggerBlobDownload(blob, `reinforcements_${start}_${end}.xlsx`);
    } catch (err) {
      toast.error(err?.message || messages.common.error);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h2>📊 {m.reportTitle}</h2>
      </div>
      <p className="page-subtitle">{m.reportHint}</p>

      <div className="reinforcement-report-page">
        <div className="reinforcement-report-controls">
          <label>
            {m.reportCut}
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="daily">{m.reportModeDaily}</option>
              <option value="weekly">{m.reportModeWeekly}</option>
              <option value="monthly">{m.reportModeMonthly}</option>
            </select>
          </label>
          <label>
            {m.reportDate}
            <input
              type="date"
              value={anchor}
              onChange={(e) => setAnchor(e.target.value)}
            />
          </label>
        </div>

        <p className="reinforcement-report-range">
          {m.reportRangeLabel}: {fmtDate(start)} – {fmtDate(end)}
        </p>

        <button
          type="button"
          className="btn btn-primary"
          disabled={downloading}
          onClick={handleDownload}
        >
          ⬇️ {m.reportDownload}
        </button>

        <p className="reinforcement-hint">
          <Link to="/actual">{m.backToBoard}</Link>
        </p>
      </div>
    </div>
  );
}
