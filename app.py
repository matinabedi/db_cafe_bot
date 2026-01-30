import telebot
from telebot import types
import psycopg2
from psycopg2 import Error
from datetime import datetime, timedelta
import os
from functools import wraps



BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_URI = os.environ.get("DB_URI")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")  
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")  

bot = telebot.TeleBot(BOT_TOKEN)

# دیکشنری برای ذخیره وضعیت لاگین کاربران
user_sessions = {}

def check_login(chat_id):
    """بررسی آیا کاربر لاگین کرده است"""
    return user_sessions.get(chat_id, False)

def login_required(func):
    """دکوراتور برای بررسی لاگین"""
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if not check_login(message.chat.id):
            bot.send_message(message.chat.id, "لطفاً ابتدا وارد سیستم شوید.")
            ask_for_username(message)
            return
        return func(message, *args, **kwargs)
    return wrapper

def get_db_connection():
    try:
        connection = psycopg2.connect(DB_URI)
        return connection
    except Error as e:
        print(f"خطا در اتصال به پایگاه داده: {e}")
        return None

def create_tables():
    conn = get_db_connection()
    if conn is None:
        return
    try:
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR NOT NULL,
                phone VARCHAR,
                email VARCHAR,
                address TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id SERIAL PRIMARY KEY,
                title VARCHAR NOT NULL,
                author VARCHAR NOT NULL,
                isbn VARCHAR UNIQUE,
                publication_year INTEGER,
                total_copies INTEGER DEFAULT 1,
                available_copies INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS borrowings (
                id SERIAL PRIMARY KEY,
                book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
                member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
                borrow_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                due_date TIMESTAMP NOT NULL,
                return_date TIMESTAMP,
                is_returned BOOLEAN DEFAULT FALSE
            );
        """)
        
        conn.commit()
        print("جداول با موفقیت ایجاد یا بررسی شدند.")
        cur.close()
    except Error as e:
        print(f"خطا در ایجاد جداول: {e}")
    finally:
        if conn:
            conn.close()

def login_menu():
    """منوی لاگین"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    btn = types.KeyboardButton('ورود به سیستم')
    markup.add(btn)
    return markup

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('نمایش کتاب‌ها')
    btn2 = types.KeyboardButton('نمایش اعضا')
    btn3 = types.KeyboardButton('اضافه کردن کتاب')
    btn4 = types.KeyboardButton('اضافه کردن عضو')
    btn5 = types.KeyboardButton('امانت دادن کتاب')
    btn6 = types.KeyboardButton('پس گرفتن کتاب')
    btn7 = types.KeyboardButton('جستجوی کتاب')
    btn8 = types.KeyboardButton('وضعیت کتاب‌های امانت‌رفته')
    btn9 = types.KeyboardButton('خروج از سیستم')
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9)
    return markup

def search_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('جستجو با عنوان')
    btn2 = types.KeyboardButton('جستجو با نویسنده')
    btn3 = types.KeyboardButton('بازگشت به منوی اصلی')
    markup.add(btn1, btn2, btn3)
    return markup

@bot.message_handler(commands=['start', 'login'])
def start_command(message):
    """شروع ربات و درخواست لاگین"""
    chat_id = message.chat.id
    
    # اگر کاربر قبلاً لاگین کرده، به منوی اصلی برو
    if check_login(chat_id):
        send_welcome(message)
        return
    
    welcome_text = """
به سیستم مدیریت کتابخانه خوش آمدید!
لطفاً برای ادامه وارد سیستم شوید.
برای ورود دکمه زیر را فشار دهید:
"""
    bot.send_message(chat_id, welcome_text, reply_markup=login_menu())

@bot.message_handler(func=lambda message: message.text == 'ورود به سیستم')
def ask_for_username(message):
    """درخواست نام کاربری"""
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "نام کاربری را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_username)

