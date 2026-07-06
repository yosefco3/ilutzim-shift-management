// Golden-fixture parity — the JS side.
//
// Consumes the SAME fixtures as the Python pytest parity test
// (backend/tests/fixtures/warnings/*.json), so a rule or threshold changed in one
// language and not the other turns this red. The fixtures are the single source
// of truth (snake_case, Python-canonical); this test carries the thin camel↔snake
// adapter — the engine itself is never adapted.

import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { computeBoardWarnings } from '../src/utils/warnings';

const here = dirname(fileURLToPath(import.meta.url));
const FIX_DIR = resolve(here, '../../../backend/tests/fixtures/warnings');

// Fixture policy is snake (Python-canonical); the JS engine reads camelCase.
function policyToCamel(p) {
  return {
    restMinutes: p.rest_minutes,
    maxConsecutiveDays: p.max_consecutive_days,
    maxContinuousMinutes: p.max_continuous_minutes,
  };
}

// The JS engine emits camelCase keys; rename them to the snake fixture form so we
// can compare against `expected`. Only these specific keys are renamed; warning
// type strings and summary keys are already snake and pass through untouched.
const RENAME = {
  byCell: 'by_cell',
  byGuard: 'by_guard',
  guardId: 'guard_id',
  guardName: 'guard_name',
  otherPosition: 'other_position',
  gapHours: 'gap_hours',
};

function toSnake(value) {
  if (Array.isArray(value)) return value.map(toSnake);
  if (value && typeof value === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[RENAME[k] || k] = toSnake(v);
    }
    return out;
  }
  return value;
}

const fixtures = readdirSync(FIX_DIR).filter((f) => f.endsWith('.json'));

describe('warnings JS↔Python parity (golden fixtures)', () => {
  it('has fixtures to check', () => {
    expect(fixtures.length).toBeGreaterThanOrEqual(8);
  });

  for (const file of fixtures) {
    it(`matches ${file}`, () => {
      const { input, expected } = JSON.parse(
        readFileSync(resolve(FIX_DIR, file), 'utf-8'),
      );
      const result = computeBoardWarnings({
        board: input.board,
        assignmentsByCell: input.assignments_by_cell,
        pool: input.pool,
        policy: policyToCamel(input.policy),
      });
      expect(toSnake(result)).toEqual(expected);
    });
  }
});
