import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/api/builderApiClient', () => ({
  listProfiles: vi.fn(),
  listPositions: vi.fn(),
  createPosition: vi.fn(),
  updatePosition: vi.fn(),
  deletePosition: vi.fn(),
  copyPosition: vi.fn(),
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

beforeEach(() => {
  vi.clearAllMocks();
  listProfiles.mockResolvedValue([PROFILE]);
  listAttributes.mockResolvedValue([ATTR]);
  listPositions.mockResolvedValue([POSITION]);
});

describe('PositionsPage', () => {
  it('loads the profile selector and lists positions', async () => {
    renderPage();
    expect(await screen.findByText('ארנונה')).toBeInTheDocument();
    expect(screen.getByText('חמוש')).toBeInTheDocument(); // requirement tag
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
  });
});
