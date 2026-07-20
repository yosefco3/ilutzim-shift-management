import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import messages from '../src/utils/messages';

vi.mock('../src/api/builderApiClient', () => ({
  listProfiles: vi.fn(),
  createProfile: vi.fn(),
  updateProfile: vi.fn(),
  duplicateProfile: vi.fn(),
  deleteProfile: vi.fn(),
  getProfileDeleteImpact: vi.fn(),
}));
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock('../src/components/Toast', () => ({
  useToast: () => toast,
}));

import {
  listProfiles,
  createProfile,
  updateProfile,
  duplicateProfile,
  deleteProfile,
  getProfileDeleteImpact,
} from '../src/api/builderApiClient';
import ProfilesPage from '../src/pages/builder/ProfilesPage';

const DEFAULT_PROFILE = {
  id: 'p1',
  name: 'שגרה',
  kind: 'רגיל',
  description: null,
  is_default: true,
  display_order: 0,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ProfilesPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listProfiles.mockResolvedValue([DEFAULT_PROFILE]);
  getProfileDeleteImpact.mockResolvedValue({ weeks: 0, assignments: 0, is_last: false });
});

describe('ProfilesPage', () => {
  it('renders the seeded default profile', async () => {
    renderPage();
    expect(await screen.findByText('שגרה')).toBeInTheDocument();
    expect(screen.getByText('ברירת מחדל')).toBeInTheDocument();
  });

  it('creates a profile via the form', async () => {
    createProfile.mockResolvedValue({ id: 'p2', name: 'חג', is_default: false });
    renderPage();
    await screen.findByText('שגרה');

    fireEvent.change(screen.getByLabelText('שם'), { target: { value: 'חג' } });
    fireEvent.click(screen.getByText('פרופיל חדש'));

    await waitFor(() =>
      expect(createProfile).toHaveBeenCalledWith({ name: 'חג' }),
    );
    expect(listProfiles).toHaveBeenCalledTimes(2); // initial + after create
  });

  it('duplicates a profile', async () => {
    duplicateProfile.mockResolvedValue({ id: 'p3', name: 'שגרה (עותק)' });
    renderPage();
    await screen.findByText('שגרה');

    fireEvent.click(screen.getByText('שכפל'));

    await waitFor(() => expect(duplicateProfile).toHaveBeenCalledWith('p1'));
  });

  it('deletes a profile after confirmation', async () => {
    deleteProfile.mockResolvedValue(null);
    renderPage();
    await screen.findByText('שגרה');

    fireEvent.click(screen.getByText('מחק')); // opens confirm dialog
    // ConfirmDialog confirm button uses the same "מחק" label
    const buttons = screen.getAllByText('מחק');
    fireEvent.click(buttons[buttons.length - 1]);

    await waitFor(() => expect(deleteProfile).toHaveBeenCalledWith('p1'));
  });

  it('warns with the cascade impact before deleting a profile that has schedules', async () => {
    getProfileDeleteImpact.mockResolvedValue({ weeks: 2, assignments: 5, is_last: false });
    deleteProfile.mockResolvedValue(null);
    renderPage();
    await screen.findByText('שגרה');

    fireEvent.click(screen.getByText('מחק')); // opens confirm dialog

    // The dialog shows the specific loss, not the generic message.
    expect(await screen.findByText(/2 שבועות/)).toBeInTheDocument();
    expect(screen.getByText(/5 שיבוצים/)).toBeInTheDocument();
    await waitFor(() => expect(getProfileDeleteImpact).toHaveBeenCalledWith('p1'));
  });

  it('hides the delete button and shows the base badge for the base profile', async () => {
    listProfiles.mockResolvedValue([
      { ...DEFAULT_PROFILE, is_base: true },
      { id: 'p2', name: 'חג', is_default: false, is_base: false, display_order: 1 },
    ]);
    renderPage();
    await screen.findByText('שגרה');
    // The base badge marks it; the non-base profile keeps its delete button.
    expect(screen.getByText('בסיס')).toBeInTheDocument();
    // Exactly one delete button remains (for 'חג'), not two.
    expect(screen.getAllByText('מחק')).toHaveLength(1);
  });

  it('keeps the delete button when no profile is the base', async () => {
    listProfiles.mockResolvedValue([
      { ...DEFAULT_PROFILE, is_base: false },
    ]);
    renderPage();
    await screen.findByText('שגרה');
    expect(screen.queryByText('בסיס')).toBeNull();
    expect(screen.getByText('מחק')).toBeInTheDocument();
  });

  it('edits a profile name', async () => {
    updateProfile.mockResolvedValue({ ...DEFAULT_PROFILE, name: 'שגרה ראשית' });
    renderPage();
    await screen.findByText('שגרה');

    fireEvent.click(screen.getByText('ערוך'));
    const input = screen.getByLabelText('ערוך-שם');
    fireEvent.change(input, { target: { value: 'שגרה ראשית' } });
    fireEvent.click(screen.getByText('שמור'));

    await waitFor(() =>
      expect(updateProfile).toHaveBeenCalledWith('p1', { name: 'שגרה ראשית' }),
    );
  });

  it('warns when the base profile is ALSO the default', async () => {
    listProfiles.mockResolvedValue([
      { ...DEFAULT_PROFILE, is_base: true, is_default: true },
    ]);
    renderPage();
    await screen.findByText('שגרה');
    expect(
      screen.getByText(messages.profiles.baseProfileWarning),
    ).toBeInTheDocument();
  });

  it('does not warn when the base profile is not the default', async () => {
    listProfiles.mockResolvedValue([
      { ...DEFAULT_PROFILE, id: 'p1', name: 'שגרה', is_base: true, is_default: false },
      { id: 'p2', name: 'חג', is_base: false, is_default: true, display_order: 1 },
    ]);
    renderPage();
    await screen.findByText('שגרה');
    expect(screen.queryByText(messages.profiles.baseProfileWarning)).toBeNull();
  });

  it('orders cards: base first, then newest-created to oldest', async () => {
    // Deliberately scrambled input order to prove it sorts, not passes through.
    listProfiles.mockResolvedValue([
      { id: 'p1', name: 'ישן', is_base: false, is_default: false, created_at: '2026-01-01T00:00:00' },
      { id: 'p2', name: 'שגרה', is_base: true, is_default: false, created_at: '2026-06-01T00:00:00' },
      { id: 'p3', name: 'חדש', is_base: false, is_default: true, created_at: '2026-07-01T00:00:00' },
      { id: 'p4', name: 'אמצע', is_base: false, is_default: false, created_at: '2026-05-01T00:00:00' },
    ]);
    renderPage();
    await screen.findByText('חדש');
    const names = [...document.querySelectorAll('.profile-card-name')].map((n) => n.textContent);
    // Base pinned first (despite not being newest), then created_at descending.
    expect(names).toEqual(['שגרה', 'חדש', 'אמצע', 'ישן']);
  });
});
