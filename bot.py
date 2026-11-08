import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
from dotenv import load_dotenv

# አካባቢያዊ (Environment) ተለዋዋጮችን መጫን
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # የአድሚን ቴሌግራም ID

# ሎግንግ ማዋቀር
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
    # ተጠቃሚዎች ሰንጠረዥ
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            phone_number TEXT
        )
    """)
    # ቁጥሮች ሰንጠረዥ (ከ1 እስከ 200 በነባሪ መፍጠር ይቻላል)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS numbers (
            number INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'AVAILABLE', -- AVAILABLE, PENDING, BOOKED
            user_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)
    # ግብይቶች ሰንጠረዥ
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
    
    # ከ1 እስከ 200 ቁጥሮችን በራስ ሰር ማስገባት (ከሌሉ)
    cursor.execute("SELECT COUNT(*) FROM numbers")
    if cursor.fetchone()[0] == 0:
        for i in range(1, 201):
            cursor.execute("INSERT OR IGNORE INTO numbers (number, status) VALUES (?, 'AVAILABLE')", (i,))
        conn.commit()
    conn.close()

init_db()

# ----------------- ትዕዛዞች እና ሂደቶች -----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"ሰላም {user.first_name}! ወደ **Edu Online Mezenna** እንኳን በደህና መጡ።\n\n"
        "ይህ ቦት የሚፈልጉትን ቁጥር መርጠው እንዲመዘገቡ እና ክፍያ አረጋግጦ እንዲይዙ ያስችሎታል።\n\n"
        "📋 **የሚገኙ ትዕዛዞች:**\n"
        "/numbers - የሚገኙ ቁጥሮችን ለማየት\n"
        "/register - ቁጥር መርጠው ለመመዝገብ\n"
        "/myinfo - የእርስዎን መረጃ ለማየት\n"
        "/help - እხმარታ ለማግኘት"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **የእርዳታ መመሪያ:**\n\n"
        "1. `/numbers` በመጫን ክፍት የሆኑ ቁጥሮችን ይመልከቱ።\n"
        "2. `/register` በመጠቀም የሚፈልጉትን ቁጥር ይምረጡ።\n"
        "3. ሙሉ ስምዎን እና ስልክ ቁጥርዎን ያስገቡ።\n"
        "4. የክፍያ ማረጋገጫ (Screenshot) ይላኩ።\n"
        "5. አድሚኑ ክፍያውን ሲያረጋግጥ ቁጥሩ በስምዎ ይመዘገባል።"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def show_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    cursor.execute("SELECT number FROM numbers WHERE status = 'AVAILABLE' LIMIT 50")
    available = [str(row[0]) for row in cursor.fetchall()]
    conn.close()

    if not available:
        await update.message.reply_text("ይቅርታ! በአሁኑ ሰዓት ምንም ክፍት ቁጥር የለም።")
        return

    nums_str = ", ".join(available)
    await update.message.reply_text(
        f"🟢 **ክፍት ቁጥሮች (የመጀመሪያዎቹ 50):**\n{nums_str}\n\n"
        "ቁጥር ለመምረጥ `/register` የሚለውን ይጠቀሙ።",
        parse_mode="Markdown"
    )

# --- ምዝገባ እና ቁጥር ምርጫ ሂደት (Conversation Handler) ---

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("እባክዎ መመዝገብ የሚፈልጉትን ቁጥር ከ1 እስከ 200 አስገቡ:")
    return SELECTING_NUMBER

async def receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit():
        await update.message.reply_text("እባክዎ ትክክለኛ ቁጥር ብቻ ያስገቡ:")
        return SELECTING_NUMBER

    num = int(text)
    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM numbers WHERE number = ?", (num,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("ይህ ቁጥር ከ1 እስከ 200 ባለው ክልል ውስጥ የለም ወይም የጸዳ አይደለም። እባክዎ እንደገና ይሞክሩ:")
        return SELECTING_NUMBER

    if row[0] != 'AVAILABLE':
        await update.message.reply_text("ይቅርታ! ይህ ቁጥር ተይዟል ወይም በሂደት ላይ ነው። እባክዎ ሌላ ቁጥር ይምረጡ:")
        return SELECTING_NUMBER

    context.user_data['selected_number'] = num
    await update.message.reply_text(f"አስደሳች! ቁጥር **{num}** መርጠዋል።\n\nአሁን እባክዎ **ሙሉ ስምዎን** ያስገቡ:", parse_mode="Markdown")
    return FULL_NAME

async def receive_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text
    
    # ስልክ ቁጥር ለማግኘት በትእዛዝ መጠየቅ (Contact Share button)
    contact_button = KeyboardButton(text="📱 ስልክ ቁጥር አጋራ", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "አመሰግናለሁ! አሁን እባክዎ ከታች ያለውን ቁልፍ በመጫን **ስልክ ቁጥርዎን** ያጋሩ:",
        reply_markup=reply_markup
    )
    return PHONE_NUMBER

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text

    context.user_data['phone_number'] = phone
    
    await update.message.reply_text(
        "ለክፍያ የሚሆን ማረጋገጫ **Screenshot (ፎቶ)** አሁን ይላኩ።\n\n"
        "(ክፍያውን ፈጽመው የባንክ ደረሰኝ ፎቶ ይላኩ)",
        reply_markup=ReplyKeyboardMarkup([["ሰርዝ / Cancel"]], resize_keyboard=True)
    )
    return PAYMENT_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("እባክዎ የክፍያ ማረጋገጫ **ፎቶ (Screenshot)** ብቻ ይላኩ:")
        return PAYMENT_SCREENSHOT

    photo_file = await update.message.photo[-1].get_file()
    photo_id = photo_file.file_id

    user_id = update.effective_user.id
    full_name = context.user_data.get('full_name')
    phone = context.user_data.get('phone_number')
    selected_num = context.user_data.get('selected_number')

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    
    # ተጠቃሚውን ማስቀመጥ ወይም ማዘመን
    cursor.execute("INSERT OR REPLACE INTO users (user_id, full_name, phone_number) VALUES (?, ?, ?)", 
                   (user_id, full_name, phone))
    
    # ቁጥሩን ወደ PENDING መቀየር
    cursor.execute("UPDATE numbers SET status = 'PENDING', user_id = ? WHERE number = ?", (user_id, selected_num))
    
    # ግብይት መመዝገብ
    cursor.execute("INSERT INTO transactions (user_id, number, screenshot_id, status) VALUES (?, ?, ?, 'PENDING')",
                   (user_id, selected_num, photo_id))
    trans_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "✅ መረጃዎ እና የክፍያ ማረጋገጫዎ በአድሚን ማረጋገጫ ሰንጠረዥ ተመዝግቧል።\n"
        "አድሚኑ ክፍያውን ሲያረጋግጥ ቁጥርዎ በይፋ ይያዛል። እናመሰግናለን!",
        reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True) # ኪቦርድን ማጽዳት
    )

    # ለአድሚን ማሳወቂያ መላክ
    if ADMIN_ID != 0:
        admin_text = (
            f"🔔 **አዲስ የክፍያ ማረጋገጫ ደርሷል!**\n\n"
            f"👤 ስም: {full_name}\n"
            f"📞 ስልክ: {phone}\n"
            f"🔢 የተመረጠ ቁጥር: {selected_num}\n"
            f"🆔 የተጠቃሚ ID: {user_id}"
        )
        keyboard = [
            [
                InlineKeyboardButton("✅ አረጋግጥ (Approve)", callback_data=f"approve_{trans_id}_{user_id}_{selected_num}"),
                InlineKeyboardButton("❌ ውድቅ አድርግ (Reject)", callback_data=f"reject_{trans_id}_{user_id}_{selected_num}")
            ]
        ]
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=admin_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ምዝገባው ተሰርዟል።", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
    return ConversationHandler.END

# --- አድሚን አስተዳደር (Admin Approvals & Number Management) ---

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    action = data[0]
    trans_id = data[1]
    user_id = int(data[2])
    number = int(data[3])

    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()

    if action == "approve":
        cursor.execute("UPDATE numbers SET status = 'BOOKED' WHERE number = ?", (number,))
        cursor.execute("UPDATE transactions SET status = 'APPROVED' WHERE id = ?", (trans_id,))
        conn.commit()
        conn.close()

        await query.edit_message_caption(caption=query.message.caption + "\n\n🟢 **ሁኔታ፡ ፀድቋል (APPROVED)**", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 እንኳን ደስ አሎት! ክፍያዎ ተረጋግጦ ቁጥር **{number}** በስምዎ ተይዟል።"
            )
        except Exception:
            pass

    elif action == "reject":
        cursor.execute("UPDATE numbers SET status = 'AVAILABLE', user_id = NULL WHERE number = ?", (number,))
        cursor.execute("UPDATE transactions SET status = 'REJECTED' WHERE id = ?", (trans_id,))
        conn.commit()
        conn.close()

        await query.edit_message_caption(caption=query.message.caption + "\n\n🔴 **ሁኔታ፡ ውድቅ ተደርጓል (REJECTED)**", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ ይቅርታ! ለቁጥር **{number}** የላኩት ክፍያ ማረጋገጫ አልተቀበለም። እባክዎ እንደገና ይሞክሩ።"
            )
        except Exception:
            pass

# አድሚን ቁጥርን ለመጨመር: /addnum 201
async def admin_add_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("አጠቃቀም: `/addnum <ቁጥር>`", parse_mode="Markdown")
        return
    
    try:
        num = int(context.args[0])
        conn = sqlite3.connect("edu_mezenna.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO numbers (number, status) VALUES (?, 'AVAILABLE')", (num,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ ቁጥር {num} በተሳካ ሁኔታ ተጨምሯል!")
    except Exception as e:
        await update.message.reply_text(f"ስህተት ተፈጥሯል: {e}")

# አድሚን ቁጥርን ለመቀነስ/ለመሰረዝ: /delnum 201
async def admin_del_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("አጠቃቀም: `/delnum <ቁጥር>`", parse_mode="Markdown")
        return
    
    try:
        num = int(context.args[0])
        conn = sqlite3.connect("edu_mezenna.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM numbers WHERE number = ?", (num,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"🗑 ቁጥር {num} ከዝርዝሩ ተወግዷል!")
    except Exception as e:
        await update.message.reply_text(f"ስህተት ተፈጥሯል: {e}")

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("edu_mezenna.db")
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, phone_number FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()

    cursor.execute("SELECT number, status FROM numbers WHERE user_id = ?", (user_id,))
    nums = cursor.fetchall()
    conn.close()

    if not user_row:
        await update.message.reply_text("እርስዎ እስካሁን አልተመዘገቡም። `/register` በመጠቀም መመዝገብ ይችላሉ።")
        return

    name, phone = user_row
    nums_text = ", ".join([f"{n[0]} ({n[1]})" for n in nums]) if nums else "የለዎትም"

    info_msg = (
        f"👤 **የእርስዎ መረጃ:**\n\n"
        f"• ስም: {name}\n"
        f"• ስልክ: {phone}\n"
        f"• የያዟቸው ቁጥሮች: {nums_text}"
    )
    await update.message.reply_text(info_msg, parse_mode="Markdown")

# ----------------- ዋና Main መተግበሪያ -----------------
def main():
    if not TOKEN:
        print("ስህተት: TELEGRAM_BOT_TOKEN በ .env ፋይል ውስጥ አልተገኘም!")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    # ምዝገባ Conversation Handler
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            SELECTING_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_number)],
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_fullname)],
            PHONE_NUMBER: [MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), receive_phone)],
            PAYMENT_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("numbers", show_numbers))
    app.add_handler(CommandHandler("myinfo", my_info))
    
    # አድሚን ትዕዛዞች
    app.add_handler(CommandHandler("addnum", admin_add_number))
    app.add_handler(CommandHandler("delnum", admin_del_number))
    
    app.add_handler(reg_handler)
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(approve|reject)_"))

    print("🤖 Edu Online Mezenna ቦት በስራ ላይ ነው...")
    app.run_polling()

if __name__ == "__main__":
    main()
