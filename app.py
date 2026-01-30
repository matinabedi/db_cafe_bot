# cafe_cashier_bot.py
import os
import telebot
from telebot import types
import psycopg2
from psycopg2 import Error
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_URI = os.environ.get("DB_URI")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
print(BOT_TOKEN)


bot = telebot.TeleBot(BOT_TOKEN)

# نگهداری سشن‌های لاگین و دادهٔ موقتی کاربران
# ساختار پیشنهادی:
# user_sessions = { chat_id: { "logged_in": True/False, "temp": {...} } }
user_sessions = {}

def ensure_session(chat_id):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {"logged_in": False, "temp": {}}
    return user_sessions[chat_id]

def check_login(chat_id):
    sess = ensure_session(chat_id)
    return sess.get("logged_in", False)

def login_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if not check_login(message.chat.id):
            bot.send_message(message.chat.id, "لطفاً ابتدا وارد سیستم شوید.", reply_markup=login_menu())
            return
        return func(message, *args, **kwargs)
    return wrapper

def get_db_connection():
    try:
        conn = psycopg2.connect(DB_URI)
        return conn
    except Error as e:
        print("خطا در اتصال به پایگاه داده:", e)
        return None

def create_tables():
    conn = get_db_connection()
    if conn is None:
        print("اتصال DB برقرار نشد — جداول ساخته نشد.")
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS category (
                id SERIAL PRIMARY KEY,
                name VARCHAR NOT NULL UNIQUE
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR NOT NULL,
                price NUMERIC(10,2) NOT NULL,
                category_id INTEGER REFERENCES category(id) ON DELETE SET NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                name VARCHAR NOT NULL,
                phone VARCHAR
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total NUMERIC(10,2) DEFAULT 0,
                status VARCHAR(20) DEFAULT 'pending' -- pending, served, cancelled
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                price_at_order NUMERIC(10,2) NOT NULL
            );
        """)
        conn.commit()
        cur.close()
        print("جداول ساخته یا بررسی شدند.")
    except Error as e:
        print("خطا در ایجاد جداول:", e)
    finally:
        if conn:
            conn.close()

# ---------- کیبوردها ----------
def login_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton('ورود به سیستم'))
    return markup

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton('محصولات'),
        types.KeyboardButton('دسته‌بندی‌ها'),
        types.KeyboardButton('ثبت سفارش'),
        types.KeyboardButton('مشاهده سفارش‌ها'),
        types.KeyboardButton('خروج از سیستم')
    )
    return markup

def products_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton('لیست محصولات'),
        types.KeyboardButton('اضافه کردن محصول'),
        types.KeyboardButton('ویرایش محصول'),
        types.KeyboardButton('حذف محصول'),
        types.KeyboardButton('بازگشت')
    )
    return markup

def categories_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton('لیست کتگوری‌ها'),
        types.KeyboardButton('اضافه کردن کتگوری'),
        types.KeyboardButton('ویرایش کتگوری'),
        types.KeyboardButton('حذف کتگوری'),
        types.KeyboardButton('بازگشت')
    )
    return markup

def order_status_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton('pending'),
        types.KeyboardButton('served'),
        types.KeyboardButton('cancelled'),
        types.KeyboardButton('بازگشت')
    )
    return markup

# ---------- لاگین ----------
@bot.message_handler(commands=['start', 'login'])
def cmd_start(message):
    chat_id = message.chat.id
    sess = ensure_session(chat_id)
    if sess.get("logged_in"):
        bot.send_message(chat_id, "شما از قبل وارد شده‌اید.", reply_markup=main_menu())
        return
    text = "به ربات صندوق کافه خوش آمدید!\nلطفاً وارد شوید."
    bot.send_message(chat_id, text, reply_markup=login_menu())

@bot.message_handler(func=lambda m: m.text == 'ورود به سیستم')
def ask_username(m):
    chat_id = m.chat.id
    msg = bot.send_message(chat_id, "نام کاربری را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_username)

def process_username(message):
    chat_id = message.chat.id
    username = message.text.strip()
    sess = ensure_session(chat_id)
    sess['temp']['username'] = username
    msg = bot.send_message(chat_id, "رمز عبور را وارد کنید:")
    bot.register_next_step_handler(msg, process_password)

def process_password(message):
    chat_id = message.chat.id
    password = message.text.strip()
    sess = ensure_session(chat_id)
    username = sess['temp'].get('username')
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        sess['logged_in'] = True
        sess['temp'] = {}
        bot.send_message(chat_id, "ورود با موفقیت انجام شد.", reply_markup=main_menu())
    else:
        sess['temp'] = {}
        bot.send_message(chat_id, "نام کاربری یا رمز عبور اشتباه است.", reply_markup=login_menu())

@bot.message_handler(func=lambda m: m.text == 'خروج از سیستم')
@login_required
def logout(m):
    chat_id = m.chat.id
    if chat_id in user_sessions:
        user_sessions[chat_id] = {"logged_in": False, "temp": {}}
    bot.send_message(chat_id, "از سیستم خارج شدید.", reply_markup=login_menu())

# ---------- محصولات ----------
@bot.message_handler(func=lambda m: m.text == 'محصولات')
@login_required
def products_root(m):
    bot.send_message(m.chat.id, "مدیریت محصولات:", reply_markup=products_menu())

@bot.message_handler(func=lambda m: m.text == 'لیست محصولات')
@login_required
def list_products(m):
    conn = get_db_connection()
    if conn is None:
        bot.send_message(m.chat.id, "خطا در اتصال به پایگاه داده.")
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.name, p.price, c.name
            FROM products p
            LEFT JOIN category c ON p.category_id = c.id
            ORDER BY p.id
        """)
        rows = cur.fetchall()
        if not rows:
            bot.send_message(m.chat.id, "هیچ محصولی ثبت نشده است.")
            return
        text = "لیست محصولات:\n\n"
        for r in rows:
            cat = r[3] if r[3] else "بدون دسته"
            text += f"کد: {r[0]} — {r[1]} — {r[2]:.2f} تومان — دسته: {cat}\n"
        bot.send_message(m.chat.id, text)
        cur.close()
    except Error as e:
        bot.send_message(m.chat.id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'اضافه کردن محصول')
