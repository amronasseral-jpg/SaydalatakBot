import os

def get_env(name, default=None):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()

# Telegram
TOKEN = get_env("TOKEN") or get_env("BOT_TOKEN")
ADMIN_CHAT_ID = int(get_env("ADMIN_CHAT_ID", "1027957590"))

# Google Sheets
GOOGLE_SHEET_ID = get_env("GOOGLE_SHEET_ID")
GOOGLE_PRODUCTS_WORKSHEET = get_env("GOOGLE_PRODUCTS_WORKSHEET", "Products")
GOOGLE_ORDERS_WORKSHEET = get_env("GOOGLE_ORDERS_WORKSHEET", "Orders")
PRODUCTS_CACHE_TTL_SECONDS = int(get_env("PRODUCTS_CACHE_TTL_SECONDS", "60"))

# Service Account JSON
GOOGLE_SERVICE_ACCOUNT_JSON = (
    get_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    or get_env("GOOGLE_CREDENTIALS")
)

print("TOKEN:", "OK" if TOKEN else "MISSING")
print("ADMIN_CHAT_ID:", ADMIN_CHAT_ID)
print("GOOGLE_SHEET_ID:", "OK" if GOOGLE_SHEET_ID else "MISSING")
print("GOOGLE_SERVICE_ACCOUNT_JSON:", "OK" if GOOGLE_SERVICE_ACCOUNT_JSON else "MISSING")