def process_username(message):
    """پردازش نام کاربری و درخواست رمز عبور"""
    chat_id = message.chat.id
    username = message.text.strip()
    
    # ذخیره نام کاربری موقت در session
    if 'temp_data' not in user_sessions:
        user_sessions['temp_data'] = {}
    user_sessions['temp_data'][chat_id] = {'username': username}
    
    msg = bot.send_message(chat_id, "رمز عبور را وارد کنید:")
    bot.register_next_step_handler(msg, process_password, username)

def process_password(message, username):
    """بررسی نام کاربری و رمز عبور"""
    chat_id = message.chat.id
    password = message.text.strip()
    
    # بررسی اعتبار نام کاربری و رمز عبور
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        user_sessions[chat_id] = True
        bot.send_message(chat_id, " ورود موفقیت‌آمیز بود!")
        send_welcome(message)
    else:
        bot.send_message(chat_id, " نام کاربری یا رمز عبور اشتباه است.")
        ask_for_username(message)

@bot.message_handler(func=lambda message: message.text == 'خروج از سیستم')
@login_required
def logout_command(message):
    """خروج از سیستم"""
    chat_id = message.chat.id
    if chat_id in user_sessions:
        del user_sessions[chat_id]
    
    # پاک کردن داده‌های موقت
    if 'temp_data' in user_sessions and chat_id in user_sessions['temp_data']:
        del user_sessions['temp_data'][chat_id]
    
    bot.send_message(chat_id, " با موفقیت از سیستم خارج شدید.", reply_markup=login_menu())

@bot.message_handler(commands=['menu', 'help'])
@login_required
def send_welcome(message):
    chat_id = message.chat.id
    welcome_text = """
 سیستم مدیریت کتابخانه
لطفاً یکی از گزینه‌های زیر را انتخاب کنید:
"""
    bot.send_message(chat_id, welcome_text, reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == 'نمایش کتاب‌ها')
@login_required
def show_books(message):
    conn = get_db_connection()
    if conn is None:
        bot.send_message(message.chat.id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, title, author, available_copies, total_copies 
            FROM books 
            ORDER BY title
        """)
        books = cur.fetchall()
        
        if not books:
            bot.send_message(message.chat.id, "هیچ کتابی در کتابخانه ثبت نشده است.")
            return
        
        response = "لیست کتاب‌ها:\n\n"
        for book in books:
            status = "موجود" if book[3] > 0 else "امانت"
            response += f"{book[1]}\n"
            response += f"نویسنده: {book[2]}\n"
            response += f"موجودی: {book[3]}/{book[4]} - {status}\n"
            response += f"کد کتاب: {book[0]}\n"
            response += "-" * 30 + "\n"
        
        bot.send_message(message.chat.id, response, parse_mode='Markdown')
        cur.close()
    except Error as e:
        bot.send_message(message.chat.id, f"خطا در دریافت اطلاعات: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'نمایش اعضا')
@login_required
def show_members(message):
    conn = get_db_connection()
    if conn is None:
        bot.send_message(message.chat.id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, full_name, phone, email, join_date 
            FROM members 
            WHERE is_active = TRUE 
            ORDER BY full_name
        """)
        members = cur.fetchall()
        
        if not members:
            bot.send_message(message.chat.id, "هیچ عضوی ثبت نشده است.")
            return
        
        response = "لیست اعضای کتابخانه:\n\n"
        for member in members:
            join_date = member[4].strftime('%Y-%m-%d')
            response += f"{member[1]}\n"
            response += f"تلفن: {member[2] or 'ثبت نشده'}\n"
            response += f"ایمیل: {member[3] or 'ثبت نشده'}\n"
            response += f"تاریخ عضویت: {join_date}\n"
            response += f"کد عضو: {member[0]}\n"
            response += "-" * 30 + "\n"
        
        bot.send_message(message.chat.id, response, parse_mode='Markdown')
        cur.close()
    except Error as e:
        bot.send_message(message.chat.id, f"خطا در دریافت اطلاعات: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'اضافه کردن عضو')
@login_required
def add_member_command(message):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "لطفاً نام کامل عضو جدید را وارد کنید:")
    bot.register_next_step_handler(msg, process_member_name)

