/**
 * TimelineBar — the core visual of the attendance UI (stage 3).
 *
 * One horizontal rail on a shared hour scale: the PLANNED windows render as a
 * light background band, and the per-minute classified segments from the
 * server paint over it — covered (green), small gap (yellow hatch), big gap
 * (orange hatch), extra/beyond-plan (purple), no-show (red frame). `future`
 * segments are intentionally NOT painted: the plan background showing through
 * *is* the "not yet" state. An optional red now-line crosses the rail.
 *
 * The rail is direction:ltr (time flows left→right) inside the RTL page.
 */

const KIND_CLASS = {
  covered: 'att-seg-ok',
  gap_small: 'att-seg-gap-soft',
  gap_big: 'att-seg-gap-hard',
  extra: 'att-seg-extra',
  no_show: 'att-seg-noshow',
};

const KIND_LABEL = {
  covered: 'נוכחות',
  gap_small: 'פער קטן',
  gap_big: 'פער גדול',
  extra: 'מעבר למתוכנן',
  no_show: 'לא הגיע',
};

const hhmm = (iso) =>
  new Date(iso).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' });

export default function TimelineBar({ planned = [], segments = [], scaleStart, scaleEnd, now }) {
  const s0 = new Date(scaleStart).getTime();
  const s1 = new Date(scaleEnd).getTime();
  const span = Math.max(1, s1 - s0);
  const pct = (iso) => {
    const t = new Date(iso).getTime();
    return Math.max(0, Math.min(100, ((t - s0) / span) * 100));
  };
  const bar = (startIso, endIso) => {
    const left = pct(startIso);
    const width = Math.max(0.4, pct(endIso) - left);
    return { left: `${left}%`, width: `${width}%` };
  };

  const nowPct = now ? ((new Date(now).getTime() - s0) / span) * 100 : null;

  return (
    <div className="att-rail" dir="ltr">
      {planned.map((w, i) => (
        <div
          key={`p${i}`}
          className="att-plan-bg"
          style={bar(w.start, w.end)}
          title={`מתוכנן ${w.position_name} ${hhmm(w.start)}–${hhmm(w.end)}`}
        />
      ))}
      {segments
        .filter((s) => s.kind !== 'future')
        .map((s, i) => (
          <div
            key={`s${i}`}
            className={`att-seg ${KIND_CLASS[s.kind] || ''}`}
            style={bar(s.start, s.end)}
            title={`${KIND_LABEL[s.kind] || s.kind} ${hhmm(s.start)}–${hhmm(s.end)}`}
          />
        ))}
      {nowPct !== null && nowPct >= 0 && nowPct <= 100 && (
        <div className="att-nowline" style={{ left: `${nowPct}%` }} data-testid="att-nowline" />
      )}
    </div>
  );
}
