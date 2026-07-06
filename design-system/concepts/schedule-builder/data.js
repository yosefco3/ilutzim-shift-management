// Demo data for the schedule-builder concept. Positions per shift, a guard pool
// with weekly availability windows + attributes. Names/positions echo the real
// hand-built sheet (סידור עבודה שבועי).
//
// Day index: 0=ראשון … 6=שבת.  Times "HH:MM"; a night window like "23:00-07:00"
// wraps past midnight (the app adds 24h to the end when end<=start).

window.SB = (function () {
  // ── Attribute keys → Hebrew labels ──────────────────────────────
  const ATTRS = {
    armed:   'חמוש',
    roni:    'רוני',
    vehicle: 'רכב עירייה',
    walking: 'הליכה מרובה',
  };

  // ── Positions (עמדות) per shift. requires: attribute keys. ───────
  // activeDays omitted = all 7 days.
  const POSITIONS = {
    morning: [
      { id: 'm_ahmash', name: 'א. אחמ"ש',  hours: '07:00-15:00', requires: ['armed'] },
      { id: 'm_arnona', name: 'ארנונה',     hours: '07:30-15:00', requires: [], activeDays: [0,1,2,3,4] },
      { id: 'm_haml',   name: 'חמ"ל',        hours: '07:00-15:00', requires: [] },
      { id: 'm_floor6', name: 'קומה 6',      hours: '07:00-15:00', requires: [] },
      { id: 'm_patrol1',name: 'סייר 1',      hours: '07:00-15:00', requires: ['walking','vehicle'] },
      { id: 'm_patrol2',name: 'סייר 2',      hours: '07:00-15:00', requires: ['walking'] },
      { id: 'm_square', name: 'סייר כיכר',   hours: '07:00-15:00', requires: ['walking'] },
      { id: 'm_b4',     name: 'ב-4',         hours: '08:00-16:30', requires: ['armed'], activeDays: [0,1,2,3,4] },
      { id: 'm_b7',     name: 'ב-7',         hours: '08:00-16:30', requires: [] },
      { id: 'm_b8',     name: 'ב-8',         hours: '08:00-16:30', requires: [] },
      { id: 'm_b10',    name: 'ב-10',        hours: '08:00-16:30', requires: [] },
      { id: 'm_mevak',  name: 'מבקרת',       hours: '08:00-16:30', requires: ['roni'] },
    ],
    evening: [
      { id: 'e_ahmash', name: 'אחמ"ש ערב',   hours: '15:00-23:00', requires: ['armed'] },
      { id: 'e_haml',   name: 'חמ"ל ערב',     hours: '15:00-23:00', requires: [] },
      { id: 'e_patrol1',name: 'סייר 1 ערב',  hours: '15:00-23:00', requires: ['walking','vehicle'] },
      { id: 'e_b1',     name: 'ב-1',          hours: '17:00-23:00', requires: [] },
      { id: 'e_sb',     name: 'ס.ב',          hours: '17:00-23:00', requires: [] },
      { id: 'e_scan',   name: 'צופה סורק',    hours: '17:00-23:00', requires: [] },
    ],
    night: [
      { id: 'n_haml',   name: 'חמ"ל לילה',    hours: '23:00-07:00', requires: [] },
      { id: 'n_patrol1',name: 'סייר 1 לילה', hours: '23:00-07:00', requires: ['walking'] },
      { id: 'n_floor6', name: 'קומה 6 לילה',  hours: '23:00-07:00', requires: [] },
      { id: 'n_car',    name: 'רכב סיור',     hours: '19:00-07:00', requires: ['vehicle'] },
    ],
  };

  // ── Guards (pool). avail: {dayIndex: "HH:MM-HH:MM"}; missing day = off. ──
  const GUARDS = [
    { id: 'g_yosef',  name: 'יוסף כהן',      role: 'אחמ"ש',       attrs: ['armed'],
      avail: { 0:'07:00-19:00', 1:'07:00-19:00', 2:'07:00-19:00', 3:'07:00-19:00', 4:'07:00-19:00', 5:'07:00-14:00' } },
    { id: 'g_yehudit',name: 'יעל אורן',         role: 'מאבטח 9 שעות', attrs: ['vehicle'],
      avail: { 0:'07:00-19:00', 1:'07:00-19:00', 2:'07:00-19:00', 3:'07:00-19:00', 4:'07:00-19:00', 5:'07:00-15:00' } },
    { id: 'g_menahem',name: 'נדב שקד',           role: 'מאבטח בסיסי',  attrs: [],
      avail: { 0:'07:00-19:00', 1:'07:00-19:00', 2:'07:00-19:00', 3:'07:00-19:00', 4:'07:00-17:00' } },
    { id: 'g_omer',   name: 'עידו נחום',       role: 'מאבטח בסיסי',  attrs: [],
      avail: { 0:'06:00-19:00', 1:'06:00-19:00', 2:'06:00-19:00', 3:'06:00-19:00', 4:'06:00-19:00', 5:'06:00-14:00' } },
    { id: 'g_yaniv',  name: 'אלון ברק',     role: "רמה ב'",       attrs: ['armed'],
      avail: { 0:'07:00-15:00', 1:'07:00-15:00', 2:'07:00-15:00', 3:'07:00-15:00' } },
    { id: 'g_dvorak', name: 'דור אלמוג',       role: 'מאבטח בסיסי',  attrs: ['roni'],
      avail: { 0:'08:00-23:00', 1:'08:00-23:00', 2:'08:00-23:00', 3:'08:00-23:00', 4:'08:00-15:00' } },
    { id: 'g_moshe',  name: 'תומר',            role: 'מאבטח בסיסי',  attrs: [],
      avail: { 0:'15:00-23:00', 1:'15:00-23:00', 2:'15:00-23:00', 3:'15:00-23:00', 4:'15:00-23:00' } },
    { id: 'g_talpeled',name:'גל סער',         role: 'מאבטח 9 שעות', attrs: ['walking','vehicle'],
      avail: { 0:'07:00-16:30', 1:'07:00-16:30', 2:'07:00-16:30', 3:'07:00-16:30', 4:'07:00-16:30' } },
    { id: 'g_sapir',  name: 'ליאור',           role: 'מאבטח בסיסי',  attrs: [],
      avail: { 0:'16:00-07:00', 1:'16:00-07:00', 2:'16:00-07:00', 3:'16:00-07:00', 4:'16:00-07:00' } },
    { id: 'g_ayalon', name: 'אלעד',          role: 'לא חמוש',      attrs: [],
      avail: { 0:'23:00-07:00', 1:'23:00-07:00', 2:'23:00-07:00', 3:'23:00-07:00' } },
    { id: 'g_lewis',  name: 'רותם',           role: 'מאבטח בסיסי',  attrs: [],
      avail: { 0:'16:30-23:00', 1:'16:30-23:00', 2:'16:30-23:00', 3:'16:30-23:00', 4:'16:30-23:00' } },
    { id: 'g_maor',   name: 'ניר גפן',     role: "רמה ב'",       attrs: ['walking'],
      avail: { 0:'07:00-16:30', 1:'07:00-16:30', 2:'07:00-16:30', 3:'07:00-16:30', 4:'07:00-16:30' } },
    { id: 'g_tzion',  name: 'אסף כרמל',      role: 'מאבטח 9 שעות', attrs: ['vehicle'],
      avail: { 0:'07:00-17:00', 1:'07:00-17:00', 2:'07:00-17:00', 3:'07:00-17:00', 4:'07:00-17:00' } },
    { id: 'g_elia',   name: 'איתן שגב',   role: 'אחמ"ש',        attrs: ['armed','roni'],
      avail: { 0:'07:00-15:00', 1:'07:00-15:00', 2:'07:00-15:00', 3:'07:00-15:00', 4:'07:00-15:00' } },
  ];

  const DAYS = [
    { name: 'ראשון',  date: '14.06' },
    { name: 'שני',    date: '15.06' },
    { name: 'שלישי',  date: '16.06' },
    { name: 'רביעי',  date: '17.06' },
    { name: 'חמישי',  date: '18.06' },
    { name: 'שישי',   date: '19.06' },
    { name: 'שבת',    date: '20.06' },
  ];

  const SHIFTS = [
    { id: 'morning', label: 'בוקר' },
    { id: 'evening', label: 'ערב' },
    { id: 'night',   label: 'לילה' },
  ];

  return { ATTRS, POSITIONS, GUARDS, DAYS, SHIFTS };
})();
