# config.py
# آمن للرفع على GitHub لأنه لا يحتوي أسرار.
# ضع الأسرار في Railway Variables أو في ملف .env محليًا فقط.

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def get_env(name, default=""):
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


TOKEN = get_env("TOKEN") or get_env("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("TOKEN/BOT_TOKEN is missing. Add it in Railway Variables.")

ADMIN_CHAT_ID = int(get_env("ADMIN_CHAT_ID", "1027957590"))

GOOGLE_SHEET_ID = get_env(
    "GOOGLE_SHEET_ID",
    "15T-HB2tPOtDCzmfN9AJlgX9YVTdu_Kg4rzJawE2rZBg"
)

GOOGLE_PRODUCTS_WORKSHEET = get_env("GOOGLE_PRODUCTS_WORKSHEET", "Products")
GOOGLE_ORDERS_WORKSHEET = get_env("GOOGLE_ORDERS_WORKSHEET", "Orders")
PRODUCTS_CACHE_TTL_SECONDS = int(get_env("PRODUCTS_CACHE_TTL_SECONDS", "60"))

GOOGLE_SERVICE_ACCOUNT_JSON = (
    get_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    or get_env("GOOGLE_CREDENTIALS")
)

print("ENV_CHECK_TOKEN =", "YES" if TOKEN else "NO", flush=True)
print("ENV_CHECK_GOOGLE_SHEET_ID =", "YES" if GOOGLE_SHEET_ID else "NO", flush=True)
print("ENV_CHECK_GOOGLE_JSON =", "YES" if GOOGLE_SERVICE_ACCOUNT_JSON else "NO", flush=True)
