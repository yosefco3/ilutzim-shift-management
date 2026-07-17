import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/setup.js',
    // Pin feature flags for tests regardless of the developer's local
    // .env/.env.local (vitest loads them via Vite): the procedures flag ships
    // default-OFF and the flag-off gating tests assert that.
    env: {
      VITE_PROCEDURES_ENABLED: 'false',
    },
  },
});