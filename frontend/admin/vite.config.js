import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Disable HTTP caching for everything this server hands out.
 *
 * The guard app is opened inside Telegram's in-app WebView, which caches a
 * WebApp aggressively by URL. With the unhashed dev-server module paths this
 * meant guards kept getting a *stale* version of the constraints form — an edit
 * looked like it succeeded but was never sent. `no-store` forces the WebView to
 * fetch fresh code every time. Applied to both the dev server and `vite preview`
 * (the latter is what is served in production via the cloudflared tunnel).
 */
function noCacheWebApp() {
  const attach = (server) => {
    server.middlewares.use((_req, res, next) => {
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');
      next();
    });
  };
  return {
    name: 'no-cache-webapp',
    configureServer: attach,
    configurePreviewServer: attach,
  };
}

// Shared dev/preview server options. `vite preview` does NOT inherit `server.*`
// (proxy, allowedHosts, …), so production — which serves the built `dist/` via
// `vite preview` behind the cloudflared tunnel — needs its own copy. The `/api`
// proxy in particular must exist on preview or every guard/admin request 404s.
const proxy = {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
};
// Extra hosts (e.g. a cloudflared tunnel domain) come from the environment OR
// the untracked .env/.env.local files, so deployment-specific domains never
// live in the repo: VITE_EXTRA_ALLOWED_HOSTS=a.example.com,.example.com
// (loadEnv is needed because Vite does NOT put .env values into process.env
// during config evaluation — a shell-exported var still wins.)
export default defineConfig(({ mode }) => {
  const fileEnv = loadEnv(mode, __dirname, '');
  const extraHosts =
    process.env.VITE_EXTRA_ALLOWED_HOSTS ?? fileEnv.VITE_EXTRA_ALLOWED_HOSTS;
  const allowedHosts = [
    'localhost',
    ...(extraHosts?.split(',').map((h) => h.trim()).filter(Boolean) ?? []),
  ];

  return {
    plugins: [react(), noCacheWebApp()],
    // Bundle down to a syntax level old mobile WebViews (Telegram's in-app browser
    // on older Android) can parse. The unbundled dev-server ESM graph was the
    // suspected cause of the blank guard page; a single transpiled bundle avoids it.
    build: {
      target: 'es2018',
    },
    server: {
      port: 3001,
      allowedHosts,
      proxy,
    },
    preview: {
      port: 3001,
      allowedHosts,
      proxy,
    },
  };
});