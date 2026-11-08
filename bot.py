import os
import sqlite3
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)
from dotenv import load_dotenv

# Environment Variables መጫን
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_PHONE = "+251941506799"

# ሎጊንግ ማዋቀር
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# የንግግር ደረጃዎች (Conversation States)
SELECTING_NUMBERS, FULL_NAME, PHONE_NUMBER, PAYMENT_SCREENSHOT, ADMIN_ACTION = range(5)

# ----------------- ዳታቤዝ ማዋቀር -----------------
def init_db():
    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        phone_number TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS numbers (
        number INTEGER PRIMARY KEY,
        status TEXT DEFAULT 'AVAILABLE',
        user_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        numbers_list TEXT,
        screenshot_id TEXT,
        status TEXT DEFAULT 'PENDING'
    )
    """)
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM numbers")
    if cursor.fetchone()[0] == 0:
        for i in range(1, 201):
            cursor.execute("INSERT OR IGNORE INTO numbers (number, status) VALUES (?, 'AVAILABLE')", (i,))
        conn.commit()
    conn.close()

init_db()

# ዋና ሜኑ
def get_main_keyboard(is_admin=False):
    keyboard = [
        ["🔢 ቁጥር መያዝ", "📋 ነፃ ቁጥሮች ማየት"],
        ["ℹ️ መረጃ", "📞 እገዛ"]
    ]
    if is_admin:
        keyboard.append(["⚙️ አድሚን መቆጣጠሪያ"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# /start ትዕዛዝ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = (user.id == ADMIN_ID)
    
    welcome_text = (
        "⭐ **ኤዱ ከአረካ online መዝናኛ** ⭐\n"
        "🔥 **ፈጣን ዕለታው ዕቁብ** 🔥\n"
        "📌 **በ100 ብር 12,000 ብር ደራሽ** (25ተኛ ዙር)\n\n"
        f"ሰላም {user.first_name}!\n\n"
        "በዚህ Bot የሚከተሉትን ማድረግ ይችላሉ:-\n"
        "✅ በርካታ ቁጥሮችን በአንድ ላይ መያዝ\n"
        "✅ ነፃ ቁጥሮች ማየት\n"
        "✅ የአገልግሎት መረጃ ማየት"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(is_admin), parse_mode="Markdown")
    return ConversationHandler.END

# 📋 ነፃ ቁጥሮችን ማየት
async def show_free_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    cursor.execute("SELECT number FROM numbers WHERE status = 'AVAILABLE' ORDER BY number ASC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("ይቅርታ, አሁን ሁሉም ቁጥሮች ተይዘዋል!")
        return

    free_nums = [str(row[0]) for row in rows]
    nums_text = ", ".join(free_nums)
    response_msg = f"📋 **ቀሪ ነፃ ቁጥሮች (ጠቅላላ {len(free_nums)} ቁጥሮች አሉ):**\n\n{nums_text}"
    
    if len(response_msg) > 4000:
        response_msg = response_msg[:4000] + "\n\n... (ሌሎች ቁጥሮችም አሉ)"

    await update.message.reply_text(response_msg, parse_mode="Markdown")

# ⚙️ አድሚን መቆጣጠሪያ ሜኑ
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        ["📊 የተያዙ ቁጥሮች ማየት"],
        ["🗑 ቁጥር መሰረዝ (Release)", "➕ አዲስ ቁጥሮችን መጨመር"],
        ["⬅️ ወደ ዋና ሜኑ መመለስ"]
    ]
    await update.message.reply_text("⚙️ **የአድሚን መቆጣጠሪያ ፓነል:**", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown")

# 🔢 ቁጥር መያዝ ማስጀመር (ብዙ ቁጥሮች)
async def choose_number_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔢 **ቁጥር ለመያዝ፦**\n\n"
        "እባክዎ የሚፈልጉትን ቁጥሮች በኮማ (comma) ለይተው ይጻፉልን (ለምሳሌ፦ `41,67,81,8,91,117` ብለው ይላኩ)።\n"
        "*(እያንዳንዱ ቁጥር 100 ብር ይመደብለታል)*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    return SELECTING_NUMBERS

# የቁጥሮች ግቤት መቀበል እና ማረጋገጥ
async def receive_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # ኮማዎችን እና ስፔሶችን አስተካክሎ ቁጥሮችን መለየት
    raw_nums = text.replace(" ", "").split(",")
    
    selected_nums = []
    for n_str in raw_nums:
        if not n_str.isdigit():
            await update.message.reply_text(f"⚠️ **{n_str}** ትክክለኛ ቁጥር አይደለም። እባክዎ ሁሉንም ቁጥሮች በትክክል በኮማ ለይተው እንደገና ይጻፉ:")
            return SELECTING_NUMBERS
        selected_nums.append(int(n_str))

    if not selected_nums:
        await update.message.reply_text("እባክዎ ቢያንስ አንድ ቁጥር ይምረጡ:")
        return SELECTING_NUMBERS

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()

    # ቁጥሮቹ ክፍት መሆናቸውን ማረጋገጥ
    unavailable_nums = []
    for num in selected_nums:
        cursor.execute("SELECT status FROM numbers WHERE number = ?", (num,))
        row = cursor.fetchone()
        if not row or row[0] != 'AVAILABLE':
            unavailable_nums.append(num)

    if unavailable_nums:
        conn.close()
        await update.message.reply_text(f"⚠️ ይቅርታ! የሚከተሉት ቁጥሮች ({', '.join(map(str, unavailable_nums))}) ተይዘዋል ወይም በሂደት ላይ ናቸው። እባክዎ ነፃ ቁጥሮችን ብቻ በመምረጥ እንደገና ይሞክሩ:")
        return SELECTING_NUMBERS

    conn.close()
    context.user_data['selected_numbers'] = selected_nums

    await update.message.reply_text(
        f"አሪፍ! የመረጧቸው ቁጥሮች ብዛት: **{len(selected_nums)}** ናቸው።\n\nአሁን እባክዎ **ሙሉ ስምዎን (First & Last Name)** ይጻፉልን፦",
        parse_mode="Markdown"
    )
    return FULL_NAME

# ሙሉ ስም መቀበል
async def receive_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text.strip()
    await update.message.reply_text("እጅግ መልካም! አሁን ደግሞ **ስልክ ቁጥርዎን** ያስገቡልን፦")
    return PHONE_NUMBER

# ስልክ ቁጥር መቀበል እና አጠቃላይ ክፍያ ማሳየት
async def receive_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone_number'] = update.message.text.strip()
    selected_nums = context.user_data['selected_numbers']
    total_price = len(selected_nums) * 100
    nums_str = ", ".
