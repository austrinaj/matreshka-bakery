import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

import db

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
# Кто может пользоваться CRM в боте: Telegram ID через запятую
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()


def is_admin(user_id):
    return user_id in ADMIN_IDS


def status_keyboard(order_id):
    """Кнопки под заказом: сменить статус в один клик."""
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"st:{order_id}:{key}")
        for key, label in db.STATUSES.items()
    ]
    # Раскладываем по 2 кнопки в ряд
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(CommandStart())
async def start(message: Message):
    if not is_admin(message.from_user.id):
        # Твой ID нужно вписать в ADMIN_IDS в файле .env
        await message.answer(
            f"Привет! Это CRM пекарни «Матрёшка».\n"
            f"Доступ только для сотрудников. Твой Telegram ID: {message.from_user.id}"
        )
        return
    await message.answer(
        "🥐 CRM пекарни «Матрёшка»\n\n"
        "/orders — активные заказы\n"
        "/all — последние 10 заказов\n"
        "/order 5 — заказ №5\n"
        "/today — статистика за сегодня\n"
        "/menu — текущее меню"
    )


@dp.message(Command("orders"))
async def active_orders(message: Message):
    if not is_admin(message.from_user.id):
        return
    orders = [o for o in db.get_orders() if o["status"] in ("new", "in_work", "ready")]
    if not orders:
        await message.answer("Активных заказов нет 🎉")
        return
    for o in reversed(orders):
        await message.answer(db.format_order(o), reply_markup=status_keyboard(o["id"]))


@dp.message(Command("all"))
async def all_orders(message: Message):
    if not is_admin(message.from_user.id):
        return
    orders = db.get_orders(limit=10)
    if not orders:
        await message.answer("Заказов пока нет")
        return
    text = "\n".join(
        f"№{o['id']} · {o['created_at'][5:16]} · {o['customer_name']} · "
        f"{o['total']} ₽ · {db.STATUSES[o['status']]}"
        for o in orders
    )
    await message.answer(text)


@dp.message(Command("order"))
async def one_order(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Напиши номер: /order 5")
        return
    order = db.get_order(int(parts[1]))
    if not order:
        await message.answer("Такого заказа нет")
        return
    await message.answer(db.format_order(order), reply_markup=status_keyboard(order["id"]))


@dp.message(Command("today"))
async def today(message: Message):
    if not is_admin(message.from_user.id):
        return
    count, revenue = db.today_stats()
    await message.answer(f"📊 Сегодня: {count} заказов на {revenue} ₽")


@dp.message(Command("menu"))
async def menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    text = "\n".join(f"• {p['name']} ({p['weight']}) — {p['price']} ₽" for p in db.get_products())
    await message.answer("🥐 Меню:\n" + text)


# Нажатие на кнопку статуса. callback_data выглядит как "st:5:ready"
@dp.callback_query(F.data.startswith("st:"))
async def change_status(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, order_id, status = callback.data.split(":")
    db.set_status(int(order_id), status)
    order = db.get_order(int(order_id))
    await callback.message.edit_text(db.format_order(order), reply_markup=status_keyboard(order["id"]))
    await callback.answer(f"Статус: {db.STATUSES[status]}")


async def main():
    if not TOKEN:
        print("Ошибка: не найден BOT_TOKEN. Проверь файл .env")
        return
    db.init_db()
    bot = Bot(TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
