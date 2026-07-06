import { describe, it, expect, beforeAll } from 'vitest';
import fs from 'fs';
import path from 'path';

describe('guard.css', () => {
  const cssPath = path.resolve(__dirname, '../src/styles/guard.css');
  let cssContent;

  beforeAll(() => {
    cssContent = fs.readFileSync(cssPath, 'utf-8');
  });

  it('should exist', () => {
    expect(fs.existsSync(cssPath)).toBe(true);
  });

  it('should wrap all selectors under .guard-layout', () => {
    // Check that key selectors are prefixed
    expect(cssContent).toContain('.guard-layout');
    expect(cssContent).toContain('.guard-layout .day-row');
    expect(cssContent).toContain('.guard-layout .submit-btn');
    expect(cssContent).toContain('.guard-layout .lock-banner');
  });

  it('should not have bare body or html selectors', () => {
    // Should not have global body/html rules (those are in admin.css)
    const bareBody = /^body\s*\{/m;
    const bareHtml = /^html\s*\{/m;
    expect(bareBody.test(cssContent)).toBe(false);
    expect(bareHtml.test(cssContent)).toBe(false);
  });

  it('should not have global * reset', () => {
    const globalReset = /^\*\s*,?\s*\*/m;
    expect(globalReset.test(cssContent)).toBe(false);
  });

  it('should include Telegram theme variables', () => {
    expect(cssContent).toContain('--tg-bg');
    expect(cssContent).toContain('--tg-btn');
    expect(cssContent).toContain('--tg-text');
  });

  it('should include all major component styles', () => {
    expect(cssContent).toContain('.day-row');
    expect(cssContent).toContain('.day-shifts');
    expect(cssContent).toContain('.shift-row');
    expect(cssContent).toContain('.shift-toggle-btn');
    expect(cssContent).toContain('.shift-hours');
    expect(cssContent).toContain('.notes-input');
    expect(cssContent).toContain('.submit-btn');
    expect(cssContent).toContain('.lock-banner');
    expect(cssContent).toContain('.error-banner');
    expect(cssContent).toContain('.success-banner');
  });

  it('should set direction rtl', () => {
    expect(cssContent).toContain('direction: rtl');
  });

  it('should set max-width for mobile', () => {
    expect(cssContent).toContain('max-width');
    expect(cssContent).toContain('480px');
  });
});