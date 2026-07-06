// Mock data for the Ilutsim admin UI kit — Hebrew, realistic shapes mirroring
// the live API (weeks lifecycle, guards with roles, weekly submissions).
window.KitData = {
  weeks: [
    { id: 24, start_date: '15.06.2026', end_date: '21.06.2026', week_label: 'שבוע 25', status: 'open',      submission_count: 9 },
    { id: 23, start_date: '08.06.2026', end_date: '14.06.2026', week_label: 'שבוע 24', status: 'locked',    submission_count: 12 },
    { id: 22, start_date: '01.06.2026', end_date: '07.06.2026', week_label: 'שבוע 23', status: 'published', submission_count: 12 },
    { id: 25, start_date: '22.06.2026', end_date: '28.06.2026', week_label: 'שבוע 26', status: 'closed',    submission_count: 0 },
  ],
  guards: [
    { id: 1, first_name: 'יוסף',  last_name: 'כהן',     phone_number: '052-1234567', role: 'AHMASH',      is_active: true  },
    { id: 2, first_name: 'דניאל', last_name: 'לוי',     phone_number: '054-7654321', role: 'BASIC_GUARD', is_active: true  },
    { id: 3, first_name: 'מאיה',  last_name: 'פרץ',     phone_number: '050-9988776', role: 'LEVEL_B',     is_active: true  },
    { id: 4, first_name: 'אבי',   last_name: 'מזרחי',   phone_number: '058-4455667', role: 'NINE_HOURS',  is_active: false },
    { id: 5, first_name: 'נועה',  last_name: 'ביטון',   phone_number: '053-2233445', role: 'CHECKER',     is_active: true  },
    { id: 6, first_name: 'איתי',  last_name: 'אזולאי',  phone_number: '050-1122334', role: 'UNARMED',     is_active: true  },
  ],
  // submissions for the open week (24)
  submissions: [
    { user_id: 1, full_name: 'יוסף כהן',   submitted_at: '2026-06-12T09:14:00', days: [
      { shift_windows: [{ shift_type: 'morning', start_time: '07:00', end_time: '16:30' }] },
      { shift_windows: [{ shift_type: 'morning', start_time: '07:00', end_time: '16:30' }] },
      { shift_windows: [] },
      { shift_windows: [{ shift_type: 'night', start_time: '23:00', end_time: '07:00' }] },
      { shift_windows: [{ shift_type: 'afternoon', start_time: '15:00', end_time: '23:00' }] },
      { shift_windows: [] },
      { shift_windows: [] },
    ], general_notes: 'מעדיף בקרים בתחילת השבוע' },
    { user_id: 2, full_name: 'דניאל לוי', submitted_at: '2026-06-12T18:02:00', days: [], general_notes: '' },
    { user_id: 3, full_name: 'מאיה פרץ',  submitted_at: '2026-06-13T07:40:00', days: [], general_notes: '' },
    { user_id: 5, full_name: 'נועה ביטון', submitted_at: null, days: [], general_notes: '' },
    { user_id: 6, full_name: 'איתי אזולאי', submitted_at: null, days: [], general_notes: '' },
  ],
  ROLE_LABELS: {
    AHMASH: 'אחמ"ש', BASIC_GUARD: 'מאבטח בסיסי', LEVEL_B: "מאבטח רמה ב'",
    NINE_HOURS: 'מאבטח 9 שעות', UNARMED: 'לא חמוש', CHECKER: 'בודק',
  },
  DAY_NAMES: ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'],
  SHIFT_LABELS: { morning: 'בוקר', afternoon: 'ערב', night: 'לילה' },
};
