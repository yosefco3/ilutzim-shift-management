import { describe, it, expect } from 'vitest';
import messages from '../src/utils/messages';

describe('Admin Messages', () => {
  it('has common section', () => {
    expect(messages.common).toBeDefined();
    expect(messages.common.loading).toBeDefined();
    expect(messages.common.save).toBeDefined();
    expect(messages.common.cancel).toBeDefined();
    expect(messages.common.delete).toBeDefined();
    expect(messages.common.confirm).toBeDefined();
  });

  it('has login section', () => {
    expect(messages.login).toBeDefined();
    expect(messages.login.title).toBeDefined();
    expect(messages.login.username).toBeDefined();
    expect(messages.login.password).toBeDefined();
    expect(messages.login.submit).toBeDefined();
  });

  it('has guards section', () => {
    expect(messages.guards).toBeDefined();
    expect(messages.guards.title).toBeDefined();
    expect(messages.guards.add).toBeDefined();
    expect(messages.guards.name).toBeDefined();
  });

  it('has weeks section', () => {
    expect(messages.weeks).toBeDefined();
    expect(messages.weeks.title).toBeDefined();
    expect(messages.weeks.status).toBeDefined();
  });

  it('has submissions section', () => {
    expect(messages.submissions).toBeDefined();
    expect(messages.submissions.title).toBeDefined();
  });

  it('has settings section', () => {
    expect(messages.settings).toBeDefined();
    expect(messages.settings.title).toBeDefined();
  });

  it('has week quick-links section (export page was removed)', () => {
    expect(messages.export).toBeUndefined();
    expect(messages.weeks.links).toBeDefined();
    expect(messages.weeks.links.exportConstraints).toBeDefined();
  });

  it('all messages are non-empty strings', () => {
    const checkNonEmpty = (obj, path = '') => {
      for (const [key, val] of Object.entries(obj)) {
        if (typeof val === 'function') {
          // Message formatters (e.g. positionsCount(n)) are valid.
          continue;
        }
        if (typeof val === 'object' && val !== null) {
          checkNonEmpty(val, `${path}.${key}`);
        } else {
          expect(typeof val).toBe('string');
          expect(val.length).toBeGreaterThan(0);
        }
      }
    };
    checkNonEmpty(messages);
  });
});