import os
import sqlite3
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
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
SELECTING_NUMBER, FULL_NAME, PHONE_NUMBER, PAYMENT_SCREENSHOT = range(4)

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
        number INTEGER,
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
def get_main_keyboard():
    keyboard = [
        [ReplyKeyboardRemove()],
        [("🔢 ቁጥር መያዝ"), ("📋 ነፃ ቁጥሮች ማየት")],
        [("ℹ️ መረጃ"), ("📞 እገዛ")]
    ]
    return ReplyKeyboardMarkup([
        ["🔢 ቁጥር መያዝ", "📋 ነፃ ቁጥሮች ማየት"],
        ["ℹ️ መረጃ", "📞 እገዛ"]
    ], resize_keyboard=True)

# /start ትዕዛዝ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"⭐ **Edu Online መዘኛ** ⭐ ሰላም {user.first_name}!\n\n"
        "በዚህ Bot የሚከተሉትን ማድረግ ይችላሉ:-\n"
        "✅ ቁጥር መያዝ\n"
        "✅ ነፃ ቁጥሮች ማየት\n"
        "✅ የአገልግሎት መረጃ ማየት\n\n"
        "እእንኳን ወደ ቤታችን በሰላም መጡ!"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    return ConversationHandler.END

# 📋 ነፃ ቁጥሮችን ማየት
async def show_free_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    cursor.execute("SELECT number FROM numbers WHERE status = 'AVAILABLE' ORDER BY number ASC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("ይቅርታ, አሁን ሁሉም ቁጥሮች ተይዘዋል!", reply_markup=get_main_keyboard())
        return

    free_nums = [str(row[0]) for row in rows]
    nums_text = ", ".join(free_nums)
    response_msg = f"📋 **ቀሪ ነፃ ቁጥሮች (ጠቅላላ {len(free_nums)} ቁጥሮች አሉ):**\n\n{nums_text}"
    
    if len(response_msg) > 4000:
        response_msg = response_msg[:4000] + "\n\n... (ሌሎች ቁጥሮችም አሉ)"

    await update.message.reply_text(response_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# 🔢 ቁጥር መያዝ ማስጀመር
async def choose_number_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔢 **ቁጥር ለመያዝ፦**\n\n"
        "እባክዎ ከ 1 እስከ 200 ያሉትን ነፃ ቁጥሮች በማየት የሚፈልጉትን ቁጥር ብቻውን (ለምሳሌ `45` ብለው) ይጻፉልን።"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    return SELECTING_NUMBER

# ቁጥር መቀበል እና ማረጋገጥ
async def receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("እባክዎ ትክክለኛ ቁጥር ብቻ ይጻፉ (ለምሳሌ፦ 45):")
        return SELECTING_NUMBER

    num = int(text)
    if num < 1 or num > 200:
        await update.message.reply_text("እባክዎ ከ 1 እስከ 200 መካከል ያለ ቁጥር ብቻ ይምረጡ:")
        return SELECTING_NUMBER

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM numbers WHERE number = ?", (num,))
    row = cursor.fetchone()
    conn.close()

    if not row or row[0] != 'AVAILABLE':
        await update.message.reply_text(f"ይቅርታ! ቁጥር **{num}** უკვე ተይዟል ወይም ሌላ ቁጥር ይሞክሩ:", parse_mode="Markdown")
        return SELECTING_NUMBER

    context.user_data['selected_number'] = num
    await update.message.reply_text(
        f"አሪፍ! ቁጥር **{num}** መርጠዋል።\n\nአሁን እባክዎ **ሙሉ ስምዎን (First & Last Name)** ይጻፉልን፦",
        parse_mode="Markdown"
    )
    return FULL_NAME

# ሙሉ ስም መቀበል
async def receive_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text.strip()
    await update.message.reply_text("እጅግ መልካም! አሁን ደግሞ **ስልክ ቁጥርዎን** ያስገቡልን፦")
    return PHONE_NUMBER

# ስልክ ቁጥር መቀበል
async def receive_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone_number'] = update.message.text.strip()
    num = context.user_data['selected_number']
    
    payment_text = (
        f"💳 **የክፍያ ማስተላለፊያ መረጃ፦**\n\n"
        f"መረጡት ቁጥር: **{num}**\n\n"
        "እባክዎ በንግድ ባንክ / CBE / Telebirr ክፍያውን ፈጽመው የክፍያ ማረጋገጫ (Screenshot) በዚህ ቦት ላይ ፎቶ አንስተው ይላኩልን።"
    )
    await update.message.reply_text(payment_text, parse_mode="Markdown")
    return PAYMENT_SCREENSHOT

# የክፍያ ስክሪንሾት መቀበል
async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("እባክዎ የክፍያውን ማረጋገጫ **ስክሪንሾት (Photo)** በመላክ ይተባበሩን:")
        return PAYMENT_SCREENSHOT

    photo_file = update.message.photo[-1].file_id
    user = update.effective_user
    num = context.user_data.get('selected_number')
    full_name = context.user_data.get('full_name')
    phone = context.user_data.get('phone_number')

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    # ቁጥሩን PENDING ማድረግ
    cursor.execute("UPDATE numbers SET status = 'PENDING', user_id = ? WHERE number = ?", (user.id, num))
    cursor.execute("INSERT OR REPLACE INTO users (user_id, full_name, phone_number) VALUES (?, ?, ?)", (user.id, full_name, phone))
    cursor.execute("INSERT INTO transactions (user_id, number, screenshot_id, status) VALUES (?, ?, ?, 'PENDING')", (user.id, num, photo_file))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "✅ **ክፍያዎ በትክክል ተልኳል!**\n\n"
        "አድሚኑ ክፍያውን አረጋግጦ ቁጥርዎን እስከሚያጸድቅ ድረስ በትዕግስት ይጠብቁ። እናመሰግናለን!",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

    # አድሚን ካለ ለአድሚን ማሳወቅ ይቻላል
    if ADMIN_ID != 0:
        try:
            admin_msg = (
                f"🔔 **አዲስ የክፍያ ጥያቄ መጥቷል!**\n\n"
                f"👤 ስም: {full_name}\n"
                f"📞 ስልክ: {phone}\n"
                f"🔢 የተመረጠ ቁጥር: {num}\n"
                f"🆔 ዩዘር ID: {user.id}"
            )
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file, caption=admin_msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"አድሚን ዘንድ መላክ አልተቻለም: {e}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ምዝገባው ተሰርዟል።", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# ℹ️ መረጃ
async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ **የአገልግሎት መረጃ፦**\n\n"
        "ይህ ቦት የ Edu Online መዘኛ ተሳታፊዎች ምዝገባን እና ክፍያ ክትትልን በራስ ሰር ለማስተካከል የተዘጋጀ ነው።"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# 📞 እገዛ (አድሚን ስልክ ቁጥርን ጨምሮ)
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📞 **እገዛ እና ድጋፍ፦**\n\n"
        "ማንኛውም ችግር ሲያጋጥምዎ ወይም እርዳታ ሲፈልጉ በቀጥታ አድሚኑን ማነጋገር ይችላሉ።\n\n"
        f"👤 **የአድሚን ስልክ ቁጥር፦** `{ADMIN_PHONE}`"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# ----------------- ፖርት ሰርቨር -----------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Edu Online Mezenna Bot is running!")

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

def main():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN አልተገኘም!")
        return

    t = threading.Thread(target=run_http_server)
    t.daemon = True
    t.start()

    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔢 ቁጥር መያዝ$"), choose_number_start)],
        states={
            SELECTING_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_number)],
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_full_name)],
            PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone_number)],
            PAYMENT_SCREENSHOT: [MessageHandler(filters.PHOTO | filters.TEXT, receive_screenshot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex("^📋 ነፃ ቁጥሮች ማየት$"), show_free_numbers))
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ መረጃ$"), info_handler))
    application.add_handler(MessageHandler(filters.Regex("^📞 እገዛ$"), help_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    logger.info("🤖 Edu Online Mezenna ቦት በሥራ ላይ ነው...")
    application.run_polling()

if __name__ == "__main__":
    main()
