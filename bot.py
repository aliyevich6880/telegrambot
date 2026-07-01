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
#   'scores': dict,
#   'rounds': int,
#   'player_names': dict,
# }
pending_hosts = {}

DEFAULT_WORDS = [
    'tova', 'pech', 'temir yol', 'ustoz', 'non pishirgich', 'aytmoq', 'ketmoq',
    'qolmoq', 'bormoq', 'romashka', 'gul', 'choynak', 'piyola', 'kalay', 'noq',
    'ha', 'hop', 'yoq', 'mayli', 'olma', 'nok', 'apelsin', 'malina', 'banan',
    'top', 'issiq', 'sovuq', 'kir', 'toza', 'shirin', 'achiq'
]

DEFAULT_CATEGORIES = [
    'Taom', 'Meva', 'Tabiat', 'So‘zlar', 'Harakat', 'His-tuyg‘u', 'Ustoz', 'Uy', 'Ichimlik'
]
CATEGORIES = DEFAULT_CATEGORIES.copy()

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
    for cat in CATEGORIES:
        buttons.append([InlineKeyboardButton(cat, callback_data=f'category:{cat}')])
    buttons.append([InlineKeyboardButton('🔙 Orqaga', callback_data='back_main')])
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
HOST_BUTTON = '� Boshlovchi bo‘lishni xohlayman!'
HOST_LABEL_PREFIX = '👤 Boshlovchi:'
GROUP_MENU_BUTTONS = [HOST_BUTTON, '👀 So‘zni ko‘rish', '⏭ Yangi so‘z', '📂 Kategoriya', '📜 Menyu', JOIN_BUTTON, STOP_BUTTON, PROFILE_BUTTON, BACK_BUTTON]


def build_group_keyboard(state=None):
    if state and state.get('host_id'):
        buttons = [
            ['👀 So‘zni ko‘rish', '⏭ Yangi so‘z'],
            ['📂 Kategoriya', '📜 Menyu'],
            [JOIN_BUTTON, STOP_BUTTON],
            [PROFILE_BUTTON],
        ]
    else:
        buttons = [
            [HOST_BUTTON],
            [JOIN_BUTTON],
        ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)


def build_menu_keyboard():
    buttons = [[BACK_BUTTON]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)


