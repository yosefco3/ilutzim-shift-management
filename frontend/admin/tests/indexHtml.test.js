import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// The guard WebApp needs the Telegram SDK loaded BEFORE the app module, or a
// `web_app` button opens to a blank dark screen (ready()/expand() never run).
describe('index.html', () => {
  // vitest runs with cwd = frontend/admin, where index.html lives.
  const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');

  it('loads the Telegram WebApp SDK', () => {
    expect(html).toContain('telegram.org/js/telegram-web-app.js');
  });

  it('loads the SDK before the app entry module', () => {
    const sdkIdx = html.indexOf('telegram-web-app.js');
    const appIdx = html.indexOf('/src/main.jsx');
    expect(sdkIdx).toBeGreaterThan(-1);
    expect(appIdx).toBeGreaterThan(-1);
    expect(sdkIdx).toBeLessThan(appIdx);
  });

  // ErrorBoundary can't catch a module that fails to load/parse (the classic
  // blank mobile-WebView page). The inline guard must paint into #root on an
  // uncaught error and when React never mounts (timeout), so a failure is never
  // an indistinguishable white screen.
  it('has a white-screen guard for module load failures and non-mounting', () => {
    expect(html).toContain("addEventListener('error'");
    expect(html).toContain("addEventListener('unhandledrejection'");
    expect(html).toContain('setTimeout');
    expect(html).toContain("getElementById('root')");
  });
});
