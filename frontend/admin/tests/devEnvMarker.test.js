import { describe, it, expect, beforeAll } from 'vitest';
import fs from 'fs';
import path from 'path';

/**
 * DEV visual marker — `vite dev` adds .dev-env on <body> (App.jsx), which
 * retints --bg/--navbar-bg in admin.css. The production build must never get
 * the class, so the rule must be gated on import.meta.env.DEV.
 */
describe('dev-env background marker', () => {
  let appJsx;
  let adminCss;

  beforeAll(() => {
    appJsx = fs.readFileSync(path.resolve(__dirname, '../src/App.jsx'), 'utf-8');
    adminCss = fs.readFileSync(
      path.resolve(__dirname, '../src/styles/admin.css'), 'utf-8',
    );
  });

  it('App.jsx adds the body class for dev builds OR dev-ish hostnames only', () => {
    // Dev is detected by build mode or hostname (localhost / dev.*) — the
    // prod domain (app.safrasecure.uk) must never match.
    expect(appJsx).toContain('import.meta.env.DEV');
    expect(appJsx).toContain("'localhost'");
    expect(appJsx).toContain("startsWith('dev.')");
    expect(appJsx).toMatch(/if\s*\(IS_DEV_ENV\)\s*{\s*document\.body\.classList\.add\('dev-env'\)/);
    // Exactly one add-site, and none outside the guard.
    expect(appJsx.match(/classList\.add\('dev-env'\)/g)).toHaveLength(1);
  });

  it('admin.css retints the app background for body.dev-env', () => {
    const rule = adminCss.match(/body\.dev-env\s*{([^}]*)}/);
    expect(rule).not.toBeNull();
    expect(rule[1]).toContain('--bg:');
    expect(rule[1]).toContain('--navbar-bg:');
    // The dev tint must differ from the standard background.
    expect(rule[1]).not.toContain('#0f1115');
  });
});
