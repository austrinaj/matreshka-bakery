from pathlib import Path

from dotenv import load_dotenv

import db
from tg import admin_ids, api

# Логика бота. handle_update() получает одно событие от Telegram
# (сообщение или нажатие кнопки) и возвращает ОДИН ответ — словарь вида
# {"method": "sendMessage", "chat_id": ..., "text": ...}
#
# Почему один ответ: на хостинге (вебхук, см. app.py) мы отдаём его Telegram
# прямо в ответе на его запрос. Так серверу не нужно самому подключаться
# к Telegram (на бесплатном PythonAnywhere это заблокировано).
#
# На своём компьютере можно запустить `python bot.py`: тогда бот сам
# спрашивает Telegram о новых сообщениях (polling) и отправляет ответы.

HELP = (
    "🥐 CRM пекарни «Матрёшка»\n\n"
    "/orders — активные заказы\n"
    "/all — последние 10 заказов\n"
    "/order 5 — заказ №5\n"
    "/today — статистика за сегодня\n"
    "/menu — текущее меню"
)


def send(chat_id, text, keyboard=None):
    answer = {"method": "sendMessage", "chat_id": chat_id, "text": text}
    if keyboard:
        answer["reply_markup"] = keyboard
    return answer


def edit(message, text, keyboard=None):
    """Заменить текст и кнопки у уже отправленного сообщения."""
    answer = {"method": "editMessageText", "chat_id": message["chat"]["id"],
              "message_id": message["message_id"], "text": text}
    if keyboard:
        answer["reply_markup"] = keyboard
    return answer


def order_keyboard(order_id):
    """Кнопки под заказом: статусы по 2 в ряд и «назад к списку»."""
    buttons = [
        {"text": label, "callback_data": f"st:{order_id}:{key}"}
        for key, label in db.STATUSES.items()
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([{"text": "← К списку заказов", "callback_data": "list"}])
    return {"inline_keyboard": rows}


def active_orders_view():
    """Текст и кнопки для списка активных заказов."""
    orders = [o for o in db.get_orders() if o["status"] in ("new", "in_work", "ready")]
    if not orders:
        return "Активных заказов нет 🎉", None
    text = "📋 Активные заказы:\n\n" + "\n".join(
        f"№{o['id']} · {o['customer_name']} · {o['total']} ₽ · {db.STATUSES[o['status']]}"
        for o in orders
    )
    buttons = [{"text": f"№{o['id']}", "callback_data": f"open:{o['id']}"} for o in orders]
    keyboard = {"inline_keyboard": [buttons[i:i + 4] for i in range(0, len(buttons), 4)]}
    return text, keyboard


def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")
    command = text.split()[0].split("@")[0] if text else ""

    if user_id not in admin_ids():
        # Свой ID нужно вписать в ADMIN_IDS в файле .env
        return send(chat_id, "Привет! Это CRM пекарни «Матрёшка».\n"
                             f"Доступ только для сотрудников. Твой Telegram ID: {user_id}")

    if command == "/orders":
        return send(chat_id, *active_orders_view())

    if command == "/all":
        orders = db.get_orders(limit=10)
        return send(chat_id, "\n".join(
            f"№{o['id']} · {o['created_at'][5:16]} · {o['customer_name']} · "
            f"{o['total']} ₽ · {db.STATUSES[o['status']]}"
            for o in orders
        ) or "Заказов пока нет")

    if command == "/order":
        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return send(chat_id, "Напиши номер: /order 5")
        order = db.get_order(int(parts[1]))
        if not order:
            return send(chat_id, "Такого заказа нет")
        return send(chat_id, db.format_order(order), order_keyboard(order["id"]))

    if command == "/today":
        count, revenue = db.today_stats()
        return send(chat_id, f"📊 Сегодня: {count} заказов на {revenue} ₽")

    if command == "/menu":
        return send(chat_id, "🥐 Меню:\n" + "\n".join(
            f"• {p['name']} ({p['weight']}) — {p['price']} ₽" for p in db.get_products()
        ))

    return send(chat_id, HELP)


def handle_callback(callback):
    """Нажатие на кнопку. callback_data: "open:5", "st:5:ready" или "list" """
    message = callback["message"]
    if callback["from"]["id"] not in admin_ids():
        return {"method": "answerCallbackQuery", "callback_query_id": callback["id"],
                "text": "Нет доступа", "show_alert": True}

    parts = callback["data"].split(":")
    if parts[0] == "list":
        return edit(message, *active_orders_view())

    order_id = int(parts[1])
    if parts[0] == "st":
        db.set_status(order_id, parts[2])
    order = db.get_order(order_id)
    if not order:
        return edit(message, "Такого заказа нет")
    return edit(message, db.format_order(order), order_keyboard(order_id))


def handle_update(update):
    if "message" in update:
        return handle_message(update["message"])
    if "callback_query" in update:
        return handle_callback(update["callback_query"])
    return None


def polling():
    """Локальный режим: спрашиваем Telegram о новых событиях в цикле."""
    # Если у бота включён вебхук (бот на хостинге), polling не работает.
    # Выключаем вебхук: после этого бот на хостинге перестанет отвечать,
    # пока снова не запустишь set_webhook.py
    api("deleteWebhook")
    me = api("getMe")
    if not me:
        print("Не удалось подключиться к Telegram. Проверь BOT_TOKEN в .env")
        return
    print(f"Бот @{me['username']} запущен. Остановить: Ctrl+C")
    offset = 0
    while True:
        updates = api("getUpdates", offset=offset, timeout=30) or []
        for update in updates:
            offset = update["update_id"] + 1
            answer = handle_update(update)
            if answer:
                method = answer.pop("method")
                api(method, **answer)


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent / ".env")
    db.init_db()
    polling()
