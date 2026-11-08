import os
import sqlite3
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
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
def get_main_keyboard(is_admin=False):
    keyboard = [
        ["🔢 ቁጥር መያዝ", "📋 ነፃ ቁጥሮች ማየት"],
        ["ℹ️ መረጃ", "📞 እገዛ"]
    ]
    if is_admin:
        keyboard.append(["📊 የተያዙ ቁጥሮች (አድሚን)"])
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
        "✅ ቁጥር መያዝ\n"
        "✅ ነፃ ቁጥሮች ማየት\n"
        "✅ የአገልግሎት መረጃ ማየት\n\n"
        "እእንኳን ወደ ቤታችን በሰላም መጡ!"
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

# 📊 የተያዙ ቁጥሮችን ማየት (ለአድሚን ብቻ)
async def show_booked_numbers_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("ይህ ትዕዛዝ ለአድሚን ብቻ የተፈቀደ ነው።")
        return

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.number, n.status, u.full_name, u.phone_number 
        FROM numbers n 
        LEFT JOIN users u ON n.user_id = u.user_id 
        WHERE n.status != 'AVAILABLE' 
        ORDER BY n.number ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📊 እስካሁን የተያዘ ወይም በሂደት ላይ ያለ ቁጥር የለም።")
        return

    msg = "📊 **የተያዙ እና በሂደት ላይ ያሉ ቁጥሮች ዝርዝር፦**\n\n"
    for r in rows:
        num, status, name, phone = r
        status_icon = "🟡 (በሂደት ላይ/Pending)" if status == 'PENDING' else "🟢 (ጸድቋል/Booked)"
        name_str = name if name else "ስም የለም"
        phone_str = phone if phone else "ስልክ የለም"
        msg += f"ቁጥር **{num}** - {status_icon}\n👤 {name_str} | 📞 {phone_str}\n\n"

    if len(msg) > 4000:
        msg = msg[:4000] + "\n\n... (ዝርዝሩ በጣም ስለረዘመ ቆርጧል)"

    await update.message.reply_text(msg, parse_mode="Markdown")

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

    # ደንበኛ የተያዘ ቁጥር ከመረጠ
    if not row or row[0] != 'AVAILABLE':
        await update.message.reply_text(f"⚠️ ይቅርታ! ቁጥር **{num}** ተይዟል (ወይም በሂደት ላይ ነው።) እባክዎ ሌላ ነፃ ቁጥር ይምረጡ:", parse_mode="Markdown")
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
    
    # ክፍያ የሚፈጸምባቸው ባንኮች (ኮፒ እንዲደረጉ የተደረጉ)
    payment_text = (
        f"💳 **የክፍያ ማስተላለፊያ መረጃ (25ተኛ ዙር):**\n\n"
        f"መረጡት ቁጥር: **{num}** (ብር 100)\n\n"
        "እባክዎ ከታች ከሚገኙት የባንክ አካውንቶች በአንዱ ክፍያውን ፈጽመው ስክሪንሾት ይላኩልን፦\n\n"
        "🏦 **Commercial Bank of Ethiopia (CBE):**\n`1000239845577`\n\n"
        "📱 **Telebirr:**\n`0941506799`\n\n"
        "🏦 **Dashen Bank:**\n`5273247599011`\n\n"
        "*(ማስታወሻ: የባንክ ቁጥሮቹን ለመውሰድ (Copy) ላይዋቸው ሲጫኑ በራስ ሰር ኮፒ ይሆናሉ)*"
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
    cursor.execute("UPDATE numbers SET status = 'PENDING', user_id = ? WHERE number = ?", (user.id, num))
    cursor.execute("INSERT OR REPLACE INTO users (user_id, full_name, phone_number) VALUES (?, ?, ?)", (user.id, full_name, phone))
    cursor.execute("INSERT INTO transactions (user_id, number, screenshot_id, status) VALUES (?, ?, ?, 'PENDING')", (user.id, num, photo_file))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "✅ **ክፍያዎ በትክክል ተልኳል!**\n\n"
        "አድሚኑ ክፍያውን አረጋግጦ ቁጥርዎን እስከሚያጸድቅ ድረስ በትንሽ ቆይታ ይጠብቁ። እናመሰግናለን!",
        reply_markup=get_main_keyboard(user.id == ADMIN_ID),
        parse_mode="Markdown"
    )

    # ለአድሚን ማሳወቂያ እና የማረጋገጫ ቁልፎች መላክ
    if ADMIN_ID != 0:
        try:
            admin_msg = (
                f"🔔 **አዲስ የክፍያ ጥያቄ መጥቷል!**\n\n"
                f"👤 ስም: {full_name}\n"
                f"📞 ስልክ: {phone}\n"
                f"🔢 የተመረጠ ቁጥር: {num}\n"
                f"🆔 ዩዘር ID: {user.id}"
            )
            keyboard = [
                [
                    InlineKeyboardButton("✅ ክፍያው ትክክል ነው", callback_data=f"approve_{user.id}_{num}"),
                    InlineKeyboardButton("❌ ክፍያው ትክክል አይደለም", callback_data=f"reject_{user.id}_{num}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file, caption=admin_msg, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"አድሚን ዘንድ መላክ አልተቻለም: {e}")

    return ConversationHandler.END

# ----------------- የአድሚን ውሳኔ (Callback Query) -----------------
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  
    parts = data.split("_")
    action = parts[0]
    target_user_id = int(parts[1])
    num = int(parts[2])

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()

    if action == "approve":
        cursor.execute("UPDATE numbers SET status = 'BOOKED' WHERE number = ?", (num,))
        cursor.execute("UPDATE transactions SET status = 'APPROVED' WHERE user_id = ? AND number = ?", (target_user_id, num))
        
        cursor.execute("SELECT full_name, phone_number FROM users WHERE user_id = ?", (target_user_id,))
        user_row = cursor.fetchone()
        conn.commit()
        conn.close()

        if user_row:
            f_name, f_phone = user_row
            success_msg = (
                f"🎉 **እንኳን ደስ አለዎት! ክፍያዎ ጸድቋል!**\n\n"
                f"👤 ስም: {f_name}\n"
                f"📞 ስልክ: {f_phone}\n"
                f"🔢 የያዙት ቁጥር: **{num}**\n\n"
                "መልካም ዕድል!!"
            )
            try:
                await context.bot.send_message(chat_id=target_user_id, text=success_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"ለተጠቃሚው ማሳወቂያ መላክ አልተቻለም: {e}")

        await query.edit_message_caption(caption=f"{query.message.caption}\n\n✅ **ሁኔታ:** ክፍያው በአድሚን ጸድቋል!")

    elif action == "reject":
        cursor.execute("UPDATE numbers SET status = 'AVAILABLE', user_id = NULL WHERE number = ?", (num,))
        cursor.execute("UPDATE transactions SET status = 'REJECTED' WHERE user_id = ? AND number = ?", (target_user_id, num))
        conn.commit()
        conn.close()

        reject_msg = (
            f"❌ **ይቅርታ! ክፍያዎ ተቀባይነት አላገኘም (ውድቅ ተደርጓል)**\n\n"
            f"የመረጡት ቁጥር (**{num}**) ተሰርዟል። እባክዎ ትክክለኛ የክፍያ ስክሪንሾት በመላክ እንደገና ይሞክሩ።"
        )
        try:
            await context.bot.send_message(chat_id=target_user_id, text=reject_msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"ለተጠቃሚው ውድቅ መደረጉን መላክ አልተቻለም: {e}")

        await query.edit_message_caption(caption=f"{query.message.caption}\n\n❌ **ሁኔታ:** ክፍያው ውድቅ ተደርጓል!")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ምዝገባው ተሰርዟል።", reply_markup=get_main_keyboard(update.effective_user.id == ADMIN_ID))
    return ConversationHandler.END

# ℹ️ መረጃ
async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ **የአገልግሎት መረጃ፦**\n\n"
        "ኤዱ ከአረካ online መዝናኛ\n"
        "🔥 **ፈጣን ዕለታው ዕቁብ** 🔥\n"
        "📌 **በ100 ብር 12,000 ብር ደራሽ** (25ተኛ ዙር)\n\n"
        "ይህ ቦት ተሳታፊዎች ምዝገባን እና ክፍያ ክትትልን በራስ ሰር ለማስተካከል የተዘጋጀ ነው።"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# 📞 እገዛ
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📞 **እገዛ እና ድጋፍ፦**\n\n"
        "ማንኛውም ችግር ሲያጋጥምዎ ወይም እርዳታ ሲፈልጉ በቀጥታ አድሚኑን ማነጋገር ይችላሉ።\n\n"
        f"👤 **የአድሚን ስልክ ቁጥር፦** `{ADMIN_PHONE}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

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
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.Regex("^📋 ነፃ ቁጥሮች ማየት$"), show_free_numbers))
    application.add_handler(MessageHandler(filters.Regex("^📊 የተያዙ ቁጥሮች \\(አድሚን\\)$"), show_booked_numbers_admin))
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ መረጃ$"), info_handler))
    application.add_handler(MessageHandler(filters.Regex("^📞 እገዛ$"), help_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    logger.info("🤖 Edu Online Mezenna ቦት በሥራ ላይ ነው...")
    application.run_polling()

if __name__ == "__main__":
    main()
