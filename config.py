import os

TOKEN = os.getenv("TOKEN")

if TOKEN is None:
    raise ValueError("TOKEN environment variable is not set")

TOKEN = TOKEN.strip()

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))