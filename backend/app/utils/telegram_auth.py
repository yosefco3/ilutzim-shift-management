"""
Telegram WebApp authentication utilities.

Validates Telegram WebApp init_data using HMAC-SHA256 as documented at:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
import urllib.parse

# init_data older than this is rejected, even if the HMAC is valid. Limits the
# window in which a leaked/captured init_data string can be replayed.
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours


def validate_telegram_web_app_data(
    init_data: str, bot_token: str, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS
) -> dict | None:
    """
    Validate Telegram WebApp init_data and return parsed dict if valid.

    Rejects data whose ``auth_date`` is older than ``max_age_seconds`` (set to
    0 or a negative value to disable the freshness check).

    Returns None if validation fails.
    """
    try:
        parsed = urllib.parse.parse_qs(init_data)
        hash_value = parsed.get("hash", [None])[0]
        if not hash_value:
            return None

        # Build data-check-string: sorted key=value pairs except 'hash'
        data_check_items = []
        for key in sorted(parsed.keys()):
            if key == "hash":
                continue
            value = parsed[key][0]
            data_check_items.append(f"{key}={value}")
        data_check_string = "\n".join(data_check_items)

        # Compute secret key: HMAC-SHA256(bot_token, "WebAppData")
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()

        # Compute hash: HMAC-SHA256(secret_key, data_check_string)
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        # Compare hashes
        if not hmac.compare_digest(computed_hash, hash_value):
            return None

        # Reject stale init_data (replay protection) once the HMAC is trusted.
        if max_age_seconds and max_age_seconds > 0:
            auth_date_raw = parsed.get("auth_date", [None])[0]
            try:
                auth_date = int(auth_date_raw)
            except (TypeError, ValueError):
                return None
            if time.time() - auth_date > max_age_seconds:
                return None

        # Return parsed data as flat dict
        result = {}
        for key, values in parsed.items():
            result[key] = values[0]
        return result

    except Exception:
        return None


def get_telegram_user_id(init_data: str, bot_token: str) -> str | None:
    """
    Validate init_data and extract the Telegram user ID.

    Returns the user ID string if valid, None otherwise.
    """
    data = validate_telegram_web_app_data(init_data, bot_token)
    if data is None:
        return None

    user_json = data.get("user")
    if not user_json:
        return None

    try:
        user = json.loads(user_json)
        return str(user.get("id"))
    except (json.JSONDecodeError, AttributeError):
        return None