def process_member_name(message):
    chat_id = message.chat.id
    full_name = message.text.strip()
    
    if not full_name or len(full_name) < 2:
        bot.send_message(chat_id, "نام وارد شده معتبر نیست. لطفاً دوباره تلاش کنید.")
        return
    
    msg = bot.send_message(chat_id, "لطفاً شماره تلفن عضو را وارد کنید (اختیاری):")
    bot.register_next_step_handler(msg, process_member_phone, full_name)

def process_member_phone(message, full_name):
    chat_id = message.chat.id
    phone = message.text.strip() if message.text else None
    
    msg = bot.send_message(chat_id, "لطفاً ایمیل عضو را وارد کنید:")
    bot.register_next_step_handler(msg, process_member_email, full_name, phone)

def process_member_email(message, full_name, phone):
    chat_id = message.chat.id
    email = message.text.strip() if message.text else None
    
    msg = bot.send_message(chat_id, "لطفاً آدرس عضو را وارد کنید:")
    bot.register_next_step_handler(msg, process_member_address, full_name, phone, email)

def process_member_address(message, full_name, phone, email):
    chat_id = message.chat.id
    address = message.text.strip() if message.text else None
    
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO members (full_name, phone, email, address)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (full_name, phone, email, address))
        
        member_id = cur.fetchone()[0]
        conn.commit()
        
        bot.send_message(chat_id, f"عضو جدید با موفقیت ثبت شد!\nکد عضویت: {member_id}")
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در ثبت عضو: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'اضافه کردن کتاب')
@login_required
def add_book_command(message):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "لطفاً عنوان کتاب را وارد کنید:")
    bot.register_next_step_handler(msg, process_book_title)

def process_book_title(message):
    chat_id = message.chat.id
    title = message.text.strip()
    
    if not title or len(title) < 2:
        bot.send_message(chat_id, "عنوان وارد شده معتبر نیست.")
        return
    
    msg = bot.send_message(chat_id, "لطفاً نام نویسنده را وارد کنید:")
    bot.register_next_step_handler(msg, process_book_author, title)

def process_book_author(message, title):
    chat_id = message.chat.id
    author = message.text.strip()
    
    if not author or len(author) < 2:
        bot.send_message(chat_id, "نام نویسنده معتبر نیست.")
        return
    
    msg = bot.send_message(chat_id, "لطفاً تعداد نسخه‌های کتاب را وارد کنید (پیش‌فرض: 1):")
    bot.register_next_step_handler(msg, process_book_copies, title, author)

def process_book_copies(message, title, author):
    chat_id = message.chat.id
    copies_text = message.text.strip()
    
    try:
        copies = int(copies_text) if copies_text else 1
        if copies < 1:
            copies = 1
    except:
        copies = 1
    
    msg = bot.send_message(chat_id, "لطفاً سال انتشار کتاب را وارد کنید (اختیاری):")
    bot.register_next_step_handler(msg, process_book_year, title, author, copies)

def process_book_year(message, title, author, copies):
    chat_id = message.chat.id
    year_text = message.text.strip()
    year = int(year_text) if year_text and year_text.isdigit() else None
    
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO books (title, author, total_copies, available_copies, publication_year)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (title, author, copies, copies, year))
        
        book_id = cur.fetchone()[0]
        conn.commit()
        
        bot.send_message(chat_id, f"کتاب جدید با موفقیت ثبت شد!\nکد کتاب: {book_id}")
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در ثبت کتاب: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'امانت دادن کتاب')
@login_required
def borrow_book_command(message):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "لطفاً کد کتاب را وارد کنید:")
    bot.register_next_step_handler(msg, process_borrow_book_id)

def process_borrow_book_id(message):
    chat_id = message.chat.id
    book_id = message.text.strip()
    
    if not book_id.isdigit():
        bot.send_message(chat_id, "کد کتاب باید عدد باشد.")
        return
    
    msg = bot.send_message(chat_id, "لطفاً کد عضو را وارد کنید:")
    bot.register_next_step_handler(msg, process_borrow_member_id, int(book_id))

