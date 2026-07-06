/**
 * Hook to access Telegram WebApp SDK.
 * Returns initData, user info, theme params, mainButton API, and close.
 *
 * In dev mode (no Telegram context), provides a fallback sentinel so the
 * app can be tested in a regular browser.
 */
import { useMemo } from "react";

const DEV_INIT_DATA = "__DEV_MODE__";

export function useTelegram() {
  return useMemo(() => {
    const tg = window?.Telegram?.WebApp;
    const isTelegram = Boolean(tg?.initData);
    const isDevMode = !isTelegram;

    return {
      /** Telegram initData string for API authentication (dev sentinel outside TG) */
      initData: tg?.initData || (isDevMode ? DEV_INIT_DATA : ""),
      /** Whether we are running outside Telegram (regular browser) */
      isDevMode,
      /** User info from initDataUnsafe (mock in dev) */
      user: tg?.initDataUnsafe?.user || (isDevMode
        ? { id: "dev-user", first_name: "Dev", last_name: "User" }
        : { id: null, first_name: "", last_name: "" }),
      /** Telegram theme color params */
      themeParams: tg?.themeParams || {},
      /** Telegram MainButton API */
      mainButton: {
        show: (text) => {
          if (tg?.MainButton) {
            tg.MainButton.text = text || "Submit";
            tg.MainButton.show();
          }
        },
        hide: () => tg?.MainButton?.hide(),
        onClick: (fn) => tg?.MainButton?.onClick(fn),
        offClick: (fn) => tg?.MainButton?.offClick(fn),
      },
      /** Close the WebApp */
      close: () => tg?.close(),
      /** Raw Telegram WebApp reference */
      webApp: tg,
    };
  }, []);
}