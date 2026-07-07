import os

TOKEN = (
    os.getenv("TOKEN")
    or os.getenv("BOT_TOKEN")
    or ""
).strip()

if not TOKEN:
    raise RuntimeError("TOKEN is missing")

ADMIN_CHAT_ID = int((os.getenv("ADMIN_CHAT_ID") or "1027957590").strip())