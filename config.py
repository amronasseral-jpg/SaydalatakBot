import os

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN/TOKEN is missing in Railway Variables."
    )

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "1027957590"))

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")