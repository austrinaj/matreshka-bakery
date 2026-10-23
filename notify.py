import json
import os
import urllib.request

# Отправка сообщения в Telegram напрямую через Bot API.
# Так сайт может сообщить о новом заказе, даже если сам бот сейчас не запущен.


def send_to_admins(text):
    token = os.getenv("BOT_TOKEN")
    admin_ids = [x.strip() for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    if not token or not admin_ids:
        print("Уведомление не отправлено: нет BOT_TOKEN или ADMIN_IDS в .env")
        return
    for chat_id in admin_ids:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            # Заказ уже сохранён, поэтому ошибка Telegram не должна ломать сайт
            print(f"Не удалось отправить уведомление {chat_id}: {e}")