@login_required
def add_product_start(m):
    msg = bot.send_message(m.chat.id, "نام محصول را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, add_product_name)

def add_product_name(message):
    chat_id = message.chat.id
    name = message.text.strip()
    if not name:
        bot.send_message(chat_id, "نام نامعتبر است.")
        return
    sess = ensure_session(chat_id)
    sess['temp']['new_product'] = {'name': name}
    bot.send_message(chat_id, "قیمت محصول را وارد کنید (به تومان):")
    bot.register_next_step_handler(bot.send_message(chat_id, "قیمت:"), add_product_price)  # workaround to show prompt and wait
    # Actually register next handler properly:
def add_product_price(message):
    chat_id = message.chat.id
    sess = ensure_session(chat_id)
    if 'new_product' not in sess['temp']:
        bot.send_message(chat_id, "خطا در روند اضافه کردن محصول.")
        return
    try:
        price = float(message.text.strip())
        if price < 0:
            raise ValueError()
    except:
        bot.send_message(chat_id, "قیمت نامعتبر است. مقدار را به صورت عدد وارد کنید.")
        return
    sess['temp']['new_product']['price'] = round(price, 2)
    # نمایش دسته‌ها برای انتخاب
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال به DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM category ORDER BY name")
        cats = cur.fetchall()
        text = "شناسه دسته را انتخاب کنید یا 0 برای عدم انتخاب/ایجاد دسته جدید وارد کنید:\n"
        for c in cats:
            text += f"{c[0]} — {c[1]}\n"
        bot.send_message(chat_id, text)
        msg = bot.send_message(chat_id, "شناسه دسته (یا 0):")
        bot.register_next_step_handler(msg, add_product_category)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

def add_product_category(message):
    chat_id = message.chat.id
    sess = ensure_session(chat_id)
    newp = sess['temp'].get('new_product')
    if not newp:
        bot.send_message(chat_id, "خطا در روند اضافه کردن محصول.")
        return
    cat_text = message.text.strip()
    try:
        cat_id = int(cat_text)
    except:
        bot.send_message(chat_id, "شناسه دسته باید عدد باشد.")
        return

    if cat_id == 0:
        # اجازهٔ وارد کردن نام دسته جدید یا خالی
        msg = bot.send_message(chat_id, "نام دسته جدید را وارد کنید (یا 'بدون' برای بدون دسته):")
        bot.register_next_step_handler(msg, add_product_insert, cat_id)
        return
    # در صورت انتخاب دستهٔ موجود، چک و وارد DB
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال به DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM category WHERE id = %s", (cat_id,))
        if cur.fetchone() is None:
            bot.send_message(chat_id, "دسته‌ای با این شناسه یافت نشد.")
            return
        cur.execute("""
            INSERT INTO products (name, price, category_id)
            VALUES (%s, %s, %s) RETURNING id
        """, (newp['name'], newp['price'], cat_id))
        prod_id = cur.fetchone()[0]
        conn.commit()
        bot.send_message(chat_id, f"محصول ثبت شد. کد محصول: {prod_id}", reply_markup=main_menu())
        sess['temp'].pop('new_product', None)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در ثبت محصول: {e}")
    finally:
        if conn: conn.close()

def add_product_insert(message, prev_cat_id):
    # prev_cat_id not used here except to indicate 0 case
    chat_id = message.chat.id
    sess = ensure_session(chat_id)
    newp = sess['temp'].get('new_product')
    if not newp:
        bot.send_message(chat_id, "خطا در روند اضافه کردن محصول.")
        return
    cat_name = message.text.strip()
    if cat_name.lower() == 'بدون':
        category_id = None
    else:
        # ایجاد یا بازیابی دسته
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "خطا در اتصال به DB.")
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM category WHERE name = %s", (cat_name,))
            row = cur.fetchone()
            if row:
                category_id = row[0]
            else:
                cur.execute("INSERT INTO category (name) VALUES (%s) RETURNING id", (cat_name,))
                category_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO products (name, price, category_id)
                VALUES (%s, %s, %s) RETURNING id
            """, (newp['name'], newp['price'], category_id))
            prod_id = cur.fetchone()[0]
            conn.commit()
            bot.send_message(chat_id, f"محصول با موفقیت ثبت شد. کد محصول: {prod_id}", reply_markup=main_menu())
            sess['temp'].pop('new_product', None)
            cur.close()
        except Error as e:
            bot.send_message(chat_id, f"خطا در ثبت: {e}")
        finally:
            if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'ویرایش محصول')
@login_required
def edit_product_start(m):
    msg = bot.send_message(m.chat.id, "کد محصولی که می‌خواهید ویرایش کنید را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, edit_product_select)

def edit_product_select(message):
    chat_id = message.chat.id
    pid_text = message.text.strip()
    if not pid_text.isdigit():
        bot.send_message(chat_id, "کد محصول باید عدد باشد.")
        return
    pid = int(pid_text)
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, price, category_id FROM products WHERE id = %s", (pid,))
        row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "محصول یافت نشد.")
            return
        sess = ensure_session(chat_id)
        sess['temp']['edit_product'] = {'id': row[0], 'name': row[1], 'price': float(row[2]), 'category_id': row[3]}
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add('ویرایش نام', 'ویرایش قیمت', 'ویرایش دسته', 'بازگشت')
        bot.send_message(chat_id, f"محصول انتخاب شد: {row[1]} — {row[2]:.2f}", reply_markup=markup)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text in ['ویرایش نام', 'ویرایش قیمت', 'ویرایش دسته'])
@login_required
def edit_product_field(m):
    chat_id = m.chat.id
    text = m.text
    sess = ensure_session(chat_id)
    if 'edit_product' not in sess['temp']:
        bot.send_message(chat_id, "هیچ محصولی برای ویرایش انتخاب نشده است.")
        return
    if text == 'ویرایش نام':
        msg = bot.send_message(chat_id, "نام جدید را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, perform_edit_name)
    elif text == 'ویرایش قیمت':
        msg = bot.send_message(chat_id, "قیمت جدید را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, perform_edit_price)
    elif text == 'ویرایش دسته':
        # نمایش دسته‌ها
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "خطا در اتصال DB.")
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name FROM category ORDER BY name")
            cats = cur.fetchall()
            textc = "شناسه دسته را وارد کنید یا 0 برای بدون دسته:\n"
            for c in cats:
                textc += f"{c[0]} — {c[1]}\n"
            bot.send_message(chat_id, textc)
            msg = bot.send_message(chat_id, "شناسه دسته:")
            bot.register_next_step_handler(msg, perform_edit_category)
            cur.close()
        except Error as e:
            bot.send_message(chat_id, f"خطا: {e}")
        finally:
            if conn: conn.close()

def perform_edit_name(message):
    chat_id = message.chat.id
    new_name = message.text.strip()
    sess = ensure_session(chat_id)
    pid = sess['temp']['edit_product']['id']
    if not new_name:
        bot.send_message(chat_id, "نام نامعتبر است.")
        return
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("UPDATE products SET name = %s WHERE id = %s", (new_name, pid))
        conn.commit()
        bot.send_message(chat_id, "نام محصول با موفقیت ویرایش شد.", reply_markup=main_menu())
        sess['temp'].pop('edit_product', None)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

def perform_edit_price(message):
    chat_id = message.chat.id
    try:
        price = float(message.text.strip())
        if price < 0:
            raise ValueError()
    except:
        bot.send_message(chat_id, "قیمت نامعتبر است.")
        return
    sess = ensure_session(chat_id)
    pid = sess['temp']['edit_product']['id']
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("UPDATE products SET price = %s WHERE id = %s", (round(price,2), pid))
        conn.commit()
        bot.send_message(chat_id, "قیمت محصول با موفقیت به‌روزرسانی شد.", reply_markup=main_menu())
        sess['temp'].pop('edit_product', None)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

def perform_edit_category(message):
    chat_id = message.chat.id
    cat_text = message.text.strip()
    try:
        cat_id = int(cat_text)
    except:
        bot.send_message(chat_id, "شناسه دسته باید عدد باشد.")
        return
    sess = ensure_session(chat_id)
    pid = sess['temp']['edit_product']['id']
    if cat_id == 0:
        new_cat = None
    else:
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "خطا در اتصال DB.")
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM category WHERE id = %s", (cat_id,))
            if cur.fetchone() is None:
                bot.send_message(chat_id, "دسته‌ای با این شناسه یافت نشد.")
                return
            cur.close()
            new_cat = cat_id
        except Error as e:
            bot.send_message(chat_id, f"خطا: {e}")
            return
        finally:
            if conn: conn.close()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE products SET category_id = %s WHERE id = %s", (new_cat, pid))
        conn.commit()
        bot.send_message(chat_id, "دسته محصول به‌روزرسانی شد.", reply_markup=main_menu())
        sess['temp'].pop('edit_product', None)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'حذف محصول')
@login_required
def delete_product_start(m):
    msg = bot.send_message(m.chat.id, "کد محصول برای حذف را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, delete_product_confirm)

def delete_product_confirm(message):
    chat_id = message.chat.id
    pid_text = message.text.strip()
    if not pid_text.isdigit():
        bot.send_message(chat_id, "کد محصول باید عدد باشد.")
        return
    pid = int(pid_text)
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM products WHERE id = %s", (pid,))
        row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "محصول یافت نشد.")
            return
        name = row[0]
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("حذف کن", callback_data=f"delprod:{pid}"))
        markup.add(types.InlineKeyboardButton("انصراف", callback_data="cancel"))
        bot.send_message(chat_id, f"آیا می‌خواهید محصول '{name}' حذف شود؟", reply_markup=markup)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("delprod:"))
def callback_delete_product(call):
    chat_id = call.message.chat.id
    pid = int(call.data.split(":",1)[1])
    conn = get_db_connection()
    if conn is None:
        bot.answer_callback_query(call.id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM products WHERE id = %s", (pid,))
        conn.commit()
        bot.edit_message_text("محصول حذف شد.", chat_id, call.message.message_id)
        cur.close()
    except Error as e:
        bot.answer_callback_query(call.id, f"خطا: {e}")
    finally:
        if conn: conn.close()

# ---------- دسته‌بندی‌ها ----------
@bot.message_handler(func=lambda m: m.text == 'دسته‌بندی‌ها')
@login_required
def categories_root(m):
    bot.send_message(m.chat.id, "مدیریت دسته‌بندی‌ها:", reply_markup=categories_menu())

@bot.message_handler(func=lambda m: m.text == 'لیست کتگوری‌ها')
@login_required
def list_categories(m):
    conn = get_db_connection()
    if conn is None:
        bot.send_message(m.chat.id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM category ORDER BY name")
        rows = cur.fetchall()
        if not rows:
            bot.send_message(m.chat.id, "هیچ دسته‌ای ثبت نشده است.")
            return
        text = "دسته‌ها:\n"
        for r in rows:
            text += f"{r[0]} — {r[1]}\n"
        bot.send_message(m.chat.id, text)
        cur.close()
    except Error as e:
        bot.send_message(m.chat.id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'اضافه کردن کتگوری')
@login_required
def add_category_start(m):
    msg = bot.send_message(m.chat.id, "نام دسته جدید را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, add_category_insert)

def add_category_insert(message):
    chat_id = message.chat.id
    name = message.text.strip()
    if not name:
        bot.send_message(chat_id, "نام نامعتبر است.")
        return
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO category (name) VALUES (%s) RETURNING id", (name,))
        cid = cur.fetchone()[0]
        conn.commit()
        bot.send_message(chat_id, f"دسته ثبت شد. کد: {cid}", reply_markup=categories_menu())
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در ثبت دسته: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'ویرایش کتگوری')
@login_required
def edit_category_start(m):
    msg = bot.send_message(m.chat.id, "کد دسته‌ای که می‌خواهید ویرایش کنید را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, edit_category_select)

def edit_category_select(message):
    chat_id = message.chat.id
    cid_text = message.text.strip()
    if not cid_text.isdigit():
        bot.send_message(chat_id, "کد دسته باید عدد باشد.")
        return
    cid = int(cid_text)
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM category WHERE id = %s", (cid,))
        row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "دسته یافت نشد.")
            return
        bot.send_message(chat_id, f"نام فعلی: {row[0]}\nنام جدید را وارد کنید:")
        bot.register_next_step_handler(bot.send_message(chat_id, "نام جدید:"), lambda msg, cid=cid: perform_edit_category_name(msg, cid))
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

def perform_edit_category_name(message, cid):
    chat_id = message.chat.id
    new_name = message.text.strip()
    if not new_name:
        bot.send_message(chat_id, "نام نامعتبر است.")
        return
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("UPDATE category SET name = %s WHERE id = %s", (new_name, cid))
        conn.commit()
        bot.send_message(chat_id, "دسته با موفقیت ویرایش شد.", reply_markup=categories_menu())
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'حذف کتگوری')
@login_required
def delete_category_start(m):
    msg = bot.send_message(m.chat.id, "کد دسته برای حذف را وارد کنید (توجه: محصولات مرتبط دسته‌شان NULL خواهد شد):", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, delete_category_confirm)

def delete_category_confirm(message):
    chat_id = message.chat.id
    cid_text = message.text.strip()
    if not cid_text.isdigit():
        bot.send_message(chat_id, "کد دسته باید عدد باشد.")
        return
    cid = int(cid_text)
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM category WHERE id = %s", (cid,))
        row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "دسته یافت نشد.")
            return
        name = row[0]
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("حذف", callback_data=f"delcat:{cid}"))
        markup.add(types.InlineKeyboardButton("انصراف", callback_data="cancel"))
        bot.send_message(chat_id, f"آیا می‌خواهید دسته '{name}' حذف شود؟", reply_markup=markup)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("delcat:"))
def callback_delete_category(call):
    cid = int(call.data.split(":",1)[1])
    conn = get_db_connection()
    if conn is None:
        bot.answer_callback_query(call.id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        # حذف دسته — محصولات مرتبط category_id = NULL خواهد شد بخاطر ON DELETE SET NULL (یا می‌توانیم دستی انجام دهیم)
        cur.execute("DELETE FROM category WHERE id = %s", (cid,))
        conn.commit()
        bot.edit_message_text("دسته حذف شد.", call.message.chat.id, call.message.message_id)
        cur.close()
    except Error as e:
        bot.answer_callback_query(call.id, f"خطا: {e}")
    finally:
        if conn: conn.close()

# ---------- سفارش‌گیری ----------
@bot.message_handler(func=lambda m: m.text == 'ثبت سفارش')
@login_required
def start_order(m):
    chat_id = m.chat.id
    # گزینه: انتخاب مشتری یا افزودن مشتری جدید
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('انتخاب مشتری', 'اضافه کردن مشتری', 'انصراف')
    bot.send_message(chat_id, "می‌خواهید با کدام مشتری سفارش ثبت شود؟", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == 'اضافه کردن مشتری')
@login_required
def add_customer_start(m):
    msg = bot.send_message(m.chat.id, "نام مشتری را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, add_customer_name)

def add_customer_name(message):
    chat_id = message.chat.id
    name = message.text.strip()
    if not name:
        bot.send_message(chat_id, "نام نامعتبر است.")
        return
    sess = ensure_session(chat_id)
    sess['temp']['new_customer'] = {'name': name}
    msg = bot.send_message(chat_id, "شماره تلفن را وارد کنید (اختیاری):")
    bot.register_next_step_handler(msg, add_customer_insert)

def add_customer_insert(message):
    chat_id = message.chat.id
    phone = message.text.strip() if message.text else None
    sess = ensure_session(chat_id)
    cust = sess['temp'].pop('new_customer', None)
    if not cust:
        bot.send_message(chat_id, "خطا در افزودن مشتری.")
        return
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO customers (name, phone) VALUES (%s, %s) RETURNING id", (cust['name'], phone))
        cid = cur.fetchone()[0]
        conn.commit()
        bot.send_message(chat_id, f"مشتری ثبت شد. کد مشتری: {cid}\nحال می‌توانید سفارش را ادامه دهید.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add('انتخاب مشتری'))
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'انتخاب مشتری')
@login_required
def select_customer_start(m):
    chat_id = m.chat.id
    msg = bot.send_message(chat_id, "لطفاً کد مشتری را وارد کنید (یا 'list' برای نمایش مشتریان):", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, select_customer_process)

def select_customer_process(message):
    chat_id = message.chat.id
    text = message.text.strip()
    if text.lower() == 'list':
        # نمایش مشتریان
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "خطا در اتصال DB.")
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name, phone FROM customers ORDER BY name")
            rows = cur.fetchall()
            if not rows:
                bot.send_message(chat_id, "هیچ مشتری ثبت نشده است.")
                return
            txt = "مشتریان:\n"
            for r in rows:
                txt += f"{r[0]} — {r[1]} — {r[2] or '-'}\n"
            bot.send_message(chat_id, txt)
            # دوباره درخواست کد
            msg = bot.send_message(chat_id, "کد مشتری را وارد کنید:")
            bot.register_next_step_handler(msg, select_customer_process)
            cur.close()
        except Error as e:
            bot.send_message(chat_id, f"خطا: {e}")
        finally:
            if conn: conn.close()
        return

    if not text.isdigit():
        bot.send_message(chat_id, "کد مشتری باید عدد یا 'list' باشد.")
        return
    cid = int(text)
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM customers WHERE id = %s", (cid,))
        row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "مشتری یافت نشد.")
            return
        sess = ensure_session(chat_id)
        sess['temp']['current_order'] = {'customer_id': cid, 'items': []}
        bot.send_message(chat_id, f"مشتری انتخاب شد: {row[1]}\nحالا محصولات را اضافه کنید.\nبرای دیدن لیست محصولات 'list' وارد کنید.\nبرای پایان و ثبت سفارش 'done' وارد کنید.", reply_markup=types.ReplyKeyboardRemove())
        msg = bot.send_message(chat_id, "کد محصول یا 'list' یا 'done':")
        bot.register_next_step_handler(msg, add_order_item)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

def add_order_item(message):
    chat_id = message.chat.id
    text = message.text.strip()
    sess = ensure_session(chat_id)
    if 'current_order' not in sess['temp']:
        bot.send_message(chat_id, "هیچ سفارشی در جریان نیست. ابتدا مشتری را انتخاب کنید.")
        return
    order = sess['temp']['current_order']
    if text.lower() == 'list':
        # نمایش محصولات
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "خطا در اتصال DB.")
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name, price FROM products ORDER BY id")
            rows = cur.fetchall()
            if not rows:
                bot.send_message(chat_id, "هیچ محصولی ثبت نشده است.")
            else:
                txt = "محصولات:\n"
                for r in rows:
                    txt += f"{r[0]} — {r[1]} — {r[2]:.2f}\n"
                bot.send_message(chat_id, txt)
            cur.close()
        except Error as e:
            bot.send_message(chat_id, f"خطا: {e}")
        finally:
            if conn: conn.close()
        msg = bot.send_message(chat_id, "کد محصول یا 'done':")
        bot.register_next_step_handler(msg, add_order_item)
        return
    if text.lower() == 'done':
        # ثبت سفارش نهایی
        if not order['items']:
            bot.send_message(chat_id, "هیچ آیتمی اضافه نشده است. سفارش لغو شد.")
            sess['temp'].pop('current_order', None)
            return
        save_order(chat_id, order)
        sess['temp'].pop('current_order', None)
        return
    # در غیر این صورت انتظار داریم یک کد محصول عددی
    if not text.isdigit():
        bot.send_message(chat_id, "کد محصول باید عدد، 'list' یا 'done' باشد.")
        return
    pid = int(text)
    # درخواست تعداد
    sess['temp']['pending_product'] = pid
    msg = bot.send_message(chat_id, "تعداد را وارد کنید:")
    bot.register_next_step_handler(msg, add_order_item_quantity)

def add_order_item_quantity(message):
    chat_id = message.chat.id
    qty_text = message.text.strip()
    sess = ensure_session(chat_id)
    if 'pending_product' not in sess['temp'] or 'current_order' not in sess['temp']:
        bot.send_message(chat_id, "خطا در روند افزودن آیتم.")
        return
    if not qty_text.isdigit():
        bot.send_message(chat_id, "تعداد باید عدد صحیح مثبت باشد.")
        return
    qty = int(qty_text)
    if qty < 1:
        bot.send_message(chat_id, "تعداد باید بزرگتر از صفر باشد.")
        return
    pid = sess['temp'].pop('pending_product')
    # گرفتن قیمت فعلی محصول
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT name, price FROM products WHERE id = %s", (pid,))
        row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "محصول یافت نشد.")
            return
        pname, price = row[0], float(row[1])
        # اضافه کردن به سفارش موقتی
        order = sess['temp']['current_order']
        order['items'].append({'product_id': pid, 'name': pname, 'quantity': qty, 'price': price})
        bot.send_message(chat_id, f"آیتم اضافه شد: {pname} x {qty} — واحد: {price:.2f}")
        # ادامهٔ اضافه کردن
        msg = bot.send_message(chat_id, "کد محصول بعدی یا 'list' یا 'done':")
        bot.register_next_step_handler(msg, add_order_item)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

def save_order(chat_id, order):
    # محاسبهٔ مجموع
    total = sum(item['quantity'] * item['price'] for item in order['items'])
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO orders (customer_id, total, status) VALUES (%s, %s, %s) RETURNING id, order_date", (order['customer_id'], round(total,2), 'pending'))
        row = cur.fetchone()
        order_id = row[0]
        order_date = row[1]
        # درج آیتم‌ها
        for it in order['items']:
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, price_at_order)
                VALUES (%s, %s, %s, %s)
            """, (order_id, it['product_id'], it['quantity'], round(it['price'],2)))
        conn.commit()
        bot.send_message(chat_id, f"سفارش ثبت شد.\nکد سفارش: {order_id}\nتاریخ: {order_date.strftime('%Y-%m-%d %H:%M')}\nمجموع: {total:.2f} تومان", reply_markup=main_menu())
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در ثبت سفارش: {e}")
    finally:
        if conn: conn.close()

