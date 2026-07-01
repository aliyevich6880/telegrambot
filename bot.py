import logging
import os
import random
import sqlite3
from dotenv import load_dotenv
from telegram import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.error import Unauthorized
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID')) if os.getenv('OWNER_ID') else None
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

DEFAULT_WORDS = [
    'tova', 'pech', 'temir yol', 'ustoz', 'non pishirgich', 'aytmoq', 'ketmoq',
    'qolmoq', 'bormoq', 'romashka', 'gul', 'choynak', 'piyola', 'kalay', 'noq',
    'ha', 'hop', 'yoq', 'mayli', 'olma', 'nok', 'apelsin', 'malina', 'banan',
    'top', 'issiq', 'sovuq', 'kir', 'toza', 'shirin', 'achiq'
]

DEFAULT_CATEGORIES = [
    'Taom', 'Meva', 'Tabiat', 'So‘zlar', 'Harakat', 'His-tuyg‘u', 'Ustoz', 'Uy', 'Ichimlik'
]

def build_start_keyboard():
    buttons = [
        [InlineKeyboardButton('Boshlovchi bo‘lish', callback_data='host')],
        [InlineKeyboardButton('So‘zni ko‘rish', callback_data='show_word')],
        [InlineKeyboardButton('Keyingi so‘z', callback_data='next_word')],
        [InlineKeyboardButton('Kategoriya tanlash', callback_data='choose_category')],
        [InlineKeyboardButton('Menyu', callback_data='menu')],
    ]
    return InlineKeyboardMarkup(buttons)


def build_category_keyboard():
    buttons = []
    for cat in DEFAULT_CATEGORIES:
        buttons.append([InlineKeyboardButton(cat, callback_data=f'category:{cat}')])
    return InlineKeyboardMarkup(buttons)


def build_word_keyboard():
    buttons = []
    for word in DEFAULT_WORDS[:6]:
        buttons.append([InlineKeyboardButton(word, callback_data=f'word:{word}')])
    buttons.append([InlineKeyboardButton('Yana so‘zlar', callback_data='more_words')])
    return InlineKeyboardMarkup(buttons)


JOIN_BUTTON = '➕ Qo‘shish'
STOP_BUTTON = '⛔ Stop'
PROFILE_BUTTON = '👤 Profil'
BACK_BUTTON = '🔙 Orqaga'
GROUP_MENU_BUTTONS = ['👀 So‘zni ko‘rish', '⏭ Yangi so‘z', '📂 Kategoriya', '📜 Menyu', JOIN_BUTTON, STOP_BUTTON, PROFILE_BUTTON, BACK_BUTTON]


def build_group_keyboard():
    buttons = [
        ['👀 So‘zni ko‘rish', '⏭ Yangi so‘z'],
        ['📂 Kategoriya', '📜 Menyu'],
        [JOIN_BUTTON, STOP_BUTTON],
        [PROFILE_BUTTON, BACK_BUTTON],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)


def build_join_keyboard(bot_username):
    url_group = f'https://t.me/{bot_username}?startgroup=true'
    url_channel = f'https://t.me/{bot_username}?startchannel=true'
    buttons = [
        [InlineKeyboardButton('Guruhga qo‘shish', url=url_group)],
        [InlineKeyboardButton('Kanalga qo‘shish', url=url_channel)],
    ]
    return InlineKeyboardMarkup(buttons)


def get_user_name(user):
    return user.full_name or user.first_name or user.username or str(user.id)


def update_state_player_name(state, user):
    if 'player_names' not in state:
        state['player_names'] = {}
    state['player_names'][user.id] = get_user_name(user)


def format_scoreboard(state):
    scores = state.get('scores', {})
    if not scores:
        return 'Hozircha ballar yo‘q.'
    lines = []
    for user_id, score in sorted(scores.items(), key=lambda x: -x[1]):
        name = state.get('player_names', {}).get(user_id, f'User {user_id}')
        lines.append(f'{name}: {score}')
    return 'Ballar:\n' + '\n'.join(lines)


