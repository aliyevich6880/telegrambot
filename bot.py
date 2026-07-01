import logging
import os
import sqlite3
from dotenv import load_dotenv
from telegram import ParseMode
from telegram.error import Unauthorized
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    print("Iltimos .env faylga BOT_TOKEN ni qo'ying (BOT_TOKEN=YOUR_TOKEN)")
    exit(1)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory game states per group chat id
games = {}
# structure: games[chat_id] = {
#   'host_id': int,
#   'category': str or None,
#   'word': str or None,
#   'revealed_user_id': int or None,
# }

def start_private(update, context):
    # Private chat instructions
    text = (
        "Salom! Bu So'z o'yini botidir.\n"
        "Guruhda /host buyrug'ini bosing va boshlovchi bo'ling.\n"
        "Boshlovchi guruhda /category <nom> bilan toifa tanlaydi, keyin shaxsiy suhbatda /setword <so'z> yuboradi.\n"
        "Guruhda boshlovchi bir foydalanuvchining xabariga javob qilib /reveal buyrug'ini yuboradi — bot maxfiy so'zni shu foydalanuvchiga shaxsiy xabarda yuboradi.\n"
        "Kim guruhda to'g'ri so'zni topsa, bot e'lon qiladi va raund tugaydi.\n"
    )
    update.message.reply_text(text)

