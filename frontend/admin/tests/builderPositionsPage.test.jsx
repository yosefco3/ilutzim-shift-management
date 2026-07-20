import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import messages from '../src/utils/messages';
import { DAY_NAMES_SHORT as DAY_NAMES } from '../src/utils/guardMessages.js';

vi.mock('../src/api/builderApiClient', () => ({
  listProfiles: vi.fn(),
  listPositions: vi.fn(),
  createPosition: vi.fn(),
  updatePosition: vi.fn(),
  updateProfile: vi.fn(),
  deletePosition: vi.fn(),
  copyPosition: vi.fn(),
  bulkUpdateDaySchedules: vi.fn(),
  listAttributes: vi.fn(),
  createAttribute: vi.fn(),
  deleteAttribute: vi.fn(),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({ useToast: () => toast }));

import {
  listProfiles,
  listPositions,
  createPosition,
  deletePosition,
  copyPosition,
  bulkUpdateDaySchedules,
  updateProfile,
  listAttributes,
} from '../src/api/builderApiClient';
import PositionsPage from '../src/pages/builder/PositionsPage';

const PROFILE = { id: 'p1', name: 'שגרה', is_default: true };
const PROFILE2 = { id: 'p2', name: 'חג', is_default: false };
const ATTR = { id: 'a1', key: 'armed', label: 'חמוש', display_order: 0 };
const POSITION = {
  id: 'pos1',
  profile_id: 'p1',
  name: 'ארנונה',
  day_schedules: { 0: { start: '07:30', end: '15:00' } },
  required_attributes: ['armed'],
  display_order: 1,
};

function renderPage(initialEntries = ['/builder/positions']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <PositionsPage />
    </MemoryRouter>,
  );
}

// Accessible name of a matrix cell (matches ProfileMatrix's aria-label).
const cellName = (posName, dayIdx, active) =>
  `${posName}, ${DAY_NAMES[dayIdx]}, ${active ? messages.positions.active : messages.positions.matrixOff}`;

beforeEach(() => {
  vi.clearAllMocks();
  listProfiles.mockResolvedValue([PROFILE]);
  listAttributes.mockResolvedValue([ATTR]);
  // Fresh clone per call so a post-save/post-409 reload returns a NEW positions
  // identity — ProfileMatrix resets its snapshot only when `positions` changes.
  listPositions.mockImplementation(async () => [JSON.parse(JSON.stringify(POSITION))]);
  updateProfile.mockResolvedValue({});
});

describe('PositionsPage', () => {
  it('loads the profile selector and lists positions', async () => {
    renderPage();
    expect(await screen.findByText('ארנונה')).toBeInTheDocument();
    // Requirement tags live on the cards — switch off the default matrix tab.
    fireEvent.click(screen.getByText('כרטיסיות'));
    expect(screen.getByText('חמוש')).toBeInTheDocument(); // requirement tag
  });

  it('defaults to the matrix tab (positions × days grid)', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    // The matrix tab button is the active one.
    const matrixBtn = screen.getByText('תצוגת לוח');
    expect(matrixBtn.className).toContain('btn-primary');
    expect(matrixBtn).toHaveAttribute('aria-pressed', 'true');
    // Matrix rendered, cards grid not.
    expect(document.querySelector('.profile-matrix')).not.toBeNull();
    expect(document.querySelector('.position-cards')).toBeNull();
  });

  it('switching to "כרטיסיות" shows the card grid and hides the matrix', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    expect(document.querySelector('.profile-matrix')).not.toBeNull();

    fireEvent.click(screen.getByText('כרטיסיות'));

    expect(document.querySelector('.position-cards')).not.toBeNull();
    expect(document.querySelector('.profile-matrix')).toBeNull();
    expect(screen.getByText('כרטיסיות').className).toContain('btn-primary');
  });

  it('matrix full-screen: enter adds the focus chrome, exit (button + Esc) removes it', async () => {
    const mp = messages.positions;
    renderPage();
    await screen.findByText('ארנונה');
    // Enter full-screen from the tab row.
    fireEvent.click(screen.getByText(mp.matrixFocusEnter));
    expect(document.body.classList.contains('positions-focus')).toBe(true);
    expect(document.querySelector('.page').className).toContain('is-matrix-focus');
    // Exit via the floating button.
    fireEvent.click(screen.getByText(mp.matrixFocusExit));
    expect(document.body.classList.contains('positions-focus')).toBe(false);
    // Re-enter, then Esc exits.
    fireEvent.click(screen.getByText(mp.matrixFocusEnter));
    expect(document.body.classList.contains('positions-focus')).toBe(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(document.body.classList.contains('positions-focus')).toBe(false);
  });

  it('matrix full-screen: the enter button is hidden on the cards tab', async () => {
    const mp = messages.positions;
    renderPage();
    await screen.findByText('ארנונה');
    expect(screen.queryByText(mp.matrixFocusEnter)).not.toBeNull();
    fireEvent.click(screen.getByText('כרטיסיות'));
    expect(screen.queryByText(mp.matrixFocusEnter)).toBeNull();
  });

  it('creates a position with day schedule and requirement', async () => {
    createPosition.mockResolvedValue({ ...POSITION, id: 'pos2' });
    renderPage();
    await screen.findByText('ארנונה');

    fireEvent.click(screen.getByText('עמדה חדשה'));
    fireEvent.change(screen.getByLabelText('שם העמדה'), { target: { value: 'קומה 6' } });
    fireEvent.click(screen.getByLabelText('ראשון')); // activate Sunday
    fireEvent.click(screen.getByLabelText('חמוש')); // requirement (in editor)
    fireEvent.click(screen.getByText('שמור'));

    await waitFor(() => expect(createPosition).toHaveBeenCalled());
    const [profileArg, body] = createPosition.mock.calls[0];
    expect(profileArg).toBe('p1');
    expect(body.name).toBe('קומה 6');
    expect(body.day_schedules['0']).toEqual({ start: '07:00', end: '15:00' });
    expect(body.required_attributes).toEqual(['armed']);
    expect(body.is_event).toBe(false); // normal position by default
  });

  it('creates an event (non-splitting) position when the checkbox is ticked', async () => {
    createPosition.mockResolvedValue({ ...POSITION, id: 'pos3', is_event: true });
    renderPage();
    await screen.findByText('ארנונה');

    fireEvent.click(screen.getByText('עמדה חדשה'));
    fireEvent.change(screen.getByLabelText('שם העמדה'), { target: { value: 'רענון' } });
    fireEvent.click(screen.getByLabelText('ראשון')); // activate Sunday
    fireEvent.click(screen.getByLabelText('לא מתפצל'));
    fireEvent.click(screen.getByText('שמור'));

    await waitFor(() => expect(createPosition).toHaveBeenCalled());
    const [, body] = createPosition.mock.calls[0];
    expect(body.is_event).toBe(true);
    // No count entered → unlimited event.
    expect(body.event_required_count).toBeNull();
  });

  it('creates a fixed-count event when a participant count is entered', async () => {
    createPosition.mockResolvedValue({ ...POSITION, id: 'pos4', is_event: true });
    renderPage();
    await screen.findByText('ארנונה');

    fireEvent.click(screen.getByText('עמדה חדשה'));
    fireEvent.change(screen.getByLabelText('שם העמדה'), { target: { value: 'מועצה' } });
    fireEvent.click(screen.getByLabelText('ראשון'));
    fireEvent.click(screen.getByLabelText('לא מתפצל'));
    // The count field appears only once the position is an event.
    fireEvent.change(screen.getByLabelText('מספר משתתפים קבוע'), { target: { value: '4' } });
    fireEvent.click(screen.getByText('שמור'));

    await waitFor(() => expect(createPosition).toHaveBeenCalled());
    const [, body] = createPosition.mock.calls[0];
    expect(body.is_event).toBe(true);
    expect(body.event_required_count).toBe(4);
  });

  it('hides the count field until "event" is ticked', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    fireEvent.click(screen.getByText('עמדה חדשה'));
    expect(screen.queryByLabelText('מספר משתתפים קבוע')).toBeNull();
    fireEvent.click(screen.getByLabelText('לא מתפצל'));
    expect(screen.getByLabelText('מספר משתתפים קבוע')).toBeInTheDocument();
  });

  it('shows the event badge on an event position card', async () => {
    listPositions.mockResolvedValue([{ ...POSITION, id: 'ev1', name: 'רענון', is_event: true }]);
    renderPage();
    expect(await screen.findByText('📣 אירוע')).toBeInTheDocument();
  });

  it('shows the participant count on a fixed-count event card', async () => {
    listPositions.mockResolvedValue([
      { ...POSITION, id: 'ev2', name: 'מועצה', is_event: true, event_required_count: 4 },
    ]);
    renderPage();
    expect(await screen.findByText('📣 אירוע · 4')).toBeInTheDocument();
  });

  it('blocks save when no day is active', async () => {
    renderPage();
    await screen.findByText('ארנונה');

    fireEvent.click(screen.getByText('עמדה חדשה'));
    fireEvent.change(screen.getByLabelText('שם העמדה'), { target: { value: 'בלי ימים' } });
    fireEvent.click(screen.getByText('שמור'));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(createPosition).not.toHaveBeenCalled();
  });

  it('copies a position to another profile by drag-and-drop', async () => {
    listProfiles.mockResolvedValue([PROFILE, PROFILE2]);
    copyPosition.mockResolvedValue({ ...POSITION, id: 'pos9', profile_id: 'p2' });
    renderPage();
    await screen.findByText('ארנונה');

    // Drag-and-drop lives on the cards — switch off the default matrix tab.
    fireEvent.click(screen.getByText('כרטיסיות'));

    // The drop target is the other profile rendered as a copy-target chip.
    const target = screen
      .getAllByText('חג')
      .find((el) => el.className.includes('copy-target'));
    expect(target).toBeTruthy();

    const dataTransfer = {
      data: {},
      setData(type, val) { this.data[type] = val; },
      getData(type) { return this.data[type]; },
    };
    const card = screen.getByText('ארנונה').closest('.position-card');
    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });

    await waitFor(() => expect(copyPosition).toHaveBeenCalledWith('pos1', 'p2'));
    expect(toast.success).toHaveBeenCalled();
  });

  it('deletes a position after confirmation', async () => {
    deletePosition.mockResolvedValue(null);
    renderPage();
    await screen.findByText('ארנונה');

    // The delete button lives on the cards — switch off the default matrix tab.
    fireEvent.click(screen.getByText('כרטיסיות'));

    fireEvent.click(screen.getByText('מחק')); // opens confirm
    const buttons = screen.getAllByText('מחק');
    fireEvent.click(buttons[buttons.length - 1]);

    await waitFor(() => expect(deletePosition).toHaveBeenCalledWith('pos1'));
  });

  it('auto-opens the editor for a deep-linked ?edit position (board edit shortcut)', async () => {
    listProfiles.mockResolvedValue([PROFILE, PROFILE2]);
    renderPage(['/builder/positions?profile=p1&edit=pos1']);

    // The editor modal opens on load, seeded with the position's name.
    expect(await screen.findByText('עריכת עמדה')).toBeInTheDocument();
    expect(screen.getByLabelText('שם העמדה').value).toBe('ארנונה');
    // ?edit lands on the cards tab (the editor flow lives there), not the matrix.
    expect(document.querySelector('.position-cards')).not.toBeNull();
    expect(document.querySelector('.profile-matrix')).toBeNull();
  });

  // ── Matrix editor (step 04): save / 409 / 500 / unsaved guard ──────────────
  // Make the matrix dirty by toggling position ארנונה's active Sunday off.
  const dirtyTheMatrix = async () => {
    fireEvent.click(screen.getByRole('button', { name: cellName('ארנונה', 0, true) }));
  };

  it('matrix save: success sends only changed rows, reloads, and toasts', async () => {
    bulkUpdateDaySchedules.mockResolvedValue({});
    renderPage();
    await screen.findByText('ארנונה');
    await dirtyTheMatrix();

    fireEvent.click(screen.getByText(messages.positions.matrixSave(1)));

    // Payload = only the changed position, with its now-empty day map [EDGE C1/D3].
    await waitFor(() =>
      expect(bulkUpdateDaySchedules).toHaveBeenCalledWith('p1', [
        { position_id: 'pos1', day_schedules: {} },
      ]),
    );
    expect(toast.success).toHaveBeenCalledWith(messages.positions.matrixSaved);
    // Reload: listPositions called a 2nd time for p1.
    await waitFor(() => expect(listPositions).toHaveBeenCalledTimes(2));
    // Dirty cleared after reload.
    expect(await screen.findByText(messages.positions.matrixSave(0))).toBeInTheDocument();
  });

  it('matrix save: 409 reloads, shows the conflict toast, and discards dirty [EDGE C2]', async () => {
    bulkUpdateDaySchedules.mockRejectedValueOnce(Object.assign(new Error('changed'), { status: 409 }));
    renderPage();
    await screen.findByText('ארנונה');
    await dirtyTheMatrix();

    fireEvent.click(screen.getByText(messages.positions.matrixSave(1)));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(messages.positions.matrixConflict));
    // Reload happened.
    await waitFor(() => expect(listPositions).toHaveBeenCalledTimes(2));
    // Dirty discarded.
    expect(await screen.findByText(messages.positions.matrixSave(0))).toBeInTheDocument();
  });

  it('matrix save: 5xx keeps the dirty state for a retry (no reload) [EDGE N1]', async () => {
    bulkUpdateDaySchedules.mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 500 }));
    renderPage();
    await screen.findByText('ארנונה');
    await dirtyTheMatrix();

    fireEvent.click(screen.getByText(messages.positions.matrixSave(1)));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('boom'));
    expect(toast.error).not.toHaveBeenCalledWith(messages.positions.matrixConflict);
    // No reload.
    expect(listPositions).toHaveBeenCalledTimes(1);
    // Dirty kept — save button still shows the changed-rows count.
    expect(screen.getByText(messages.positions.matrixSave(1))).toBeInTheDocument();
  });

  it('switching profile with a dirty matrix opens the guard; confirm proceeds [EDGE N2]', async () => {
    listProfiles.mockResolvedValue([PROFILE, PROFILE2]);
    renderPage();
    await screen.findByText('ארנונה');
    await dirtyTheMatrix();

    // Switching profile is intercepted (the <select> is controlled, so it
    // reverts until confirmed).
    fireEvent.change(screen.getByLabelText(messages.positions.profile), { target: { value: 'p2' } });
    expect(await screen.findByText(messages.positions.matrixDirtyLeave)).toBeInTheDocument();

    // Confirm → the pending switch runs (loads p2's positions).
    fireEvent.click(screen.getByText(messages.positions.matrixDirtyLeaveConfirm));
    await waitFor(() => expect(listPositions).toHaveBeenCalledWith('p2'));
  });

  it('canceling the unsaved-changes guard keeps the current profile [EDGE N2]', async () => {
    listProfiles.mockResolvedValue([PROFILE, PROFILE2]);
    renderPage();
    await screen.findByText('ארנונה');
    await dirtyTheMatrix();

    fireEvent.change(screen.getByLabelText(messages.positions.profile), { target: { value: 'p2' } });
    expect(await screen.findByText(messages.positions.matrixDirtyLeave)).toBeInTheDocument();

    fireEvent.click(screen.getByText(messages.common.cancel));

    // Did NOT switch to p2; guard closed.
    expect(listPositions).not.toHaveBeenCalledWith('p2');
    expect(screen.queryByText(messages.positions.matrixDirtyLeave)).toBeNull();
    // Still on p1; the dirty change is still there.
    expect(screen.getByText(messages.positions.matrixSave(1))).toBeInTheDocument();
  });

  // ── Step 07: header day-label editing (PATCHes the profile's day_labels) ──
  it('day-label Enter PATCHes the full merged day_labels map via updateProfile', async () => {
    renderPage();
    await screen.findByText('ארנונה');
    // Thursday has no label yet → open its "+ תווית" affordance.
    fireEvent.click(
      screen.getByRole('button', { name: `${DAY_NAMES[4]} · ${messages.positions.matrixAddDayLabel}` }),
    );
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ט׳ באב' } });
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });

    // The page merges the FULL map (current {} + Thursday) and PATCHes.
    await waitFor(() =>
      expect(updateProfile).toHaveBeenCalledWith('p1', { day_labels: { '4': 'ט׳ באב' } }),
    );
    expect(toast.success).toHaveBeenCalledWith(messages.positions.dayLabelSaved);
  });

  it('day-label clear removes the key from the PATCHed day_labels map', async () => {
    listProfiles.mockResolvedValue([
      { id: 'p1', name: 'שגרה', is_default: true, day_labels: { '4': 'ישן' } },
    ]);
    renderPage();
    // Thursday shows the existing label; click it to edit.
    fireEvent.click(await screen.findByText('ישן'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '' } });
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });

    // Empty value → the key is dropped → the whole map clears to {}.
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith('p1', { day_labels: {} }));
  });
});