# ---------- مشاهده سفارش‌ها ----------
@bot.message_handler(func=lambda m: m.text == 'مشاهده سفارش‌ها')
@login_required
def view_orders_menu(m):
    chat_id = m.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('لیست سفارش‌ها', 'جستجوی سفارش', 'بازگشت')
    bot.send_message(chat_id, "مدیریت سفارش‌ها:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == 'لیست سفارش‌ها')
@login_required
def list_orders(m):
    conn = get_db_connection()
    if conn is None:
        bot.send_message(m.chat.id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT o.id, c.name, o.order_date, o.total, o.status
            FROM orders o
            LEFT JOIN customers c ON o.customer_id = c.id
            ORDER BY o.order_date DESC
            LIMIT 50
        """)
        rows = cur.fetchall()
        if not rows:
            bot.send_message(m.chat.id, "هیچ سفارشی ثبت نشده است.")
            return
        text = "سفارش‌ها:\n\n"
        for r in rows:
            cust = r[1] or "مشتری ناشناس"
            text += f"سفارش #{r[0]} — {cust} — {r[2].strftime('%Y-%m-%d %H:%M')} — مجموع: {r[3]:.2f} — وضعیت: {r[4]}\n"
        bot.send_message(m.chat.id, text)
        cur.close()
    except Error as e:
        bot.send_message(m.chat.id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'جستجوی سفارش')
@login_required
def search_order_start(m):
    msg = bot.send_message(m.chat.id, "کد سفارش را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, search_order_by_id)

def search_order_by_id(message):
    chat_id = message.chat.id
    text = message.text.strip()
    if not text.isdigit():
        bot.send_message(chat_id, "کد سفارش باید عدد باشد.")
        return
    oid = int(text)
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT o.id, c.name, o.order_date, o.total, o.status
            FROM orders o
            LEFT JOIN customers c ON o.customer_id = c.id
            WHERE o.id = %s
        """, (oid,))
        row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "سفارشی با این کد یافت نشد.")
            return
        text = f"سفارش #{row[0]} — {row[1] or 'مشتری ناشناس'} — {row[2].strftime('%Y-%m-%d %H:%M')} — مجموع: {row[3]:.2f} — وضعیت: {row[4]}\n\nآیتم‌ها:\n"
        cur.execute("""
            SELECT oi.quantity, oi.price_at_order, p.name
            FROM order_items oi
            LEFT JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (oid,))
        items = cur.fetchall()
        for it in items:
            text += f"{it[2] or 'محصول حذف شده'} — {it[0]} x {it[1]:.2f}\n"
        # امکان تغییر وضعیت
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('تغییر وضعیت', 'بازگشت')
        bot.send_message(chat_id, text, reply_markup=markup)
        # ذخیرهٔ id برای ویرایش احتمالی
        sess = ensure_session(chat_id)
        sess['temp']['last_viewed_order'] = oid
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا: {e}")
    finally:
        if conn: conn.close()

@bot.message_handler(func=lambda m: m.text == 'تغییر وضعیت')
@login_required
def change_order_status_prompt(m):
    chat_id = m.chat.id
    sess = ensure_session(chat_id)
    oid = sess['temp'].get('last_viewed_order')
    if not oid:
        bot.send_message(chat_id, "ابتدا یک سفارش را جستجو یا مشاهده کنید.")
        return
    bot.send_message(chat_id, "وضعیت جدید را انتخاب کنید:", reply_markup=order_status_menu())

@bot.message_handler(func=lambda m: m.text in ['pending', 'served', 'cancelled'])
@login_required
def change_order_status(m):
    chat_id = m.chat.id
    new_status = m.text
    sess = ensure_session(chat_id)
    oid = sess['temp'].get('last_viewed_order')
    if not oid:
        bot.send_message(chat_id, "ابتدا یک سفارش را انتخاب کنید.")
        return
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال DB.")
        return
    try:
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, oid))
        conn.commit()
        bot.send_message(chat_id, f"وضعیت سفارش #{oid} به '{new_status}' تغییر کرد.", reply_markup=main_menu())
        sess['temp'].pop('last_viewed_order', None)
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در تغییر وضعیت: {e}")
    finally:
        if conn: conn.close()

# ---------- سایر هندلرها ----------
@bot.message_handler(func=lambda m: m.text == 'بازگشت')
@login_required
def go_back(m):
    bot.send_message(m.chat.id, "بازگشت به منوی اصلی.", reply_markup=main_menu())

@bot.message_handler(func=lambda message: True)
def fallback(message):
    # پاسخ پیش‌فرض برای ورودی‌های شناخته نشده
    if check_login(message.chat.id):
        bot.send_message(message.chat.id, "لطفاً یکی از گزینه‌ها را از منو انتخاب کنید.", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "برای شروع /start را بزنید.", reply_markup=login_menu())

if __name__ == '__main__':
    create_tables()
    print("Bot is running ...")
    bot.polling(none_stop=True)