def host(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos bu buyruqni guruhda ishlating.")
        return
    games[chat.id] = {'host_id': user.id, 'category': None, 'word': None, 'revealed_user_id': None}
    update.message.reply_text(f"{user.first_name} siz bu guruh uchun boshlovchi bo'ldingiz. Endi /category bilan toifa tanlang.")

def category(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos toifani guruhda belgilang: /category <nom>")
        return
    if chat.id not in games or games[chat.id].get('host_id') != user.id:
        update.message.reply_text("Faqat boshlovchi toifani o'zgartirishi mumkin. Avval /host bosing.")
        return
    if len(context.args) == 0:
        update.message.reply_text("Iltimos toifa nomini yozing: /category film|hayvon|mashina ...")
        return
    cat = ' '.join(context.args)
    games[chat.id]['category'] = cat
    update.message.reply_text(f"Toifa '{cat}' deb o'rnatildi. Endi boshlovchi shaxsiy chatda /setword <so'z> yuborsin.")

def setword(update, context):
    # must be in private chat and user must be host of some group
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != 'private':
        update.message.reply_text("Iltimos bu buyruqni shaxsiy chatda yuboring: /setword <so'z>")
        return
    # If args provided, use that word. Otherwise try to pick a random stored word for the host's group.
    if len(context.args) == 0:
        # try to choose random word from DB for this host's group
        conn = sqlite3.connect('words.db')
        c = conn.cursor()
        c.execute("SELECT id, word FROM words WHERE chat_id = ? ORDER BY RANDOM() LIMIT 1", (target_chat_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            update.message.reply_text("Hech qanday saqlangan so'z topilmadi. Iltimos shaxsiyda /setword <so'z> yuboring yoki guruhda /addword bilan qo'shing.")
            return
        wid, word = row[0], row[1]
        update.message.reply_text(f"Bazadan so'z tanlandi (id={wid}). Endi guruhda maqsadli foydalanuvchiga /reveal bilan yuboring.")
    else:
        word = ' '.join(context.args).strip()
    # find the group where this user is host and which doesn't have an active word
    target_chat_id = None
    for cid, state in games.items():
        if state.get('host_id') == user.id:
            target_chat_id = cid
            break
    if not target_chat_id:
        update.message.reply_text("Siz hozir hech qanday guruhda boshlovchi emassiz. Guruhda /host buyrug'ini bosing.")
        return
    games[target_chat_id]['word'] = word
    games[target_chat_id]['revealed_user_id'] = None
    update.message.reply_text(f"So'z o'rnatildi va guruh ({target_chat_id}) uchun tayyor. Guruhda maqsadli foydalanuvchiga /reveal bilan so'zni ko'rsating.")

def init_db():
    conn = sqlite3.connect('words.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        word TEXT,
        added_by INTEGER
    )''')
    conn.commit()
    conn.close()

def addword(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos guruhda /addword <so'z> bilan qo'shing.")
        return
    if chat.id not in games or games[chat.id].get('host_id') != user.id:
        update.message.reply_text("Faqat boshlovchi so'z qo'shishi mumkin. Avval /host bosing.")
        return
    if not context.args:
        update.message.reply_text("Iltimos so'zni yozing: /addword <so'z>")
        return
    word = ' '.join(context.args).strip()
    conn = sqlite3.connect('words.db')
    c = conn.cursor()
    c.execute("INSERT INTO words (chat_id, word, added_by) VALUES (?, ?, ?)", (chat.id, word, user.id))
    conn.commit()
    wid = c.lastrowid
    conn.close()
    update.message.reply_text(f"So'z qo'shildi (id={wid}).")

def listwords(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos guruhda /listwords buyrug'ini bering.")
        return
    if chat.id not in games or games[chat.id].get('host_id') != user.id:
        update.message.reply_text("Faqat boshlovchi ro'yxatni ko'ra oladi.")
        return
    conn = sqlite3.connect('words.db')
    c = conn.cursor()
    c.execute("SELECT id, word, added_by FROM words WHERE chat_id = ?", (chat.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        update.message.reply_text("Hech qanday so'z qo'shilmagan.")
        return
    lines = [f"{r[0]}: {r[1]}" for r in rows]
    update.message.reply_text("\n".join(lines))

def removeword(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos guruhda /removeword <id> qiling.")
        return
    if chat.id not in games or games[chat.id].get('host_id') != user.id:
        update.message.reply_text("Faqat boshlovchi o'chirishi mumkin.")
        return
    if not context.args:
        update.message.reply_text("Iltimos id ni ko'rsating: /removeword <id>")
        return
    try:
        wid = int(context.args[0])
    except:
        update.message.reply_text("Id butun son bo'lishi kerak.")
        return
    conn = sqlite3.connect('words.db')
    c = conn.cursor()
    c.execute("DELETE FROM words WHERE id = ? AND chat_id = ?", (wid, chat.id))
    if c.rowcount == 0:
        update.message.reply_text("Bunday id topilmadi.")
    else:
        update.message.reply_text("So'z o'chirildi.")
    conn.commit()
    conn.close()

def useword(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != 'private':
        update.message.reply_text("Iltimos shaxsiyda /useword <id> bilan so'zni tanlang.")
        return
    if not context.args:
        update.message.reply_text("Iltimos so'z id sini bering: /useword <id> — bu siz host bo‘lgan guruh uchun ishlaydi.")
        return
    try:
        wid = int(context.args[0])
    except:
        update.message.reply_text("Id butun son bo'lishi kerak.")
        return
    # find the group where this user is host
    target_chat_id = None
    for cid, state in games.items():
        if state.get('host_id') == user.id:
            target_chat_id = cid
            break
    if not target_chat_id:
        update.message.reply_text("Siz hech qanday guruhda boshlovchi emassiz.")
        return
    conn = sqlite3.connect('words.db')
    c = conn.cursor()
    c.execute("SELECT word FROM words WHERE id = ? AND chat_id = ?", (wid, target_chat_id))
    row = c.fetchone()
    conn.close()
    if not row:
        update.message.reply_text("Bunday so'z topilmadi o'zingiz qo'shgan guruh ro'yxatida.")
        return
    word = row[0]
    games[target_chat_id]['word'] = word
    games[target_chat_id]['revealed_user_id'] = None
    update.message.reply_text(f"So'z (id={wid}) guruhga o'rnatildi. Guruhda /reveal bilan maqsadli foydalanuvchiga yuboring.")

def reveal(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos bu buyruqni guruhda, maqsadli foydalanuvchining xabariga javoban yuboring: javobga /reveal")
        return
    if chat.id not in games:
        update.message.reply_text("Bu guruhda raund boshlanmagan. Avval /host bosing va /setword yuboring.")
        return
    state = games[chat.id]
    if state.get('host_id') != user.id:
        update.message.reply_text("Faqat boshlovchi bu buyruqni bajarishi mumkin.")
        return
    if not state.get('word'):
        update.message.reply_text("So'z hali o'rnatilmagan. Boshlovchi shaxsiy chatda /setword <so'z> yuborishi kerak.")
        return
    if state.get('revealed_user_id'):
        update.message.reply_text("Allaqachon bir foydalanuvchiga so'z ko'rsatilgan. Raundni bekor qilish uchun /cancel bering.")
        return
    # We expect /reveal as a reply to the target user's message
    if not update.message.reply_to_message:
        update.message.reply_text("Iltimos, maqsadli foydalanuvchining xabariga javoban /reveal bering.")
        return
    target_user = update.message.reply_to_message.from_user
    try:
        context.bot.send_message(chat_id=target_user.id, text=(f"Sizga maxfiy so'z: *{state['word']}*\n"
                                                              "Iltimos bu so'zni guruhga yozmang — faqat tushuntirib bering."), parse_mode=ParseMode.MARKDOWN)
    except Unauthorized:
        update.message.reply_text(f"Foydalanuvchiga shaxsiy xabar yuborib bo'lmadi. Iltimos @{target_user.username} botni shaxsiyda ishga tushirsin.")
        return
    state['revealed_user_id'] = target_user.id
    update.message.reply_text(f"So'z @{target_user.username} ga yuborildi. Endi u tushuntiradi va boshqalar taxmin qiladi.")

def cancel(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos bu buyruqni guruhda yuboring.")
        return
    if chat.id not in games:
        update.message.reply_text("Raund mavjud emas.")
        return
    if games[chat.id].get('host_id') != user.id:
        update.message.reply_text("Faqat boshlovchi raundni bekor qilishi mumkin.")
        return
    games.pop(chat.id, None)
    update.message.reply_text("Raund bekor qilindi va o'yin holati tozalandi.")

def handle_group_message(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        return
    if chat.id not in games:
        return
    state = games[chat.id]
    if not state.get('word'):
        return
    text = (update.message.text or '').strip()
    if not text:
        return
    # If the revealer accidentally sends the word, ignore their guesses
    if state.get('revealed_user_id') and user.id == state.get('revealed_user_id'):
        return
    if text.lower() == state['word'].lower():
        update.message.reply_text(f"Tabriklaymiz {user.first_name}! Siz so'zni topdingiz: {state['word']}")
        # clear the game state for this chat
        games.pop(chat.id, None)

def help_cmd(update, context):
    update.message.reply_text("Buyruqlar: /host - boshlovchi bo'ling; /category <nom> - toifa; shaxsiyda /setword <so'z>; guruhda javobga /reveal; /cancel - bekor qilish")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start_private))
    dp.add_handler(CommandHandler('host', host))
    dp.add_handler(CommandHandler('category', category, pass_args=True))
    dp.add_handler(CommandHandler('setword', setword, pass_args=True))
    dp.add_handler(CommandHandler('reveal', reveal))
    dp.add_handler(CommandHandler('cancel', cancel))
    dp.add_handler(CommandHandler('help', help_cmd))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_group_message))

    print("Bot ishga tushmoqda...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
