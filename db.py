import sqlite3
from pathlib import Path

# База данных: один файл bakery.db рядом с кодом. Её используют и сайт, и бот.
DB_PATH = Path(__file__).parent / "bakery.db"

# Статусы заказа: ключ хранится в базе, подпись показывается людям
STATUSES = {
    "new": "Новый",
    "in_work": "Готовится",
    "ready": "Готов к выдаче",
    "done": "Выдан",
    "canceled": "Отменён",
}

# Стартовое меню (первые три позиции взяты из Яндекс Карт, остальное — шаблон)
SEED_PRODUCTS = [
    ("Дениш вишнёвый", "150 г", 130),
    ("Синнобомба", "140 г", 185),
    ("Слойка Швейцарская", "150 г", 130),
    ("Круассан классический", "80 г", 120),
    ("Пирожок с капустой", "120 г", 90),
    ("Кофе американо", "250 мл", 150),
]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # строки можно читать как словари: row["name"]
    return conn


def init_db():
    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                weight TEXT,
                price INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                pickup_time TEXT,
                comment TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                total INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            CREATE TABLE IF NOT EXISTS order_items (
                order_id INTEGER NOT NULL REFERENCES orders(id),
                product_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                qty INTEGER NOT NULL
            );
        """)
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO products (name, weight, price) VALUES (?, ?, ?)",
                SEED_PRODUCTS,
            )


# ---------- Товары ----------

def get_products(only_active=True):
    sql = "SELECT * FROM products"
    if only_active:
        sql += " WHERE active = 1"
    with connect() as conn:
        return conn.execute(sql + " ORDER BY id").fetchall()


def add_product(name, weight, price):
    with connect() as conn:
        conn.execute(
            "INSERT INTO products (name, weight, price) VALUES (?, ?, ?)",
            (name, weight, price),
        )


def toggle_product(product_id):
    with connect() as conn:
        conn.execute("UPDATE products SET active = 1 - active WHERE id = ?", (product_id,))


# ---------- Заказы ----------

def create_order(customer_name, phone, pickup_time, comment, items):
    """items — список пар (товар, количество). Возвращает номер заказа."""
    total = sum(p["price"] * qty for p, qty in items)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO orders (customer_name, phone, pickup_time, comment, total) "
            "VALUES (?, ?, ?, ?, ?)",
            (customer_name, phone, pickup_time, comment, total),
        )
        order_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO order_items (order_id, product_name, price, qty) VALUES (?, ?, ?, ?)",
            [(order_id, p["name"], p["price"], qty) for p, qty in items],
        )
    return order_id


def get_orders(status=None, limit=100):
    sql = "SELECT * FROM orders"
    params = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def get_order(order_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_order_items(order_id):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
        ).fetchall()


def set_status(order_id, status):
    if status not in STATUSES:
        raise ValueError(f"Неизвестный статус: {status}")
    with connect() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))


def today_stats():
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(total), 0) AS revenue FROM orders "
            "WHERE date(created_at) = date('now', 'localtime') AND status != 'canceled'"
        ).fetchone()
    return row["cnt"], row["revenue"]


def get_customers():
    """Клиенты = уникальные телефоны из заказов, со счётчиком и суммой."""
    with connect() as conn:
        return conn.execute(
            "SELECT phone, MAX(customer_name) AS name, COUNT(*) AS orders_count, "
            "SUM(total) AS total_spent, MAX(created_at) AS last_order "
            "FROM orders WHERE status != 'canceled' "
            "GROUP BY phone ORDER BY total_spent DESC"
        ).fetchall()


def format_order(order):
    """Текст заказа для Telegram (используют и сайт, и бот)."""
    lines = [
        f"🧾 Заказ №{order['id']} — {STATUSES[order['status']]}",
        f"👤 {order['customer_name']}, {order['phone']}",
    ]
    if order["pickup_time"]:
        lines.append(f"🕒 Забрать: {order['pickup_time']}")
    for item in get_order_items(order["id"]):
        lines.append(f"• {item['product_name']} × {item['qty']} = {item['price'] * item['qty']} ₽")
    lines.append(f"💰 Итого: {order['total']} ₽")
    if order["comment"]:
        lines.append(f"💬 {order['comment']}")
    return "\n".join(lines)