def build_profile_keyboard():
    buttons = [[BACK_BUTTON]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)


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

    if text == HOST_BUTTON or text.startswith(HOST_LABEL_PREFIX):
        if chat.id in games:
            if games[chat.id].get('host_id') == user.id:
                update.message.reply_text(
                    "Siz allaqachon boshlovchisiz. So'zni ko'rish yoki yangi so'z tanlang.",
                    reply_markup=build_group_keyboard(games[chat.id])
                )
            else:
                current_host = get_user_name(context.bot.get_chat_member(chat.id, games[chat.id]['host_id']).user) if games[chat.id].get('host_id') else "Noma'lum"
                update.message.reply_text(
                    f"O'yin allaqachon boshlagan. Hozirgi boshlovchi: {current_host}.",
                    reply_markup=build_group_keyboard(games[chat.id])
                )
            return True
        pending_hosts[chat.id] = user.id
        update.message.reply_text(
            f"{user.first_name} siz boshlovchi bo'lish uchun ariza berdingiz. Endi /game buyrug'ini bering.",
            reply_markup=build_group_keyboard()
        )
        return True

    if chat.id not in games:
        if chat.id in pending_hosts:
            update.message.reply_text("O'yin hali boshlanmagan. Avvalo /game buyrug'ini bering.")
        else:
            update.message.reply_text("Avvalo /host bering va boshlovchi bo'ling, so'ng /game buyrug'ini bering.")
        return True

    state = games[chat.id]

    if text == '👀 So‘zni ko‘rish':
        if state.get('host_id') != user.id:
            update.message.reply_text(
                "So'zni faqat boshlovchi ko'rishi mumkin.",
                reply_markup=build_group_keyboard(games[chat.id])
            )
            return True
        if not state.get('word'):
            category = state.get('category')
            word, source = choose_random_word(chat.id, category)
            if not word:
                word = random.choice(DEFAULT_WORDS)
                source = 'Bazadan'
            state['word'] = word
            state['revealed_user_id'] = None
            state['category'] = category
            private_text = f"{source} tasodifiy so'z tanlandi: *{state['word']}*\nIltimos, uni guruhga yozmang."
        else:
            private_text = f"Sizga maxfiy so'z: *{state['word']}*\nIltimos, uni guruhga yozmang."
        try:
            context.bot.send_message(chat_id=user.id, text=private_text, parse_mode=ParseMode.MARKDOWN)
        except Unauthorized:
            update.message.reply_text(
                "So'zni shaxsiyda yuborib bo'lmadi. Iltimos botga shaxsiyda /start yozing.",
                reply_markup=build_group_keyboard(games[chat.id])
            )
            return True
        state['revealed_user_id'] = user.id
        update.message.reply_text(
            "So'z sizga shaxsiyda yuborildi. Endi boshqa foydalanuvchilar taxmin qilsin.",
            reply_markup=build_group_keyboard(games[chat.id])
        )
        return True

    if text == '⏭ Yangi so‘z':
        if state.get('host_id') != user.id:
            update.message.reply_text(
                "Yangi so'zni faqat boshlovchi so'rashi mumkin.",
                reply_markup=build_group_keyboard(games[chat.id])
            )
            return True
        category = state.get('category')
        word, source = choose_random_word(chat.id, category)
        if not word:
            word = random.choice(DEFAULT_WORDS)
            source = 'Bazadan'
        state['word'] = word
        state['revealed_user_id'] = None
        try:
            context.bot.send_message(chat_id=user.id, text=f"{source} yangi so'z: *{word}*\nIltimos, uni guruhga yozmang.", parse_mode=ParseMode.MARKDOWN)
        except Unauthorized:
            update.message.reply_text(
                "So'zni shaxsiyda yuborib bo'lmadi. Iltimos botga shaxsiyda /start yozing.",
                reply_markup=build_group_keyboard(games[chat.id])
            )
            return True
        state['revealed_user_id'] = user.id
        update.message.reply_text(
            "Yangi so'z hostga shaxsiyda yuborildi. Endi boshqa foydalanuvchilar taxmin qilsin.",
            reply_markup=build_group_keyboard(games[chat.id])
        )
        return True

    if text == '📂 Kategoriya':
        if state.get('host_id') != user.id:
            update.message.reply_text(
                "Faqat boshlovchi toifani tanlashi mumkin.",
                reply_markup=build_group_keyboard()
            )
            return True
        update.message.reply_text(
            "Toifa tanlang:",
            reply_markup=build_category_keyboard()
        )
        return True

    if text == '📜 Menyu':
        update.message.reply_text(
            "Menyu ochildi. Orqaga qaytish uchun tugmani bosing.",
            reply_markup=build_menu_keyboard()
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
            if chat.id in pending_hosts:
                update.message.reply_text("O'yin hali boshlanmagan. Avvalo /game buyrug'ini bering.")
            else:
                update.message.reply_text("Hozircha o'yin boshlanmagan.")
            return True
        host_name = state.get('player_names', {}).get(state.get('host_id'), 'Noma\'lum')
        update.message.reply_text(
            f"Profil:\nBoshlovchi: {host_name}\n"
            f"Roundlar: {state.get('rounds', 0)}\n"
            f"{format_scoreboard(state)}",
            reply_markup=build_profile_keyboard()
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
        "1) Guruhda /host bering va boshlovchi bo‘lib oling, so‘ng /game buyrug‘ini bering.\n"
        "2) Kategoriya tanlang yoki o‘zingiz kiritishingiz mumkin.\n"
        "3) Shu tugmalardan foydalanib so‘z tanlang yoki keyingi so‘zga o‘ting.\n"
        "4) Guruhda /reveal yordamida so‘zni tanlangan ishtirokchiga ko‘rsating.\n"
        "5) Botni guruh yoki kanalingizga qo‘shish uchun ➕ Qo‘shish tugmasini bosing.\n"
    )
    update.message.reply_text(text, reply_markup=build_group_keyboard())

def host(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos bu buyruqni guruhda ishlating.")
        return
    pending_hosts[chat.id] = user.id
    update.message.reply_text(
        f"{user.first_name} siz guruh uchun boshlovchi bo'lishni xohlaysiz.\n"
        "O'yinni boshlash uchun /game buyrug'ini bering.",
        reply_markup=build_group_keyboard()
    )


def game(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos bu buyruqni guruhda ishlating.")
        return
    if chat.id in games:
        current_host = get_user_name(context.bot.get_chat_member(chat.id, games[chat.id]['host_id']).user) if games[chat.id].get('host_id') else "Noma'lum"
        update.message.reply_text(
            f"O'yin allaqachon boshlandi. Boshlovchi: {current_host}. /setword bilan so'zni o'rnating yoki /reveal bilan so'zni yuboring.",
            reply_markup=build_group_keyboard()
        )
        return
    if chat.id not in pending_hosts:
        update.message.reply_text(
            "Avvalo /host bering va boshlovchi bo'ling, so'ng /game buyrug'ini bering.",
            reply_markup=build_group_keyboard()
        )
        return
    if pending_hosts[chat.id] != user.id:
        update.message.reply_text(
            "Siz guruhdagi boshlovchi emassiz. Avvalo /host bering va boshlovchi bo'ling.",
            reply_markup=build_group_keyboard()
        )
        return

    games[chat.id] = {
        'host_id': user.id,
        'category': None,
        'word': None,
        'revealed_user_id': None,
        'scores': {},
        'rounds': 0,
        'player_names': {},
    }
    update_state_player_name(games[chat.id], user)
    pending_hosts.pop(chat.id, None)
    update.message.reply_text(
        f"{user.first_name} endi o'yin boshlandi. Toifa tanlang yoki /setword <so'z> yuborishni kuting.",
        reply_markup=build_group_keyboard()
    )

def category(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("Iltimos guruhda toifa tanlang: /category <nom> yoki tugmachadan foydalaning.")
        return
    if chat.id not in games or games[chat.id].get('host_id') != user.id:
        if chat.id in pending_hosts:
            update.message.reply_text("Avvalo /game buyrug'ini bering va o'yinni boshlang.")
        else:
            update.message.reply_text("Faqat boshlovchi toifani tanlashi mumkin. Avval /host bosing.")
        return
    if len(context.args) == 0:
        update.message.reply_text("Iltimos mavjud toifalardan tanlang: " + ", ".join(CATEGORIES))
        return
    cat = ' '.join(context.args)
    if cat not in CATEGORIES:
        update.message.reply_text(
            "Bunday toifa mavjud emas. Iltimos mavjud toifalardan tanlang."
        )
        return
    games[chat.id]['category'] = cat
    update.message.reply_text(
        f"Toifa '{cat}' deb o'rnatildi. Endi bot egasi shaxsiy chatda /setword <so'z> yuborsin.",
        reply_markup=build_group_keyboard()
    )

def choose_random_word(chat_id, category=None):
    conn = sqlite3.connect('words.db')
    c = conn.cursor()
    if category:
        c.execute("SELECT word FROM words WHERE chat_id = ? AND category = ?", (chat_id, category))
        rows = c.fetchall()
        if rows:
            word = random.choice([r[0] for r in rows])
            conn.close()
            return word, f"Toifadan ({category})"
    c.execute("SELECT word FROM words WHERE chat_id = ?", (chat_id,))
    rows = c.fetchall()
    conn.close()
    if rows:
        return random.choice([r[0] for r in rows]), 'Saqlangan so‘zlardan'
    return None, None


def setword(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != 'private':
        update.message.reply_text("Iltimos bu buyruqni shaxsiy chatda yuboring: /setword <so'z>")
        return
    if OWNER_ID and user.id != OWNER_ID:
        update.message.reply_text("Faqat bot egasi so'z o'rnatishi mumkin.")
        return
    if not games:
        update.message.reply_text("Hozir hech qanday guruhda o'yin boshlanmagan. Avvalo /host bering va /game buyrug'ini bering.")
        return
    target_chat_id = None
    if len(games) == 1:
        target_chat_id = next(iter(games))
    elif len(context.args) > 1 and context.args[0].isdigit():
        target_chat_id = int(context.args[0])
        context.args = context.args[1:]
        if target_chat_id not in games:
            update.message.reply_text("Noma'lum guruh. Iltimos to'g'ri chat_id ko'rsating.")
            return
    else:
        update.message.reply_text("Agar bir nechta guruhda o'yin bo'lsa, iltimos /setword <chat_id> <so'z> yozing.")
        return
    if len(context.args) == 0:
        category = games[target_chat_id].get('category')
        word, source = choose_random_word(target_chat_id, category)
        if not word:
            word = random.choice(DEFAULT_WORDS)
            source = 'Bazadan'
        update.message.reply_text(
            f"{source} tasodifiy so'z tanlandi: {word}.\nEndi host shaxsiy chatda /sozni_ko'rish tugmasini ishlatishi mumkin.",
            reply_markup=build_word_keyboard()
        )
    else:
        word = ' '.join(context.args).strip()
    games[target_chat_id]['word'] = word
    games[target_chat_id]['revealed_user_id'] = None
    update.message.reply_text(
        f"So'z guruh ({target_chat_id}) uchun o'rnatildi. Host shaxsiyda ✅ So'zni ko'rish tugmasini bosing.",
        reply_markup=build_word_keyboard()
    )

def init_db():
    conn = sqlite3.connect('words.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        word TEXT,
        added_by INTEGER,
        category TEXT
    )''')
    c.execute("PRAGMA table_info(words)")
    columns = [row[1] for row in c.fetchall()]
    if 'category' not in columns:
        c.execute("ALTER TABLE words ADD COLUMN category TEXT")
    conn.commit()
    conn.close()

def addword(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if OWNER_ID and user.id != OWNER_ID:
        update.message.reply_text("Faqat bot egasi so'z qo'shishi mumkin.")
        return
    if chat.type != 'private':
        update.message.reply_text("Iltimos shaxsiy chatda /addword <kategoriya> <so'z> yuboring.")
        return
    if len(context.args) < 2:
        update.message.reply_text("Iltimos to'g'ri yozing: /addword <kategoriya> <so'z>")
        return
    category = context.args[0]
    word = ' '.join(context.args[1:]).strip()
    if category not in CATEGORIES:
        update.message.reply_text("Bunday toifa yo'q. Iltimos mavjud kategoriyalardan birini tanlang: " + ", ".join(CATEGORIES))
        return
    conn = sqlite3.connect('words.db')
    c = conn.cursor()
    c.execute("INSERT INTO words (chat_id, word, added_by, category) VALUES (?, ?, ?, ?)", (chat.id, word, user.id, category))
    conn.commit()
    wid = c.lastrowid
    conn.close()
    update.message.reply_text(f"So'z qo'shildi (id={wid}) kategoriya: {category}.")


def addcategory(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if OWNER_ID and user.id != OWNER_ID:
        update.message.reply_text("Faqat bot egasi yangi kategoriya qo'shishi mumkin.")
        return
    if chat.type != 'private':
        update.message.reply_text("Iltimos shaxsiy chatda /addcategory <nom> yuboring.")
        return
    if not context.args:
        update.message.reply_text("Iltimos kategoriya nomini yozing: /addcategory <nom>")
        return
    cat = ' '.join(context.args).strip()
    if cat in CATEGORIES:
        update.message.reply_text("Bu toifa allaqachon mavjud.")
        return
    CATEGORIES.append(cat)
    update.message.reply_text(f"Yangi toifa qo'shildi: {cat}")

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
    c.execute("SELECT id, category, word, added_by FROM words WHERE chat_id = ?", (chat.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        update.message.reply_text("Hech qanday so'z qo'shilmagan.")
        return
    lines = [f"{r[0]} [{r[1] or 'NoCategory'}]: {r[2]}" for r in rows]
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
    if OWNER_ID and user.id != OWNER_ID:
        update.message.reply_text("Faqat bot egasi saqlangan so'zni tanlashi mumkin.")
        return
    if chat.type != 'private':
        update.message.reply_text("Iltimos shaxsiyda /useword <id> bilan so'zni tanlang.")
        return
    if not context.args:
        update.message.reply_text("Iltimos so'z id sini bering: /useword <id> — bu siz owner bo'lib ko'rsatilgan guruh uchun ishlaydi.")
        return
    target_chat_id = None
    if len(games) == 1:
        target_chat_id = next(iter(games))
    elif len(context.args) > 1 and context.args[0].isdigit():
        target_chat_id = int(context.args[0])
        context.args = context.args[1:]
        if target_chat_id not in games:
            update.message.reply_text("Noma'lum guruh. Iltimos to'g'ri chat_id ko'rsating.")
            return
    else:
        update.message.reply_text("Agar bir nechta guruhda o'yin bo'lsa, iltimos /useword <chat_id> <id> yozing.")
        return
    try:
        wid = int(context.args[0])
    except:
        update.message.reply_text("Id butun son bo'lishi kerak.")
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
        update.message.reply_text("Iltimos bu buyruqni guruhda yuboring.")
        return
    if chat.id not in games:
        if chat.id in pending_hosts:
            update.message.reply_text("Bu guruhda o'yin hali boshlanmagan. Avvalo /game buyrug'ini bering.")
        else:
            update.message.reply_text("Bu guruhda raund boshlanmagan. Avval /host bosing va owner so'zni shaxsiyda yuborsin.")
        return
    state = games[chat.id]
    if state.get('host_id') != user.id:
        update.message.reply_text("Faqat boshlovchi bu buyruqni bajarishi mumkin.")
        return
    if not state.get('word'):
        update.message.reply_text("So'z hali o'rnatilmagan. Owner shaxsiy chatda /setword <so'z> yuborishi kerak.")
        return
    if state.get('revealed_user_id') == user.id:
        update.message.reply_text("Sizga so'z allaqachon yuborilgan.")
        return
    try:
        context.bot.send_message(chat_id=user.id, text=(f"Sizga maxfiy so'z: *{state['word']}*\n"
                                                         "Iltimos bu so'zni guruhga yozmang — faqat tushuntirib bering."), parse_mode=ParseMode.MARKDOWN)
    except Unauthorized:
        update.message.reply_text("Sizga shaxsiy xabar yuborib bo'lmadi. Iltimos botga shaxsiyda /start yozing.")
        return
    state['revealed_user_id'] = user.id
    update.message.reply_text("So'z sizga shaxsiyda yuborildi. Endi boshqa foydalanuvchilar taxmin qilsin.")

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
        saved_word = get_random_saved_word(query.message.chat.id)
        next_word = saved_word or random.choice(DEFAULT_WORDS)
        source = 'Saqlangan so‘zlardan' if saved_word else 'Bazadan'
        query.message.reply_text(
            f"{source} yangi so'z: {next_word}\nEndi shaxsiyda /setword {next_word} bering.",
            reply_markup=build_group_keyboard()
        )
        return
    if data == 'choose_category':
        query.message.reply_text("Kategoriya tanlash uchun quyidagilardan birini bering:", reply_markup=build_category_keyboard())
        return
    if data.startswith('category:'):
        cat = data.split(':', 1)[1]
        chat = query.message.chat
        state = games.get(chat.id)
        if not state or state.get('host_id') != query.from_user.id:
            query.message.reply_text(
                "Faqat boshlovchi kategoriya tanlashi mumkin.",
                reply_markup=build_group_keyboard()
            )
            return
        if cat not in CATEGORIES:
            query.message.reply_text(
                "Bunday toifa mavjud emas.",
                reply_markup=build_group_keyboard()
            )
            return
        state['category'] = cat
        query.message.reply_text(
            f"Toifa '{cat}' tanlandi. Endi owner shaxsiy chatda /setword <so'z> yuborsin.",
            reply_markup=build_group_keyboard()
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
    if data == 'back_main':
        query.message.reply_text(
            "Asosiy menyuga qaytildi.",
            reply_markup=build_group_keyboard()
        )
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
            f"TOPDZ! {winner_name} so'zni topdi.\n{state['last_round_result']}\nKeyingi round uchun boshlovchi {winner_name} bo'ldi. /setword yordamida yangi so'z o'rnating.\n{format_scoreboard(state)}",
            reply_to_message_id=update.message.message_id,
            reply_markup=build_group_keyboard(games[chat.id])
        )
        return

def help_cmd(update, context):
    update.message.reply_text(
        "Buyruqlar: /host - boshlovchi bo'ling; /category <nom> - toifa;\n"
        "/addcategory <nom> - yangi toifa qo'shish (faqat bot egasi); /addword <so'z> - so'z qo'shish; /listwords - so'zlarni ko'rish;\n"
        "/removeword <id> - so'z o'chirish; /setword <so'z> - maxfiy so'z o'rnatish;\n"
        "/useword <id> - saqlangan so'zni tanlash (faqat bot egasi);\n"
        "/reveal - javobga yuborilgan xabarga so'zni ko'rsatish; /cancel - raundni bekor qilish;\n"
        "/profile - o'yinchilar ballari va roundlar haqida ma'lumot;\n"
        "/game - guruh o'yinini boshlash uchun /host bilan bir xil."
    )

def profile_cmd(update, context):
    chat = update.effective_chat
    if chat.type == 'private':
        update.message.reply_text("/profile faqat guruhda ishlaydi.")
        return
    if chat.id not in games:
        if chat.id in pending_hosts:
            update.message.reply_text("O'yin hali boshlanmagan. Avvalo /game buyrug'ini bering.")
        else:
            update.message.reply_text("Hozircha o'yin boshlanmagan.")
        return
    state = games[chat.id]
    host_name = state.get('player_names', {}).get(state.get('host_id'), "Noma'lum")
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
    dp.add_handler(CommandHandler('game', game))
    dp.add_handler(CommandHandler('category', category, pass_args=True))
    dp.add_handler(CommandHandler('setword', setword, pass_args=True))
    dp.add_handler(CommandHandler('useword', useword, pass_args=True))
    dp.add_handler(CommandHandler('addword', addword, pass_args=True))
    dp.add_handler(CommandHandler('addcategory', addcategory, pass_args=True))
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
