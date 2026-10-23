import os
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

import bot
import db
from tg import send_to_admins

# Ищем .env рядом с app.py (на хостинге программа запускается из другой папки)
load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)
# Секретный ключ нужен Flask, чтобы подписывать сессию (вход в CRM)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

db.init_db()


# ---------- Публичный сайт ----------

@app.route("/")
def index():
    return render_template("index.html", products=db.get_products())


@app.route("/order", methods=["POST"])
def order():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    if not name or not phone:
        flash("Укажите имя и телефон")
        return redirect(url_for("index") + "#order")

    # В форме у каждого товара поле qty_<id>. Собираем те, где количество > 0.
    items = []
    for p in db.get_products():
        qty = request.form.get(f"qty_{p['id']}", "0")
        if qty.isdigit() and int(qty) > 0:
            items.append((p, int(qty)))
    if not items:
        flash("Выберите хотя бы одну позицию")
        return redirect(url_for("index") + "#order")

    order_id = db.create_order(
        name, phone, request.form.get("pickup_time", ""), request.form.get("comment", ""), items
    )
    send_to_admins("🔔 Новый заказ с сайта!\n\n" + db.format_order(db.get_order(order_id)))
    return render_template("thanks.html", order_id=order_id)


# ---------- CRM (админка) ----------

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_orders"))
        flash("Неверный пароль")
    return render_template("login.html")


@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_orders():
    status = request.args.get("status") or None
    orders = db.get_orders(status)
    items = {o["id"]: db.get_order_items(o["id"]) for o in orders}
    count, revenue = db.today_stats()
    return render_template(
        "admin_orders.html", orders=orders, items=items, statuses=db.STATUSES,
        current=status, today_count=count, today_revenue=revenue,
    )


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@login_required
def change_status(order_id):
    db.set_status(order_id, request.form["status"])
    return redirect(request.referrer or url_for("admin_orders"))


@app.route("/admin/products", methods=["GET", "POST"])
@login_required
def admin_products():
    if request.method == "POST":
        price = request.form.get("price", "")
        if request.form.get("name") and price.isdigit():
            db.add_product(request.form["name"], request.form.get("weight", ""), int(price))
        else:
            flash("Нужно название и цена числом")
        return redirect(url_for("admin_products"))
    return render_template("admin_products.html", products=db.get_products(only_active=False))


@app.route("/admin/products/<int:product_id>/toggle", methods=["POST"])
@login_required
def toggle_product(product_id):
    db.toggle_product(product_id)
    return redirect(url_for("admin_products"))


@app.route("/admin/customers")
@login_required
def admin_customers():
    return render_template("admin_customers.html", customers=db.get_customers())


# ---------- Telegram-бот (вебхук) ----------

@app.route("/tg-webhook", methods=["POST"])
def tg_webhook():
    # Telegram присылает секрет в заголовке: так чужой не сможет притвориться им
    secret = os.getenv("WEBHOOK_SECRET")
    if not secret or request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        abort(403)
    # Ответ бота отдаём прямо в ответе на запрос Telegram (сервер сам в Telegram не ходит)
    answer = bot.handle_update(request.get_json())
    return jsonify(answer or {})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