def process_borrow_member_id(message, book_id):
    chat_id = message.chat.id
    member_id = message.text.strip()
    
    if not member_id.isdigit():
        bot.send_message(chat_id, "کد عضو باید عدد باشد.")
        return
    
    msg = bot.send_message(chat_id, "برای چند روز امانت داده شود؟ (پیش‌فرض: 14 روز)")
    bot.register_next_step_handler(msg, process_borrow_days, book_id, int(member_id))

def process_borrow_days(message, book_id, member_id):
    chat_id = message.chat.id
    days_text = message.text.strip()
    
    try:
        days = int(days_text) if days_text else 14
        if days < 1:
            days = 14
    except:
        days = 14
    
    due_date = datetime.now() + timedelta(days=days)
    
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        
        cur.execute("SELECT available_copies, title FROM books WHERE id = %s", (book_id,))
        book_info = cur.fetchone()
        
        if not book_info:
            bot.send_message(chat_id, "کتابی با این کد یافت نشد.")
            return
        
        if book_info[0] < 1:
            bot.send_message(chat_id, f"کتاب '{book_info[1]}' در حال حاضر موجود نیست.")
            return
        
        cur.execute("SELECT full_name FROM members WHERE id = %s AND is_active = TRUE", (member_id,))
        member_info = cur.fetchone()
        
        if not member_info:
            bot.send_message(chat_id, "عضوی با این کد یافت نشد یا غیرفعال است.")
            return
        
        cur.execute("""
            INSERT INTO borrowings (book_id, member_id, due_date)
            VALUES (%s, %s, %s)
        """, (book_id, member_id, due_date))
        
        cur.execute("""
            UPDATE books 
            SET available_copies = available_copies - 1 
            WHERE id = %s
        """, (book_id,))
        
        conn.commit()
        
        due_date_str = due_date.strftime('%Y-%m-%d')
        bot.send_message(chat_id, f"کتاب '{book_info[1]}' به '{member_info[0]}' امانت داده شد.\nموعد بازگشت: {due_date_str}")
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در ثبت امانت: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'پس گرفتن کتاب')
@login_required
def return_book_command(message):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "لطفاً کد کتاب را وارد کنید:")
    bot.register_next_step_handler(msg, process_return_book)

def process_return_book(message):
    chat_id = message.chat.id
    book_id = message.text.strip()
    
    if not book_id.isdigit():
        bot.send_message(chat_id, "کد کتاب باید عدد باشد.")
        return
    
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT b.id, bk.title, m.full_name 
            FROM borrowings b
            JOIN books bk ON b.book_id = bk.id
            JOIN members m ON b.member_id = m.id
            WHERE b.book_id = %s AND b.is_returned = FALSE
            ORDER BY b.borrow_date DESC LIMIT 1
        """, (int(book_id),))
        
        borrowing = cur.fetchone()
        
        if not borrowing:
            bot.send_message(chat_id, "هیچ امانت فعالی برای این کتاب یافت نشد.")
            return
        
        cur.execute("""
            UPDATE borrowings 
            SET is_returned = TRUE, return_date = CURRENT_TIMESTAMP 
            WHERE id = %s
        """, (borrowing[0],))
        
        cur.execute("""
            UPDATE books 
            SET available_copies = available_copies + 1 
            WHERE id = %s
        """, (int(book_id),))
        
        conn.commit()
        
        bot.send_message(chat_id, f"کتاب '{borrowing[1]}' از '{borrowing[2]}' پس گرفته شد.")
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در پس گرفتن کتاب: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'جستجوی کتاب')
@login_required
def search_book_menu(message):
    bot.send_message(message.chat.id, "لطفاً نوع جستجو را انتخاب کنید:", 
                     reply_markup=search_menu())

@bot.message_handler(func=lambda message: message.text == 'جستجو با عنوان')
@login_required
def search_by_title_command(message):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "لطفاً بخشی از عنوان کتاب را وارد کنید:")
    bot.register_next_step_handler(msg, search_by_title)

def search_by_title(message):
    chat_id = message.chat.id
    keyword = f"%{message.text.strip()}%"
    
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, title, author, available_copies 
            FROM books 
            WHERE title ILIKE %s 
            ORDER BY title
        """, (keyword,))
        
        books = cur.fetchall()
        
        if not books:
            bot.send_message(chat_id, "کتابی با این عنوان یافت نشد.")
            return
        
        response = f"نتایج جستجو برای '{message.text.strip()}':\n\n"
        for book in books:
            status = "موجود" if book[3] > 0 else "امانت"
            response += f"{book[1]}\n"
            response += f"نویسنده: {book[2]}\n"
            response += f"وضعیت: {status}\n"
            response += f"کد کتاب: {book[0]}\n"
            response += "-" * 30 + "\n"
        
        bot.send_message(chat_id, response, parse_mode='Markdown')
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در جستجو: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'جستجو با نویسنده')
@login_required
def search_by_author_command(message):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "لطفاً نام نویسنده را وارد کنید:")
    bot.register_next_step_handler(msg, search_by_author)