def is_admin_or_owner(chat, user):
    if OWNER_ID and user.id == OWNER_ID:
        return True
    try:
        member = chat.get_member(user.id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False


def find_hosted_group(user_id):
    for cid, state in games.items():
        if state.get('host_id') == user_id:
            return cid
    return None


def handle_group_button_text(update, context):
    text = (update.message.text or '').strip()
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        return False

    if text == '👀 So‘zni ko‘rish':
        update.message.reply_text(
            "Faqat boshlovchi shaxsiy chatda /setword <so'z> yoki /useword <id> orqali so'z o'rnatishi mumkin.",
            reply_markup=build_group_keyboard()
        )
        return True

    if text == '⏭ Yangi so‘z':
        update.message.reply_text(
            "Yangi so'z uchun boshlovchi shaxsiy chatda /setword yoki /useword dan foydalanishi kerak.",
            reply_markup=build_group_keyboard()
        )
        return True

    if text == '📂 Kategoriya':
        update.message.reply_text(
            "Toifa tanlang:",
            reply_markup=build_category_keyboard()
        )
        return True

    if text == '📜 Menyu':
        update.message.reply_text(
            "Asosiy bot menyusi: Guruhda /host bering, so'ng /category yoki /setword bilan davom eting.",
            reply_markup=build_group_keyboard()
        )
        return True

    if text == JOIN_BUTTON:
        bot_username = context.bot.username or ''
        if bot_username:
            update.message.reply_text(
                "Botni guruhga yoki kanalingizga qo‘shish uchun quyidagi tugmalardan foydalaning:",
                reply_markup=build_join_keyboard(bot_username)
            )
        else:
            update.message.reply_text(
                "Botni guruhga yoki kanalingizga qo‘shish uchun @botusername orqali qidiring va uni qo‘shing."
            )
        return True

    if text == STOP_BUTTON:
        if not is_admin_or_owner(chat, user):
            update.message.reply_text("Faqat adminlar yoki bot egasi o'yinni to'xtatishi mumkin.")
            return True
        if chat.id not in games:
            update.message.reply_text("Raund yo'q.")
            return True
        state = games[chat.id]
        rounds = state.get('rounds', 0)
        update.message.reply_text(
            f"Stop berildi. O'yin tugadi. Jami {rounds} round bo'lib o'tdi.\n{format_scoreboard(state)}"
        )
        games.pop(chat.id, None)
        return True

    if text == PROFILE_BUTTON:
        if chat.id not in games:
            update.message.reply_text("Hozircha o'yin boshlanmagan.")
            return True
        state = games[chat.id]
        host_name = state.get('player_names', {}).get(state.get('host_id'), 'Noma'lum')
        update.message.reply_text(
            f"Profil:\nBoshlovchi: {host_name}\n"
            f"Roundlar: {state.get('rounds', 0)}\n"
            f"{format_scoreboard(state)}",
            reply_markup=build_group_keyboard()
        )
        return True

    if text == BACK_BUTTON:
        update.message.reply_text(
            "Asosiy menyuga qaytildi.",
            reply_markup=build_group_keyboard()
        )
        return True

    return False


def start_private(update, context):
    text = (
        "Salom! Bu So‘z o‘yini botiga xush kelibsiz.\n"
        "Sizga osonroq bo‘lishi uchun pastki tugmalar yordamida o‘ynash mumkin.\n"
        "1) Guruhda /host bering va boshlovchi bo‘ling.\n"
        "2) Kategoriya tanlang yoki o‘zingiz kiritishingiz mumkin.\n"
        "3) Shu tugmalardan foydalanib so‘z tanlang yoki keyingi so‘zga o‘ting.\n"
        "4) Guruhda /reveal yordamida so‘zni tanlangan ishtirokchiga ko‘rsating.\n"
        "5) Botni guruh yoki kanalingizga qo‘shish uchun ➕ Qo‘shish tugmasini bosing.\n"
    )
    update.message.reply_text(text, reply_markup=build_group_keyboard())

def host(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if OWNER_ID and user.id != OWNER_ID:
        update.message.reply_text("Faqat bot egasi boshlovchi bo‘lishi mumkin.")
        return
    if chat.type == 'private':
        update.message.reply_text("Iltimos bu buyruqni guruhda ishlating.")
        return
    games[chat.id] = {
        'host_id': user.id,
        'category': None,
        'word': None,
        'revealed_user_id': None,
        'scores': {},
        'rounds': 0,
        'player_names': {user.id: get_user_name(user)},
        'last_round_result': None,
    }
    update.message.reply_text(
        f"{user.first_name} siz bu guruh uchun boshlovchi bo'ldingiz. Endi toifa tanlang.\n"
        "Bot menyusi pastda paydo bo‘ladi.",
        reply_markup=build_group_keyboard()
    )

def category(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos guruhda /category <nom> yoki tugmachadan foydalaning.")
        return
    if chat.id not in games or games[chat.id].get('host_id') != user.id:
        update.message.reply_text("Faqat boshlovchi toifani o'zgartirishi mumkin. Avval /host bosing.")
        return
    if len(context.args) == 0:
        update.message.reply_text("Iltimos toifa nomini yozing: /category film|hayvon|mashina ...")
        return
    cat = ' '.join(context.args)
    games[chat.id]['category'] = cat
    update.message.reply_text(
        f"Toifa '{cat}' deb o'rnatildi. Endi boshlovchi shaxsiy chatda /setword <so'z> yuborsin.",
        reply_markup=build_category_keyboard()
    )

def setword(update, context):
    # must be in private chat and user must be host of some group
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != 'private':
        update.message.reply_text("Iltimos bu buyruqni shaxsiy chatda yuboring: /setword <so'z>")
        return
    # find the group where this user is host
    target_chat_id = None
    for cid, state in games.items():
        if state.get('host_id') == user.id:
            target_chat_id = cid
            break
    if not target_chat_id:
        update.message.reply_text("Siz hozir hech qanday guruhda boshlovchi emassiz. Avval guruhda /host bering yoki avval o'yinlarda g'olib bo'ling.")
        return
    if len(context.args) == 0:
        word = random.choice(DEFAULT_WORDS)
        update.message.reply_text(
            f"Bazadan tasodifiy so'z tanlandi: {word}.\nEndi guruhda maqsadli foydalanuvchiga /reveal bilan yuboring.",
            reply_markup=build_word_keyboard()
        )
    else:
        word = ' '.join(context.args).strip()
    games[target_chat_id]['word'] = word
    games[target_chat_id]['revealed_user_id'] = None
    update.message.reply_text(
        f"So'z o'rnatildi va guruh ({target_chat_id}) uchun tayyor. Guruhda maqsadli foydalanuvchiga /reveal bilan so'zni ko'rsating.",
        reply_markup=build_word_keyboard()
    )

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
    if OWNER_ID and user.id != OWNER_ID:
        update.message.reply_text("Faqat bot egasi so'z qo'shishi mumkin.")
        return
    if chat.type == 'private':
        update.message.reply_text("Iltimos guruhda /addword <so'z> yoki guruhga yuborilgan tugmalardan foydalaning.")
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
    if OWNER_ID and user.id != OWNER_ID:
        update.message.reply_text("Faqat bot egasi saqlangan so'zlarni ko'rishi mumkin.")
        return
    if chat.type == 'private':
        update.message.reply_text("Iltimos guruhda /listwords buyrug'ini bering.")
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
    if OWNER_ID and user.id != OWNER_ID:
        update.message.reply_text("Faqat bot egasi so'zni o'chirishi mumkin.")
        return
    if chat.type == 'private':
        update.message.reply_text("Iltimos guruhda /removeword <id> qiling.")
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
    state = games[chat.id]
    if state.get('host_id') != user.id and not is_admin_or_owner(chat, user):
        update.message.reply_text("Faqat boshlovchi yoki admin bu raundni bekor qilishi mumkin.")
        return
    rounds = state.get('rounds', 0)
    games.pop(chat.id, None)
    update.message.reply_text(
        f"Raund bekor qilindi. Jami {rounds} round bo'lib o'tdi.\n{format_scoreboard(state)}"
    )


def button_handler(update, context):
    query = update.callback_query
    data = query.data
    query.answer()
    user = query.from_user

    if data == 'host':
        query.message.reply_text("Guruhda /host bering va boshlovchi bo'ling.", reply_markup=build_group_keyboard())
        return
    if data == 'show_word':
        query.message.reply_text(
            "So'zni ko'rish uchun shaxsiy chatda /setword <so'z> yoki /useword <id> botiga yozing.",
            reply_markup=build_group_keyboard()
        )
        return
    if data == 'next_word':
        next_word = random.choice(DEFAULT_WORDS)
        query.message.reply_text(
            f"Yangi so'z: {next_word}\nEndi shaxsiyda /setword {next_word} bering.",
            reply_markup=build_group_keyboard()
        )
        return
    if data == 'choose_category':
        query.message.reply_text("Kategoriya tanlash uchun quyidagilardan birini bering:", reply_markup=build_category_keyboard())
        return
    if data.startswith('category:'):
        cat = data.split(':', 1)[1]
        query.message.reply_text(
            f"Siz tanladingiz: {cat}. Guruhda /category {cat} bering yoki boshqacha toifa yozing."
        )
        return
    if data.startswith('word:'):
        word = data.split(':', 1)[1]
        query.message.reply_text(
            f"Siz tanladingiz: {word}. Endi shaxsiyda /setword {word} yuboring."
        )
        return
    if data == 'more_words':
        extra = DEFAULT_WORDS[6:12]
        buttons = [[InlineKeyboardButton(w, callback_data=f'word:{w}')] for w in extra]
        query.message.reply_text("Qo'shimcha so'zlar:", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if data == 'menu':
        query.message.reply_text(
            "Asosiy menyu:",
            reply_markup=build_group_keyboard()
        )
        return


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
    if text in GROUP_MENU_BUTTONS:
        return
    # If the revealer accidentally sends the word, ignore their guesses
    if state.get('revealed_user_id') and user.id == state.get('revealed_user_id'):
        return
    if text.lower() == state['word'].lower():
        winner_name = get_user_name(user)
        update_state_player_name(state, user)
        state.setdefault('scores', {})
        state['scores'][user.id] = state['scores'].get(user.id, 0) + 1
        state['rounds'] = state.get('rounds', 0) + 1
        state['last_round_result'] = f"Round {state['rounds']} tugadi. G'olib: {winner_name} (+1 ball)."
        state['previous_winner'] = user.id
        state['host_id'] = user.id
        state['word'] = None
        state['revealed_user_id'] = None
        update.message.reply_text(
            f"{state['last_round_result']}\nKeyingi round uchun boshlovchi {winner_name} bo'ldi. /setword yordamida yangi so'z o'rnating.\n{format_scoreboard(state)}",
            reply_markup=build_group_keyboard()
        )
        return

def help_cmd(update, context):
    update.message.reply_text(
        "Buyruqlar: /host - boshlovchi bo'ling; /category <nom> - toifa;\n"
        "/addword <so'z> - so'z qo'shish; /listwords - so'zlarni ko'rish;\n"
        "/removeword <id> - so'z o'chirish; /setword <so'z> - maxfiy so'z o'rnatish;\n"
        "/useword <id> - saqlangan so'zni tanlash (boshlovchi uchun);\n"
        "/reveal - javobga yuborilgan xabarga so'zni ko'rsatish; /cancel - raundni bekor qilish;\n"
        "/profile - o'yinchilar ballari va roundlar haqida ma'lumot."
    )

def profile_cmd(update, context):
    chat = update.effective_chat
    if chat.type == 'private':
        update.message.reply_text("/profile faqat guruhda ishlaydi.")
        return
    if chat.id not in games:
        update.message.reply_text("Hozircha o'yin boshlanmagan.")
        return
    state = games[chat.id]
    host_name = state.get('player_names', {}).get(state.get('host_id'), 'Noma'lum')
    update.message.reply_text(
        f"Profil:\nBoshlovchi: {host_name}\n"
        f"Roundlar: {state.get('rounds', 0)}\n"
        f"{format_scoreboard(state)}"
    )


def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start_private))
    dp.add_handler(CommandHandler('host', host))
    dp.add_handler(CommandHandler('category', category, pass_args=True))
    dp.add_handler(CommandHandler('setword', setword, pass_args=True))
    dp.add_handler(CommandHandler('useword', useword, pass_args=True))
    dp.add_handler(CommandHandler('reveal', reveal))
    dp.add_handler(CommandHandler('cancel', cancel))
    dp.add_handler(CommandHandler('profile', profile_cmd))
    dp.add_handler(CommandHandler('help', help_cmd))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_group_button_text))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_group_message))

    init_db()
    print("Bot ishga tushmoqda...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
