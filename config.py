import os

TOKEN = (os.getenv("TOKEN") or "").strip()
if not TOKEN:
    raise RuntimeError("TOKEN is missing. Add TOKEN in Railway Variables as one line, then Redeploy.")

ADMIN_CHAT_ID = int((os.getenv("ADMIN_CHAT_ID") or "1027957590").strip())
