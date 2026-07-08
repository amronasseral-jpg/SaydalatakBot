# config.py
# Professional Railway-safe configuration.
# Do NOT put real tokens or Google private keys inside this file.
# Put secrets in Railway > SaydalatakBot service > Variables.
# For local testing only, you may create local_settings.py, and it is ignored by Git.

import json
import os
import re
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _clean(value):
    if value is None:
        return ""
    value = str(value).strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1].strip()
    return value


def get_setting(name, default=""):
    return _clean(os.getenv(name) or default)


LOCAL = {}
try:
    from local_settings import LOCAL_SECRETS
    if isinstance(LOCAL_SECRETS, dict):
        LOCAL = LOCAL_SECRETS
except Exception:
    LOCAL = {}


def get_secret(name, default=""):
    return _clean(os.getenv(name) or LOCAL.get(name) or default)


TOKEN = get_secret("TOKEN") or get_secret("BOT_TOKEN")
BOT_TOKEN = TOKEN

ADMIN_CHAT_ID = int(get_secret("ADMIN_CHAT_ID", "1027957590"))

GOOGLE_SHEET_ID = get_secret(
    "GOOGLE_SHEET_ID",
    "15T-HB2tPOtDCzmfN9AJlgX9YVTdu_Kg4rzJawE2rZBg",
)

GOOGLE_PRODUCTS_WORKSHEET = get_secret("GOOGLE_PRODUCTS_WORKSHEET", "Products")
GOOGLE_ORDERS_WORKSHEET = get_secret("GOOGLE_ORDERS_WORKSHEET", "Orders")
PRODUCTS_CACHE_TTL_SECONDS = int(get_secret("PRODUCTS_CACHE_TTL_SECONDS", "60"))

GOOGLE_SERVICE_ACCOUNT_JSON = (
    get_secret("GOOGLE_SERVICE_ACCOUNT_JSON")
    or get_secret("GOOGLE_CREDENTIALS")
)


def _looks_like_telegram_token(token):
    return bool(re.match(r"^\d{8,12}:[A-Za-z0-9_-]{30,}$", token or ""))


def validate_config():
    print("CONFIG_SOURCE_TOKEN =", "YES" if TOKEN else "NO", flush=True)
    print("CONFIG_SOURCE_ADMIN_CHAT_ID =", ADMIN_CHAT_ID, flush=True)
    print("CONFIG_SOURCE_GOOGLE_SHEET_ID =", "YES" if GOOGLE_SHEET_ID else "NO", flush=True)
    print("CONFIG_SOURCE_GOOGLE_JSON =", "YES" if GOOGLE_SERVICE_ACCOUNT_JSON else "NO", flush=True)
    print("CONFIG_SOURCE_SERVICE_FILE =", "YES" if Path("service_account.json").exists() else "NO", flush=True)

    if not TOKEN:
        raise RuntimeError(
            "TOKEN/BOT_TOKEN is missing. Add TOKEN or BOT_TOKEN in Railway Variables "
            "inside the SaydalatakBot service, not another service."
        )

    if not _looks_like_telegram_token(TOKEN):
        raise RuntimeError(
            "TOKEN/BOT_TOKEN exists but format is invalid. Paste the exact token from BotFather."
        )

    if GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        except Exception as e:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON. Paste the full JSON content from { to }."
            ) from e
