import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID')) if os.getenv('OWNER_ID') else None

if not TOKEN:
    print("Iltimos .env faylga BOT_TOKEN ni qo'ying (BOT_TOKEN=YOUR_TOKEN)")
    raise SystemExit(1)