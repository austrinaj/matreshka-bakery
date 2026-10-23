from pathlib import Path

from dotenv import load_dotenv

import db
from tg import admin_ids, api

# Логика бота. handle_update() получает одно событие от Telegram
# (сообщение или нажатие кнопки) и отвечает на него.
#
# На хостинге события присылает сам Telegram на сайт (вебхук, см. app.py).
# На своём компьютере можно запустить `python bot.py`: тогда бот сам
# спрашивает Telegram о новых сообщениях (polling).

HELP = (
    "🥐 CRM пекарни «Матрёшка»\n\n"
    "/orders — активные заказы\n"
    "/all — последние 10 заказов\n"
    "/order 5 — заказ №5\n"
    "/today — статистика за сегодня\n"
    "/menu — текущее меню"
)


def status_keyboard(order_id):
    """Кнопки под заказом: сменить статус в один клик. По 2 кнопки в ряд."""
    buttons = [
        {"text": label, "callback_data": f"st:{order_id}:{key}"}
        for key, label in db.STATUSES.items()
    ]
    return {"inline_keyboard": [buttons[i:i + 2] for i in range(0, len(buttons), 2)]}


def send_order(chat_id, order):
    api("sendMessage", chat_id=chat_id, text=db.format_order(order),
        reply_markup=status_keyboard(order["id"]))


def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")
    command = text.split()[0].split("@")[0] if text else ""

    def reply(answer):
        api("sendMessage", chat_id=chat_id, text=answer)

    if user_id not in admin_ids():
        # Свой ID нужно вписать в ADMIN_IDS в файле .env
        reply("Привет! Это CRM пекарни «Матрёшка».\n"
              f"Доступ только для сотрудников. Твой Telegram ID: {user_id}")
        return

    if command == "/orders":
        orders = [o for o in db.get_orders() if o["status"] in ("new", "in_work", "ready")]
        if not orders:
            reply("Активных заказов нет 🎉")
        for o in reversed(orders):
            send_order(chat_id, o)

    elif command == "/all":
        orders = db.get_orders(limit=10)
        reply("\n".join(
            f"№{o['id']} · {o['created_at'][5:16]} · {o['customer_name']} · "
            f"{o['total']} ₽ · {db.STATUSES[o['status']]}"
            for o in orders
        ) or "Заказов пока нет")

    elif command == "/order":
        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            reply("Напиши номер: /order 5")
            return
        order = db.get_order(int(parts[1]))
        if order:
            send_order(chat_id, order)
        else:
            reply("Такого заказа нет")

    elif command == "/today":
        count, revenue = db.today_stats()
        reply(f"📊 Сегодня: {count} заказов на {revenue} ₽")

    elif command == "/menu":
        reply("🥐 Меню:\n" + "\n".join(
            f"• {p['name']} ({p['weight']}) — {p['price']} ₽" for p in db.get_products()
        ))

    else:
        reply(HELP)


def handle_callback(callback):
    """Нажатие на кнопку статуса. callback_data выглядит как "st:5:ready" """
    if callback["from"]["id"] not in admin_ids():
        api("answerCallbackQuery", callback_query_id=callback["id"],
            text="Нет доступа", show_alert=True)
        return
    _, order_id, status = callback["data"].split(":")
    db.set_status(int(order_id), status)
    order = db.get_order(int(order_id))
    msg = callback["message"]
    api("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
        text=db.format_order(order), reply_markup=status_keyboard(order["id"]))
    api("answerCallbackQuery", callback_query_id=callback["id"],
        text=f"Статус: {db.STATUSES[status]}")


def handle_update(update):
    if "message" in update:
        handle_message(update["message"])
    elif "callback_query" in update:
        handle_callback(update["callback_query"])


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
            handle_update(update)


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent / ".env")
    db.init_db()
    polling()
