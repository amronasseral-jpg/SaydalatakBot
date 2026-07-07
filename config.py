import os

def get_env(name):
    value = os.environ.get(name)
    return value.strip() if value else ""

# طباعة للتأكد من المتغيرات الموجودة في السيرفر أثناء التشغيل
print("ALL_ENV_KEYS =", list(os.environ.keys()), flush=True)

# يقرأ من السيرفر، وإذا لم يجده يضع التوكن مباشرة كخيار احتياطي
TOKEN = get_env("BOT_TOKEN") or "8806198611:AAFlzQpYZ1pQ-T5IAKYgWClXrxYDPCaYxOs"

print("ENV_CHECK_BOT_TOKEN =", "YES" if TOKEN else "NO", flush=True)
print("ENV_CHECK_ADMIN_CHAT_ID =", "YES" if get_env("ADMIN_CHAT_ID") else "NO", flush=True)

if not TOKEN or "8806198611:AAFlzQpYZ1pQ-T5IAKYgWClXrxYDPCaYxOs" in TOKEN:
    raise RuntimeError("BOT_TOKEN is missing! Please provide a valid token.")

ADMIN_CHAT_ID = int(get_env("ADMIN_CHAT_ID") or "1027957590")

GOOGLE_SHEET_ID = get_env("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = get_env("GOOGLE_SERVICE_ACCOUNT_JSON")