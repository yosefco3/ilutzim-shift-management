import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import GuardPool from '../src/components/board/GuardPool';

const GUARDS = [
  {
    id: 'u1',
    full_name: 'נתן כהן',
    roles: ['ARMED'],
    remaining_hours: 12,
    available_hours: 24,
    notes: 'עדיפות לבקרים',
    availability: { 0: [{ start: '07:00', end: '19:00' }] },
  },
  {
    id: 'u2',
    full_name: 'רון לוי',
    roles: [],
    remaining_hours: 0,
    available_hours: 8,
    notes: null,
    availability: {},
  },
];

const attrLabel = (k) => ({ armed: 'חמוש' }[k] || k);

describe('GuardPool', () => {
  it('renders a card per guard with remaining hours', () => {
    render(<GuardPool guards={GUARDS} selectedId={null} onSelect={() => {}} attrLabel={attrLabel} />);
    expect(screen.getByText('נתן כהן')).toBeInTheDocument();
    expect(screen.getByText('רון לוי')).toBeInTheDocument();
    expect(screen.getByText(/נותרו 12/)).toBeInTheDocument();
    expect(screen.getByText('חמוש')).toBeInTheDocument();
  });

  it('moves fully-used guards into the "נוצלו במלואם" section', () => {
    render(<GuardPool guards={GUARDS} selectedId={null} onSelect={() => {}} attrLabel={attrLabel} />);
    expect(screen.getByText(/נוצלו במלואם/)).toBeInTheDocument();
    expect(screen.getByText('נוצל')).toBeInTheDocument(); // רון לוי, 0h left
  });

  it('filters guards by the search box', () => {
    render(<GuardPool guards={GUARDS} selectedId={null} onSelect={() => {}} attrLabel={attrLabel} />);
    fireEvent.change(screen.getByLabelText('חיפוש מאבטח…'), { target: { value: 'רון' } });
    expect(screen.queryByText('נתן כהן')).toBeNull();
    expect(screen.getByText('רון לוי')).toBeInTheDocument();
  });

  it('selects a guard on click', () => {
    const onSelect = vi.fn();
    render(<GuardPool guards={GUARDS} selectedId={null} onSelect={onSelect} attrLabel={attrLabel} />);
    fireEvent.click(screen.getByText('נתן כהן'));
    expect(onSelect).toHaveBeenCalledWith('u1');
  });

  it('toggles selection off when the selected guard is clicked again', () => {
    const onSelect = vi.fn();
    render(<GuardPool guards={GUARDS} selectedId="u1" onSelect={onSelect} attrLabel={attrLabel} />);
    fireEvent.click(screen.getByText('נתן כהן'));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('pins the selected guard to the top of the list while assigning him', () => {
    // נתן (12h) sorts above רון, but with רון selected he should jump to the top
    // — and stay there even though his remaining hours are lower — so the admin
    // can keep assigning him without him sinking back down the list.
    const guards = [
      { ...GUARDS[0], id: 'u1', full_name: 'נתן כהן', remaining_hours: 12 },
      { ...GUARDS[1], id: 'u2', full_name: 'רון לוי', remaining_hours: 4 },
    ];
    const { container } = render(
      <GuardPool guards={guards} selectedId="u2" onSelect={() => {}} attrLabel={attrLabel} />,
    );
    const names = [...container.querySelectorAll('.guard-card-name')].map((n) => n.textContent);
    expect(names[0]).toBe('רון לוי');
    expect(names[1]).toBe('נתן כהן');
  });

  it('keeps a selected guard pinned at the top even once he is fully used up', () => {
    // רון has 0h left — normally in the "נוצלו במלואם" section, but while selected
    // he stays pinned at the top of the active list until deselected.
    const guards = [
      { ...GUARDS[0], id: 'u1', full_name: 'נתן כהן', remaining_hours: 12 },
      { ...GUARDS[1], id: 'u2', full_name: 'רון לוי', remaining_hours: 0 },
    ];
    const { container } = render(
      <GuardPool guards={guards} selectedId="u2" onSelect={() => {}} attrLabel={attrLabel} />,
    );
    const firstList = container.querySelector('.guard-pool-list');
    const firstName = firstList.querySelector('.guard-card-name').textContent;
    expect(firstName).toBe('רון לוי');
    // and he is no longer down in the "used up" section
    expect(screen.queryByText(/נוצלו במלואם/)).toBeNull();
  });

  it('shows the note only after clicking the note button', () => {
    render(<GuardPool guards={GUARDS} selectedId={null} onSelect={() => {}} attrLabel={attrLabel} />);
    expect(screen.queryByText('עדיפות לבקרים')).toBeNull();
    fireEvent.click(screen.getByLabelText('הערת המאבטח'));
    expect(screen.getByText('עדיפות לבקרים')).toBeInTheDocument();
  });

  it('is draggable and carries the guard id while selecting them on drag-start', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <GuardPool guards={GUARDS} selectedId={null} onSelect={onSelect} attrLabel={attrLabel} />,
    );
    const card = container.querySelector('.guard-card');
    expect(card).toHaveAttribute('draggable', 'true');
    const dataTransfer = { setData: vi.fn(), effectAllowed: '' };
    fireEvent.dragStart(card, { dataTransfer });
    expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', 'u1');
    expect(onSelect).toHaveBeenCalledWith('u1');
  });

  it('dismisses a guard from the pool without selecting them', () => {
    const onDismiss = vi.fn();
    const onSelect = vi.fn();
    render(
      <GuardPool guards={GUARDS} selectedId={null} onSelect={onSelect} onDismiss={onDismiss} onRestore={vi.fn()} attrLabel={attrLabel} />,
    );
    fireEvent.click(screen.getAllByLabelText('הסתר מהמאגר')[0]);
    expect(onDismiss).toHaveBeenCalledWith('u1');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('moves a dismissed guard into the "הוסתרו" section with a restore chip', () => {
    const onRestore = vi.fn();
    const { container } = render(
      <GuardPool
        guards={GUARDS}
        selectedId={null}
        onSelect={() => {}}
        onDismiss={vi.fn()}
        onRestore={onRestore}
        dismissedIds={new Set(['u1'])}
        attrLabel={attrLabel}
      />,
    );
    // u1 is no longer a card in the working list, only a restore chip.
    expect(container.querySelector('.guard-card-name')?.textContent).not.toBe('נתן כהן');
    expect(screen.getByText(/הוסתרו/)).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('החזר למאגר'));
    expect(onRestore).toHaveBeenCalledWith('u1');
  });

  it('renders an empty state when no guards submitted', () => {
    render(<GuardPool guards={[]} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText('אף מאבטח לא הגיש זמינות לשבוע זה')).toBeInTheDocument();
  });

  describe('"אחמ"שים קודם" toggle', () => {
    // Backend order: plain guard (most free) before the AHMASH guard.
    const MIXED = [
      { id: 'p1', full_name: 'פנוי רגיל', roles: [], remaining_hours: 12, available_hours: 12, notes: null, availability: {} },
      { id: 'a1', full_name: 'אחמש עסוק', roles: ['AHMASH'], remaining_hours: 4, available_hours: 12, notes: null, availability: {} },
    ];

    const names = (container) =>
      [...container.querySelectorAll('.guard-card-name')].map((n) => n.textContent);

    afterEach(() => localStorage.removeItem('board.ahmashFirst'));

    it('is ON by default and lifts AHMASH guards above the rest', () => {
      const { container } = render(
        <GuardPool guards={MIXED} selectedId={null} onSelect={() => {}} attrLabel={attrLabel} />,
      );
      expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
      expect(names(container)).toEqual(['אחמש עסוק', 'פנוי רגיל']);
    });

    it('falls back to the incoming (remaining-hours) order when switched OFF, and persists', () => {
      const { container } = render(
        <GuardPool guards={MIXED} selectedId={null} onSelect={() => {}} attrLabel={attrLabel} />,
      );
      fireEvent.click(screen.getByRole('switch'));
      expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
      expect(names(container)).toEqual(['פנוי רגיל', 'אחמש עסוק']);
      expect(localStorage.getItem('board.ahmashFirst')).toBe('false');
    });

    it('starts OFF when the persisted preference says so', () => {
      localStorage.setItem('board.ahmashFirst', 'false');
      const { container } = render(
        <GuardPool guards={MIXED} selectedId={null} onSelect={() => {}} attrLabel={attrLabel} />,
      );
      expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
      expect(names(container)).toEqual(['פנוי רגיל', 'אחמש עסוק']);
    });
  });

  it('flags a guard with a policy warning (red dot + tooltip), clean guards have none', () => {
    const { container } = render(
      <GuardPool
        guards={GUARDS}
        selectedId={null}
        onSelect={() => {}}
        attrLabel={attrLabel}
        guardWarnings={{
          u1: [{ type: 'over_continuous_hours', guardName: 'נתן כהן', hours: 15 }],
        }}
      />,
    );
    const badges = container.querySelectorAll('.guard-card-warn');
    expect(badges.length).toBe(1); // only נתן כהן is flagged
    expect(badges[0].getAttribute('title')).toMatch(/מעל 12ש׳ רצופות/);
  });
});
