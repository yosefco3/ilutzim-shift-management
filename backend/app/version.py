"""Application build/version token used for cache-busting the Telegram WebApp URL.

Telegram's in-app WebView caches a WebApp aggressively, keyed by its URL. After a
deploy, guards can keep getting a *stale* version of the constraints form — so an
edit looks like it succeeded but is never sent. Appending ``?v=APP_VERSION`` to the
WebApp URL makes Telegram treat it as a fresh URL after each (re)start, defeating
that cache.

The token is computed once at process start, so it is stable within a single
server lifetime (hashed assets still cache within a session) but changes on every
restart / deploy.
"""

import time

APP_VERSION: str = str(int(time.time()))