def search_by_author(message):
    chat_id = message.chat.id
    keyword = f"%{message.text.strip()}%"
    
    conn = get_db_connection()
    if conn is None:
        bot.send_message(chat_id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, title, author, available_copies 
            FROM books 
            WHERE author ILIKE %s 
            ORDER BY title
        """, (keyword,))
        
        books = cur.fetchall()
        
        if not books:
            bot.send_message(chat_id, "کتابی از این نویسنده یافت نشد.")
            return
        
        response = f"نتایج جستجو برای نویسنده '{message.text.strip()}':\n\n"
        for book in books:
            status = "موجود" if book[3] > 0 else "امانت"
            response += f"{book[1]}\n"
            response += f"نویسنده: {book[2]}\n"
            response += f"وضعیت: {status}\n"
            response += f"کد کتاب: {book[0]}\n"
            response += "-" * 30 + "\n"
        
        bot.send_message(chat_id, response, parse_mode='Markdown')
        cur.close()
    except Error as e:
        bot.send_message(chat_id, f"خطا در جستجو: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'وضعیت کتاب‌های امانت‌رفته')
@login_required
def show_borrowed_books(message):
    conn = get_db_connection()
    if conn is None:
        bot.send_message(message.chat.id, "خطا در اتصال به پایگاه داده.")
        return
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                b.title,
                bk.author,
                m.full_name,
                br.borrow_date,
                br.due_date,
                CASE 
                    WHEN br.due_date < CURRENT_DATE THEN 'معوقه'
                    ELSE 'در امانت'
                END as status
            FROM borrowings br
            JOIN books b ON br.book_id = b.id
            JOIN members m ON br.member_id = m.id
            JOIN books bk ON br.book_id = bk.id
            WHERE br.is_returned = FALSE
            ORDER BY br.due_date
        """)
        
        borrowed = cur.fetchall()
        
        if not borrowed:
            bot.send_message(message.chat.id, "هیچ کتابی در حال حاضر امانت نیست.")
            return
        
        response = "کتاب‌های در حال امانت:\n\n"
        for item in borrowed:
            borrow_date = item[3].strftime('%Y-%m-%d')
            due_date = item[4].strftime('%Y-%m-%d')
            response += f"{item[0]}\n"
            response += f"نویسنده: {item[1]}\n"
            response += f"امانت گیرنده: {item[2]}\n"
            response += f"تاریخ امانت: {borrow_date}\n"
            response += f"موعد بازگشت: {due_date}\n"
            response += f"وضعیت: {item[5]}\n"
            response += "-" * 30 + "\n"
        
        bot.send_message(message.chat.id, response, parse_mode='Markdown')
        cur.close()
    except Error as e:
        bot.send_message(message.chat.id, f"خطا در دریافت اطلاعات: {e}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(func=lambda message: message.text == 'بازگشت به منوی اصلی')
@login_required
def back_to_main_menu(message):
    send_welcome(message)

if __name__ == '__main__':
    create_tables()
    print("Running .....")

    bot.polling(none_stop=True)
