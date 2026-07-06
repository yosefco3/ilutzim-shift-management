import { describe, it, expect } from 'vitest';
import { weeklyExportFilename } from '../src/utils/download';

describe('weeklyExportFilename', () => {
  it('keys the filename on the week start date, not the opaque id', () => {
    expect(weeklyExportFilename('guard-positions', '2026-07-05')).toBe(
      'guard-positions_2026-07-05.xlsx',
    );
  });

  it('tolerates a datetime string, keeping only the yyyy-mm-dd part', () => {
    expect(weeklyExportFilename('schedule', '2026-07-05T00:00:00')).toBe(
      'schedule_2026-07-05.xlsx',
    );
  });

  it('falls back to just the content name when no date is available', () => {
    expect(weeklyExportFilename('constraints', undefined)).toBe('constraints.xlsx');
    expect(weeklyExportFilename('constraints', '')).toBe('constraints.xlsx');
  });
});
