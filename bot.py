import logging
import asyncio
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import google.generativeai as genai
from database import Session, User, Chat, Code, Setting
from datetime import datetime
import config

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=config.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

bot_application = None
bot_thread = None
bot_running = False

def get_setting(key, default=''):
    session = Session()
    s = session.query(Setting).filter_by(key=key).first()
    session.close()
    return s.value if s else default

def get_or_create_user(telegram_user):
    session = Session()
    db_user = session.query(User).filter_by(telegram_id=telegram_user.id).first()
    if not db_user:
        db_user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            first_seen=datetime.utcnow(),
            last_active=datetime.utcnow()
        )
        session.add(db_user)
    else:
        db_user.last_active = datetime.utcnow()
    session.commit()
    session.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_setting('bot_active', 'true') != 'true':
        await update.message.reply_text('البوت متوقف مؤقتاً.')
        return
    user = update.effective_user
    get_or_create_user(user)
    welcome_message = get_setting('welcome_message', 'مرحباً بك! 🤖')
    keyboard = [
        [InlineKeyboardButton("💬 محادثة", callback_data='chat'),
         InlineKeyboardButton("👨‍💻 كود", callback_data='code')],
        [InlineKeyboardButton("📚 المساعدة", callback_data='help')]
    ]
    await update.message.reply_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'help':
        await query.edit_message_text("📚 *الأوامر:*\n/start - البداية\n/code [لغة] [وصف] - توليد كود\n/help - مساعدة\n\nأو أرسل أي رسالة للمحادثة!", parse_mode='Markdown')
    elif query.data == 'code':
        await query.edit_message_text("لتوليد كود استخدم:\n`/code Python برنامج حاسبة`", parse_mode='Markdown')
    elif query.data == 'chat':
        await query.edit_message_text("أرسل أي سؤال وسأرد عليك فوراً! 💬")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_setting('bot_active', 'true') != 'true':
        await update.message.reply_text('البوت متوقف مؤقتاً.')
        return
    user_message = update.message.text
    user = update.effective_user
    get_or_create_user(user)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        response = model.generate_content(user_message)
        bot_response = response.text
    except Exception as e:
        bot_response = "عذراً، حدث خطأ. حاول مرة أخرى."
        logger.error(f"Gemini error: {e}")
    session = Session()
    db_user = session.query(User).filter_by(telegram_id=user.id).first()
    if db_user:
        chat = Chat(user_id=db_user.id, telegram_id=user.id, message=user_message, response=bot_response, type='text', timestamp=datetime.utcnow())
        session.add(chat)
        db_user.chats_count += 1
        session.commit()
    session.close()
    await update.message.reply_text(bot_response)

async def generate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parts = text.split(' ', 2)
    if len(parts) < 3:
        await update.message.reply_text("الاستخدام:\n`/code Python برنامج حاسبة`", parse_mode='Markdown')
        return
    language = parts[1]
    description = parts[2]
    user = update.effective_user
    get_or_create_user(user)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    await update.message.reply_text(f"⚙️ جاري توليد كود {language}...")
    try:
        prompt = f"اكتب كود {language} كامل لـ: {description}. أضف تعليقات بالعربية."
        response = model.generate_content(prompt)
        code = response.text
    except Exception as e:
        await update.message.reply_text("عذراً، حدث خطأ أثناء توليد الكود.")
        return
    session = Session()
    db_user = session.query(User).filter_by(telegram_id=user.id).first()
    if db_user:
        db_code = Code(user_id=db_user.id, telegram_id=user.id, language=language, description=description, code=code, timestamp=datetime.utcnow())
        session.add(db_code)
        db_user.codes_count += 1
        chat = Chat(user_id=db_user.id, telegram_id=user.id, message=f"/code {language} {description}", response=code, type='code', timestamp=datetime.utcnow())
        session.add(chat)
        session.commit()
    session.close()
    await update.message.reply_text(f"✅ *كود {language}:*\n\n{code[:4000]}", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 *المساعدة*\n\n/start - البداية\n/code [لغة] [وصف] - توليد كود\n/help - هذه الرسالة\n\nمثال: `/code Python حاسبة`", parse_mode='Markdown')

def run_bot():
    global bot_application, bot_running
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application = Application.builder().token(config.BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('code', generate_code))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_application = application
    bot_running = True
    loop.run_until_complete(application.run_polling(drop_pending_updates=True))

def start_bot():
    global bot_thread, bot_running
    if bot_running:
        return False
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    return True

def stop_bot():
    global bot_running
    bot_running = False
    return True
