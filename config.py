import os

def get_env(name, default=""):
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else value

# Railway Variables: TOKEN أو BOT_TOKEN
TOKEN = get_env("TOKEN") or get_env("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("TOKEN/BOT_TOKEN is missing from Railway Variables")

ADMIN_CHAT_ID = int(get_env("ADMIN_CHAT_ID", "1027957590"))

GOOGLE_SHEET_ID = get_env("GOOGLE_SHEET_ID")

# يدعم الاسمين لتفادي اختلاف الاسم في Railway
GOOGLE_SERVICE_ACCOUNT_JSON = (
    get_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    or get_env("GOOGLE_CREDENTIALS")
)

# Debug آمن بدون طباعة أسرار
print("ENV_CHECK_TOKEN =", "YES" if TOKEN else "NO", flush=True)
print("ENV_CHECK_ADMIN_CHAT_ID =", "YES" if ADMIN_CHAT_ID else "NO", flush=True)
print("ENV_CHECK_GOOGLE_SHEET_ID =", "YES" if GOOGLE_SHEET_ID else "NO", flush=True)
print("ENV_CHECK_GOOGLE_JSON =", "YES" if GOOGLE_SERVICE_ACCOUNT_JSON else "NO", flush=True)
