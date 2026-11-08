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

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_PHONE = "+251941506799"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

SELECTING_NUMBERS, FULL_NAME, PHONE_NUMBER, PAYMENT_SCREENSHOT, ADMIN_ACTION = range(5)

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

def get_main_keyboard(is_admin=False):
    keyboard = [
        ["🔢 ቁጥር መያዝ", "📋 ነፃ ቁጥሮች ማየት"],
        ["ℹ️ መረጃ", "📞 እገዛ"]
    ]
    if is_admin:
        keyboard.append(["⚙️ አድሚን መቆጣጠሪያ"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# በሂደት ውስጥ (Conversation ውስጥ) የሚታይ የባክ ቁልፍ ኪቦርድ
def get_back_keyboard():
    keyboard = [
        ["🔙 ወደ ዋና ሜኑ"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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

async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ **የአገልግሎት መረጃ፦**\n\n"
        "ኤዱ ከአረካ online መዝናኛ\n"
        "🔥 **ፈጣን ዕለታው ዕቁብ** 🔥\n"
        "📌 **በ100 ብር 12,000 ብር ደራሽ** (25ተኛ ዙር)\n\n"
        "ይህ ቦት ተሳታፊዎች ምዝገባን እና ክፍያ ክትትልን በራስ ሰር ለማስተካከል የተዘጋጀ ነው።"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📞 **እገዛ እና ድጋፍ፦**\n\n"
        "ማንኛውም ችግር ሲያጋጥምዎ ወይም እርዳታ ሲፈልጉ በቀጥታ አድሚኑን ማነጋገር ይችላሉ።\n\n"
        f"👤 **የአድሚን ስልክ ቁጥር፦** `{ADMIN_PHONE}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        ["📊 የተያዙ ቁጥሮች ማየት"],
        ["🗑 ቁጥር መሰረዝ (Release)", "➕ አዲስ ቁጥሮችን መጨመር"],
        ["🔙 ወደ ዋና ሜኑ"]
    ]
    await update.message.reply_text("⚙️ **የአድሚን መቆጣጠሪያ ፓነል:**", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown")

async def choose_number_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔢 **ቁጥር ለመያዝ፦**\n\n"
        "እባክዎ የሚፈልጉትን ቁጥሮች በኮማ (comma) ለይተው ይጻፉልን (ለምሳሌ፦ `41,67,81,8,91,117` ብለው ይላኩ)።\n"
        "*(እያንዳንዱ ቁጥር 100 ብር ይመደብለታል)*"
    )
    await update.message.reply_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    return SELECTING_NUMBERS

async def receive_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    raw_nums = text.replace(" ", "").split(",")
    selected_nums = []
    for n_str in raw_nums:
        if not n_str.isdigit():
            await update.message.reply_text(f"⚠️ **{n_str}** ትክክለኛ ቁጥር አይደለም። እባክዎ ሁሉንም ቁጥሮች በትክክል በኮማ ለይተው እንደገና ይጻፉ:", reply_markup=get_back_keyboard())
            return SELECTING_NUMBERS
        selected_nums.append(int(n_str))

    if not selected_nums:
        await update.message.reply_text("እባክዎ ቢያንስ አንድ ቁጥር ይምረጡ:", reply_markup=get_back_keyboard())
        return SELECTING_NUMBERS

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    unavailable_nums = []
    for num in selected_nums:
        cursor.execute("SELECT status FROM numbers WHERE number = ?", (num,))
        row = cursor.fetchone()
        if not row or row[0] != 'AVAILABLE':
            unavailable_nums.append(num)

    if unavailable_nums:
        conn.close()
        await update.message.reply_text(f"⚠️ ይቅርታ! የሚከተሉት ቁጥሮች ({', '.join(map(str, unavailable_nums))}) ተይዘዋል ወይም በሂደት ላይ ናቸው። እባክዎ ነፃ ቁጥሮችን ብቻ በመምረጥ እንደገና ይሞክሩ:", reply_markup=get_back_keyboard())
        return SELECTING_NUMBERS

    conn.close()
    context.user_data['selected_numbers'] = selected_nums
    await update.message.reply_text(
        f"አሪፍ! የመረጧቸው ቁጥሮች ብዛት: **{len(selected_nums)}** ናቸው።\n\nአሁን እባክዎ **ሙሉ ስምዎን (First & Last Name)** ይጻፉልን፦",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    return FULL_NAME

async def receive_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text.strip()
    await update.message.reply_text("እጅግ መልካም! አሁን ደግሞ **ስልክ ቁጥርዎን** ያስገቡልን፦", reply_markup=get_back_keyboard())
    return PHONE_NUMBER

async def receive_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone_number'] = update.message.text.strip()
    selected_nums = context.user_data['selected_numbers']
    total_price = len(selected_nums) * 100
    nums_str = ", ".join(map(str, selected_nums))
    payment_text = (
        f"💳 **የክፍያ ማስተላለፊያ መረጃ (25ተኛ ዙር):**\n\n"
        f"የመረጧቸው ቁጥሮች: **{nums_str}**\n"
        f"ጠቅላላ የቁጥር ብዛት: **{len(selected_nums)}**\n"
        f"💰 **አጠቃላይ የሚከፈለው ብር:** **{total_price} ብር**\n\n"
        "እባክዎ ከታች ከሚገኙት የባንክ አካውንቶች በአንዱ ክፍያውን ፈጽመው ስክሪንሾት ይላኩልን፦\n\n"
        "🏦 **Commercial Bank of Ethiopia (CBE):**\n`1000239845577`\n\n"
        "📱 **Telebirr:**\n`0941506799`\n\n"
        "🏦 **Dashen Bank:**\n`5273247599011`"
    )
    await update.message.reply_text(payment_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    return PAYMENT_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("እባክዎ የክፍያውን ማረጋገጫ **ስክሪንሾት (Photo)** በመላክ ይተባበሩን:", reply_markup=get_back_keyboard())
        return PAYMENT_SCREENSHOT

    photo_file = update.message.photo[-1].file_id
    user = update.effective_user
    selected_nums = context.user_data.get('selected_numbers')
    full_name = context.user_data.get('full_name')
    phone = context.user_data.get('phone_number')
    total_price = len(selected_nums) * 100
    nums_str = ",".join(map(str, selected_nums))

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    for num in selected_nums:
        cursor.execute("UPDATE numbers SET status = 'PENDING', user_id = ? WHERE number = ?", (user.id, num))
    cursor.execute("INSERT OR REPLACE INTO users (user_id, full_name, phone_number) VALUES (?, ?, ?)", (user.id, full_name, phone))
    cursor.execute("INSERT INTO transactions (user_id, numbers_list, screenshot_id, status) VALUES (?, ?, ?, 'PENDING')", (user.id, nums_str, photo_file))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "✅ **ክፍያዎ በትክክል ተልኳል!**\n\n"
        "አድሚኑ ክፍያውን አረጋግጦ ቁጥርዎን እስከሚያጸድቅ ድረስ በትንሽ ቆይታ ይጠብቁ። እናመሰግናለን!",
        reply_markup=get_main_keyboard(user.id == ADMIN_ID),
        parse_mode="Markdown"
    )

    if ADMIN_ID != 0:
        try:
            admin_msg = (
                f"🔔 **አዲስ የክፍያ ጥያቄ መጥቷል!**\n\n"
                f"👤 ስም: {full_name}\n"
                f"📞 ስልክ: {phone}\n"
                f"🔢 የተመረጡ ቁጥሮች: {nums_str}\n"
                f"💰 ጠቅላላ ክፍያ: {total_price} ብር\n"
                f"🆔 ዩዘር ID: {user.id}"
            )
            keyboard = [
                [
                    InlineKeyboardButton("✅ ክፍያው ትክክል ነው", callback_data=f"approve_{user.id}_{nums_str}"),
                    InlineKeyboardButton("❌ ክፍያው ትክክል አይደለም", callback_data=f"reject_{user.id}_{nums_str}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file, caption=admin_msg, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"አድሚን ዘንድ መላክ አልተቻለም: {e}")

    return ConversationHandler.END

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  
    parts = data.split("_")
    action = parts[0]
    target_user_id = int(parts[1])
    nums_str = parts[2]
    nums_list = [int(n) for n in nums_str.split(",")]

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()

    if action == "approve":
        for num in nums_list:
            cursor.execute("UPDATE numbers SET status = 'BOOKED' WHERE number = ?", (num,))
        cursor.execute("UPDATE transactions SET status = 'APPROVED' WHERE user_id = ? AND numbers_list = ?", (target_user_id, nums_str))
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
                f"🔢 የያዙዋቸው ቁጥሮች: **{nums_str}**\n\n"
                "መልካም ዕድል!!"
            )
            try:
                await context.bot.send_message(chat_id=target_user_id, text=success_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"ለተጠቃሚው ማሳወቂያ መላክ አልተቻለም: {e}")

        await query.edit_message_caption(caption=f"{query.message.caption}\n\n✅ **ሁኔታ:** ክፍያው በአድሚን ጸድቋል!")

    elif action == "reject":
        for num in nums_list:
            cursor.execute("UPDATE numbers SET status = 'AVAILABLE', user_id = NULL WHERE number = ?", (num,))
        cursor.execute("UPDATE transactions SET status = 'REJECTED' WHERE user_id = ? AND numbers_list = ?", (target_user_id, nums_str))
        conn.commit()
        conn.close()

        reject_msg = (
            f"❌ **ይቅርታ! ክፍያዎ ተቀባይነት አላገኘም (ውድቅ ተደርጓል)**\n\n"
            f"የመረጧቸው ቁጥሮች (**{nums_str}**) ተሰርዘዋል። እባክዎ ትክክለኛ የክፍያ ስክሪንሾት በመላክ እንደገና ይሞክሩ።"
        )
        try:
            await context.bot.send_message(chat_id=target_user_id, text=reject_msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"ለተጠቃሚው ውድቅ መደረጉን መላክ አልተቻለም: {e}")

        await query.edit_message_caption(caption=f"{query.message.caption}\n\n❌ **ሁኔታ:** ክፍያው ውድቅ ተደርጓል!")

async def show_booked_numbers_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
        status_icon = "🟡 (Pending)" if status == 'PENDING' else "🟢 (Booked)"
        msg += f"ቁጥር **{num}** - {status_icon}\n👤 {name} | 📞 {phone}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def release_number_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🗑️ ሊያጠፉት (ነፃ ሊያደርጉት) የሚፈልጉትን ቁጥር ብቻውን ይጻፉ (ለምሳሌ: `45`):")
    context.user_data['admin_action_type'] = 'release'
    return ADMIN_ACTION

async def add_numbers_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("➕ ወደ ዳታቤዝ ለመጨመር ወይም አጠቃላይ ብዛቱን ለማስተካከል የሚፈልጉትን ከፍተኛ ቁጥር ያስገቡ (ለምሳሌ: `250`):")
    context.user_data['admin_action_type'] = 'add'
    return ADMIN_ACTION

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    text = update.message.text.strip()
    action_type = context.user_data.get('admin_action_type')

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    if action_type == 'release':
        if not text.isdigit():
            await update.message.reply_text("እባክዎ ትክክለኛ ቁጥር ያስገቡ:")
            conn.close()
            return ADMIN_ACTION
        num = int(text)
        cursor.execute("UPDATE numbers SET status = 'AVAILABLE', user_id = NULL WHERE number = ?", (num,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ ቁጥር **{num}** ተሰርዞ አሁን ነፃ (AVAILABLE) ሆኗል!", reply_markup=get_main_keyboard(True), parse_mode="Markdown")
    elif action_type == 'add':
        if not text.isdigit():
            await update.message.reply_text("እባክዎ ትክክለኛ ቁጥር ያስገቡ:")
            conn.close()
            return ADMIN_ACTION
        max_num = int(text)
        for i in range(1, max_num + 1):
            cursor.execute("INSERT OR IGNORE INTO numbers (number, status) VALUES (?, 'AVAILABLE')", (i,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ እስከ **{max_num}** ያሉት ቁጥሮች ተስተካክለዋል/ተጨምረዋል!", reply_markup=get_main_keyboard(True), parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ተሰርዟል።", reply_markup=get_main_keyboard(update.effective_user.id == ADMIN_ID))
    return ConversationHandler.END

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
            SELECTING_NUMBERS: [
                MessageHandler(filters.Regex("^🔙 ወደ ዋና ሜኑ$"), start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_numbers)
            ],
            FULL_NAME: [
                MessageHandler(filters.Regex("^🔙 ወደ ዋና ሜኑ$"), start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_full_name)
            ],
            PHONE_NUMBER: [
                MessageHandler(filters.Regex("^🔙 ወደ ዋና ሜኑ$"), start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone_number)
            ],
            PAYMENT_SCREENSHOT: [
                MessageHandler(filters.Regex("^🔙 ወደ ዋና ሜኑ$"), start),
                MessageHandler(filters.PHOTO | filters.TEXT, receive_screenshot)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    admin_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🗑 ቁጥር መሰረዝ \\(Release\\)$"), release_number_prompt),
            MessageHandler(filters.Regex("^➕ አዲስ ቁጥሮችን መጨመር$"), add_numbers_prompt)
        ],
        states={
            ADMIN_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_action)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(admin_conv_handler)
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.Regex("^📋 ነፃ ቁጥሮች ማየት$"), show_free_numbers))
    application.add_handler(MessageHandler(filters.Regex("^⚙️ አድሚን መቆጣጠሪያ$"), admin_panel))
    application.add_handler(MessageHandler(filters.Regex("^📊 የተያዙ ቁጥሮች ማየት$"), show_booked_numbers_admin))
    application.add_handler(MessageHandler(filters.Regex("^🔙 ወደ ዋና ሜኑ$"), start))
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ መረጃ$"), info_handler))
    application.add_handler(MessageHandler(filters.Regex("^📞 እገዛ$"), help_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    logger.info("🤖 Edu Online Mezenna ቦት በሥራ ላይ ነው...")
    application.run_polling()

if __name__ == "__main__":
    main()
