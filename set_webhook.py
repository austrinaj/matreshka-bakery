import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

from tg import api

# Говорит Telegram: «присылай все сообщения бота на мой сайт».
# Запуск (на хостинге, один раз):  python set_webhook.py https://austrinaj.pythonanywhere.com

load_dotenv(Path(__file__).parent / ".env")

if len(sys.argv) < 2:
    print("Укажи адрес сайта: python set_webhook.py https://твой-сайт")
    sys.exit(1)

secret =os.getenv("WEBHOOK_SECRET")
if not secret:
    print("Добавь в .env строку WEBHOOK_SECRET=" + secrets.token_hex(16))
    sys.exit(1)

url = sys.argv[1].rstrip("/") + "/tg-webhook"
ok = api("setWebhook", url=url, secret_token=secret)
print("Готово! Вебхук:" if ok else "Не получилось. Вебхук:", url)
