import os
import sqlite3
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

# Environment Variables መጫን
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ሎጊንግ ማዋቀር
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

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

# ----------------- ዋና ሜኑ እና ቁልፎች -----------------
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🔢 ቁጥር መያዝ"), KeyboardButton("📋 ነፃ ቁጥሮች ማየት")],
        [KeyboardButton("ℹ️ መረጃ"), KeyboardButton("📞 እገዛ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ----------------- የቦት ዋና ተግባራት -----------------
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
    # በጣም ብዙ ቁጥሮች ከሆኑ በዝርዝር ላለመጨናነቅ በኮማ (comma) እንለየዋለን
    nums_text = ", ".join(free_nums)
    
    response_msg = f"📋 **ቀሪ ነፃ ቁጥሮች (ጠቅላላ {len(free_nums)} ቁጥሮች አሉ):**\n\n{nums_text}"
    
    # ቴሌግራም የሜሴጅ ገደብ ስላለው ረጅም ከሆነ ቆርጦ ይልካል
    if len(response_msg) > 4000:
        response_msg = response_msg[:4000] + "\n\n... (ሌሎች ቁጥሮችም አሉ)"

    await update.message.reply_text(response_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# 🔢 ቁጥር መያዝ
async def choose_number_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔢 **ቁጥር ለመያዝ፦**\n\n"
        "እባክዎ ከ 1 እስከ 200 ያሉትን ነፃ ቁጥሮች በማየት የሚፈልጉትን ቁጥር በቀጥታ ጽሁፍ መልክ ይላኩልን (ለምሳሌ፦ `45` ብለው ይጻፉ)።"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# ℹ️ መረጃ
async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ **የአገልግሎት መረጃ፦**\n\n"
        "ይህ ቦት የ Edu Online መዘኛ ተሳታፊዎች ምዝገባን እና ክፍያ ክትትልን በራስ ሰር ለማስተካከል የተዘጋጀ ነው።"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# 📞 እገዛ
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📞 **እገዛ ማግኘት፦**\n\n"
        "ማንኛውም ችግር ሲያጋጥምዎ ወይም እርዳታ ሲፈልጉ አድሚኑን ማነጋገር ይችላሉ።"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# ----------------- ፖርት ክፍት ማድረጊያ ሰርቨር -----------------
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

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^📋 ነፃ ቁጥሮች ማየት$"), show_free_numbers))
    application.add_handler(MessageHandler(filters.Regex("^🔢 ቁጥር መያዝ$"), choose_number_prompt))
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ መረጃ$"), info_handler))
    application.add_handler(MessageHandler(filters.Regex("^📞 እገዛ$"), help_handler))
    
    # ሌላ ያልታወቀ ቴክስት ሲመጣ
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    logger.info("🤖 Edu Online Mezenna ቦት በሥራ ላይ ነው...")
    application.run_polling()

if __name__ == "__main__":
    main()
