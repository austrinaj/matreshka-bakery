import json
import os
import urllib.request

# Работа с Telegram Bot API напрямую, без библиотек.
# Любой запрос к боту = обращение к адресу https://api.telegram.org/bot<токен>/<метод>


def api(method, **params):
    token = os.getenv("BOT_TOKEN")
    if not token:
        print(f"Telegram: нет BOT_TOKEN в .env, метод {method} не вызван")
        return None
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.load(resp).get("result")
    except Exception as e:
        # Ошибка Telegram не должна ломать сайт
        print(f"Telegram: ошибка в {method}: {e}")
        return None


def admin_ids():
    """Кто может пользоваться CRM в боте: Telegram ID через запятую в .env"""
    return {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}


def send_to_admins(text):
    for chat_id in admin_ids():
        api("sendMessage", chat_id=chat_id, text=text)
