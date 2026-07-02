import logging

import database
from config import OWNER_ID
from game import manager
from keyboards import (
    claim_host_keyboard,
    category_keyboard,
    host_panel_keyboard,
    join_keyboard,
    settings_menu_keyboard,
    group_select_keyboard,
)

logger = logging.getLogger(__name__)

# Per-owner conversation state for the /settings "add word" / "add category" flows.
# PENDING_ADDWORD[user_id] = {'chat_id': int, 'category': str}  (category set once chosen)
# PENDING_ADDCATEGORY[user_id] = True
PENDING_ADDWORD = {}
PENDING_ADDCATEGORY = {}


# ---------- helpers ----------

def is_admin_or_owner(chat, user):
    if OWNER_ID and user.id == OWNER_ID:
        return True
    try:
        member = chat.get_member(user.id)
        return member.status in ('administrator', 'creator')
    except Exception:
        return False


def is_owner(user):
    return bool(OWNER_ID) and user.id == OWNER_ID


def host_panel_text(game):
    cat = game.category or 'tanlanmagan'
    return f"📂 Kategoriya: {cat}\n👀 So'zni ko'rish tugmasini bosing."


def active_group_titles(context):
    """Returns [(chat_id, title), ...] for every chat currently tracked in manager.games."""
    groups = []
    for chat_id in manager.games.keys():
        try:
            title = context.bot.get_chat(chat_id).title or str(chat_id)
        except Exception:
            title = str(chat_id)
        groups.append((chat_id, title))
    return groups


# ---------- private chat ----------

def start_private(update, context):
    text = (
        "Salom! Bu So‘z o‘yini botiga xush kelibsiz.\n\n"
        "Qanday o‘ynaladi:\n"
        "1) Guruhda /game buyrug‘ini bering.\n"
        "2) Birinchi bo‘lib \"🎤 Boshlovchi bo‘lish\" tugmasini bosgan kishi boshlovchi bo‘ladi.\n"
        "3) Boshlovchi kategoriya tanlaydi, so‘ng \"👀 So‘zni ko‘rish\" tugmasini bosadi — so‘z faqat "
        "unga popup ko‘rinishida chiqadi, hech kim boshqasi ko‘rmaydi.\n"
        "4) Boshlovchi so‘zni guruhda og‘zaki tushuntiradi. Kim to‘g‘ri topsa — ball oladi va keyingi "
        "boshlovchi o‘sha bo‘ladi.\n"
        "5) /score — reyting, /stop — o‘yinni tugatish.\n\n"
        "Botni guruh yoki kanalingizga qo‘shish uchun ➕ tugmasidan foydalaning."
    )
    bot_username = context.bot.username or ''
    markup = join_keyboard(bot_username) if bot_username else None
    update.message.reply_text(text, reply_markup=markup)


def help_cmd(update, context):
    update.message.reply_text(
        "Buyruqlar:\n"
        "/game - guruhda o'yin boshlash\n"
        "/score - joriy reytingni ko'rish\n"
        "/stop - o'yinni to'xtatish (boshlovchi yoki admin)\n\n"
        "Bot egasi uchun (shaxsiy chatda):\n"
        "/settings - so'z/kategoriya qo'shish menyusi\n"
        "/addcategory <nom> - yangi toifa qo'shish\n"
        "/addword <kategoriya> <so'z> - so'z qo'shish\n"
        "/listwords - guruh uchun saqlangan so'zlarni ko'rish (guruhda ishlatiladi)\n"
        "/removeword <id> - so'zni o'chirish"
    )


def cmd_settings(update, context):
    user = update.effective_user
    chat = update.effective_chat
    if not is_owner(user):
        update.message.reply_text("Faqat bot egasi sozlamalarga kira oladi.")
        return
    if chat.type != 'private':
        update.message.reply_text("Iltimos /settings buyrug'ini botga shaxsiy chatda yuboring.")
        return
    update.message.reply_text("⚙️ Sozlamalar:", reply_markup=settings_menu_keyboard())


def cb_settings_menu(update, context):
    query = update.callback_query
    user = query.from_user
    if not is_owner(user):
        query.answer("Faqat bot egasi sozlamalarga kira oladi.", show_alert=True)
        return
    query.answer()
    query.edit_message_text("⚙️ Sozlamalar:", reply_markup=settings_menu_keyboard())


def cb_aw_start(update, context):
    query = update.callback_query
    user = query.from_user
    if not is_owner(user):
        query.answer("Faqat bot egasi so'z qo'shishi mumkin.", show_alert=True)
        return

    PENDING_ADDWORD[user.id] = {}
    query.answer()
    categories = database.get_categories()
    query.edit_message_text(
        "📂 Qaysi kategoriyaga so'z qo'shamiz?",
        reply_markup=category_keyboard(categories, callback_prefix='awcat:', back_target='settings_menu')
    )


def cb_aw_choose_category(update, context):
    query = update.callback_query
    user = query.from_user
    if not is_owner(user):
        query.answer("Faqat bot egasi so'z qo'shishi mumkin.", show_alert=True)
        return
    pending = PENDING_ADDWORD.get(user.id)
    if not pending:
        query.answer("Sessiya tugagan. /settings dan qaytadan boshlang.", show_alert=True)
        return
    category = query.data.split(':', 1)[1]
    pending['category'] = category
    query.answer(f"Kategoriya: {category}")
    query.edit_message_text(
        f"📂 Kategoriya: {category}\n✍️ Endi qo'shmoqchi bo'lgan so'zni oddiy xabar qilib yozing:"
    )


def cb_ac_start(update, context):
    query = update.callback_query
    user = query.from_user
    if not is_owner(user):
        query.answer("Faqat bot egasi kategoriya qo'shishi mumkin.", show_alert=True)
        return
    PENDING_ADDCATEGORY[user.id] = True
    query.answer()
    query.edit_message_text("✍️ Yangi kategoriya nomini oddiy xabar qilib yozing:")


def cb_lw_start(update, context):
    query = update.callback_query
    user = query.from_user
    if not is_owner(user):
        query.answer("Faqat bot egasi so'zlarni ko'ra oladi.", show_alert=True)
        return

    query.answer()
    _show_word_list(query)


def _show_word_list(query):
    rows = database.list_words()
    if not rows:
        text = "Hozircha hech qanday so'z qo'shilmagan."
    else:
        lines = [f"{r[0]} [{r[1] or 'NoCategory'}]: {r[2]}" for r in rows]
        text = "So'zlar ro'yxati:\n" + "\n".join(lines)
    query.edit_message_text(text[:4000], reply_markup=settings_menu_keyboard())


def handle_private_text(update, context):
    """Captures the follow-up text message for the /settings add-word / add-category flow."""
    chat = update.effective_chat
    user = update.effective_user
    if chat.type != 'private':
        return

    text = (update.message.text or '').strip()
    if not text:
        return

    if user.id in PENDING_ADDWORD:
        pending = PENDING_ADDWORD[user.id]
        category = pending.get('category')
        if not category:
            return  # still waiting on category button
        wid = database.add_word(text, user.id, category)
        PENDING_ADDWORD.pop(user.id, None)
        update.message.reply_text(
            f"✅ So'z qo'shildi (id={wid}), kategoriya: {category}.",
            reply_markup=settings_menu_keyboard()
        )
        return

    if user.id in PENDING_ADDCATEGORY:
        PENDING_ADDCATEGORY.pop(user.id, None)
        if database.add_category(text):
            update.message.reply_text(f"✅ Yangi toifa qo'shildi: {text}", reply_markup=settings_menu_keyboard())
        else:
            update.message.reply_text("Bu toifa allaqachon mavjud.", reply_markup=settings_menu_keyboard())
        return


# ---------- /game flow ----------

def cmd_game(update, context):
    chat = update.effective_chat
    if chat.type == 'private':
        update.message.reply_text("Iltimos bu buyruqni guruhda ishlating.")
        return

    if manager.exists(chat.id):
        game = manager.get(chat.id)
        if game.host_id:
            host_name = game.get_name(game.host_id)
            update.message.reply_text(f"O'yin allaqachon davom etmoqda. Boshlovchi: {host_name}")
        else:
            update.message.reply_text(
                "O'yin boshlanish jarayonida. Boshlovchi bo'lish uchun tugmani bosing:",
                reply_markup=claim_host_keyboard()
            )
        return

    manager.create(chat.id)
    update.message.reply_text(
        "🎮 O'yin boshlandi! Kim boshlovchi bo'lishni xohlaydi?",
        reply_markup=claim_host_keyboard()
    )


def cb_claim_host(update, context):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user
    game = manager.get(chat.id)

    if not game:
        query.answer("O'yin topilmadi. /game bilan qaytadan boshlang.", show_alert=True)
        return
    if game.host_id is not None:
        query.answer("Boshlovchi allaqachon tanlangan.", show_alert=True)
        return
    if game.pending_winner_id is not None and user.id != game.pending_winner_id:
        query.answer("❌ Faqat so'zni topgan o'yinchi boshlovchi bo'la oladi.", show_alert=True)
        return

    game.host_id = user.id
    game.pending_winner_id = None
    name = game.remember_player(user)
    query.answer(f"✅ {name} boshlovchi bo'ldi!")

    if not game.category_chosen_once:
        categories = database.get_categories()
        query.edit_message_text(
            f"✅ {name} boshlovchi bo'ldi.\n📂 Kategoriya tanlang:",
            reply_markup=category_keyboard(categories, show_back=False)
        )
    else:
        query.edit_message_text(
            f"✅ {name} boshlovchi bo'ldi.\n{host_panel_text(game)}",
            reply_markup=host_panel_keyboard()
        )


def cb_choose_category(update, context):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user
    game = manager.get(chat.id)

    if not game or game.host_id != user.id:
        query.answer("Faqat boshlovchi kategoriya tanlashi mumkin.", show_alert=True)
        return

    query.answer()
    categories = database.get_categories()
    query.edit_message_text("📂 Kategoriya tanlang:", reply_markup=category_keyboard(categories))


def cb_set_category(update, context):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user
    game = manager.get(chat.id)

    if not game or game.host_id != user.id:
        query.answer("Faqat boshlovchi kategoriya tanlashi mumkin.", show_alert=True)
        return

    cat = query.data.split(':', 1)[1]
    game.category = cat
    game.category_chosen_once = True
    game.used_words.clear()
    game.word = None
    query.answer(f"Kategoriya: {cat}")
    query.edit_message_text(f"✅ Kategoriya o'rnatildi.\n{host_panel_text(game)}", reply_markup=host_panel_keyboard())


def cb_host_panel(update, context):
    query = update.callback_query
    chat = query.message.chat
    game = manager.get(chat.id)
    if not game:
        query.answer()
        return
    query.answer()
    query.edit_message_text(host_panel_text(game), reply_markup=host_panel_keyboard())


def cb_show_word(update, context):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user
    game = manager.get(chat.id)

    if not game or game.host_id != user.id:
        query.answer("Faqat boshlovchi so'zni ko'rishi mumkin.", show_alert=True)
        return

    if not game.word:
        word, _source = database.pick_random_word(game.category, game.used_words)
        game.word = word

    query.answer(f"🤫 So'z: {game.word}\n\nBuni guruhga yozmang!", show_alert=True)


def cb_next_word(update, context):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user
    game = manager.get(chat.id)

    if not game or game.host_id != user.id:
        query.answer("Faqat boshlovchi yangi so'z so'rashi mumkin.", show_alert=True)
        return

    word, _source = database.pick_random_word(game.category, game.used_words)
    game.word = word
    query.answer(f"🤫 Yangi so'z: {word}\n\nBuni guruhga yozmang!", show_alert=True)


def cb_score(update, context):
    query = update.callback_query
    chat = query.message.chat
    game = manager.get(chat.id)
    if not game:
        query.answer("O'yin mavjud emas.", show_alert=True)
        return
    query.answer(game.scoreboard_text()[:190], show_alert=True)


def cb_stop(update, context):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user
    game = manager.get(chat.id)

    if not game:
        query.answer()
        return
    if not (user.id == game.host_id or is_admin_or_owner(chat, user)):
        query.answer("Faqat boshlovchi yoki admin o'yinni to'xtata oladi.", show_alert=True)
        return

    manager.end(chat.id)
    query.answer("O'yin to'xtatildi.")
    query.edit_message_text(
        f"⛔ O'yin tugadi.\nJami {game.rounds} round o'tdi.\n{game.scoreboard_text()}"
    )


# ---------- text commands mirroring the inline actions ----------

def cmd_score(update, context):
    chat = update.effective_chat
    if chat.type == 'private':
        update.message.reply_text("/score faqat guruhda ishlaydi.")
        return
    game = manager.get(chat.id)
    if not game:
        update.message.reply_text("Hozircha o'yin boshlanmagan.")
        return
    update.message.reply_text(game.scoreboard_text())


def cmd_stop(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        update.message.reply_text("/stop faqat guruhda ishlaydi.")
        return
    game = manager.get(chat.id)
    if not game:
        update.message.reply_text("O'yin mavjud emas.")
        return
    if not (user.id == game.host_id or is_admin_or_owner(chat, user)):
        update.message.reply_text("Faqat boshlovchi yoki admin o'yinni to'xtata oladi.")
        return
    manager.end(chat.id)
    update.message.reply_text(
        f"⛔ O'yin tugadi.\nJami {game.rounds} round o'tdi.\n{game.scoreboard_text()}"
    )


# ---------- guessing ----------

def handle_group_text(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == 'private':
        return

    game = manager.get(chat.id)
    if not game or not game.word:
        return

    text = (update.message.text or '').strip()
    if not text:
        return

    # Ignore anything the host types — including the word itself.
    if user.id == game.host_id:
        return

    if text.lower() == game.word.lower():
        winner_name = game.remember_player(user)
        game.scores[user.id] = game.scores.get(user.id, 0) + 1
        game.rounds += 1
        game.word = None
        game.host_id = None
        game.pending_winner_id = user.id

        update.message.reply_text(
            f"🎉 {winner_name} so'zni topdi!\n\n{game.scoreboard_text()}\n\n"
            f"Endi {winner_name} boshlovchi bo'lish uchun tugmani bosishi kerak 👇",
            reply_to_message_id=update.message.message_id,
            reply_markup=claim_host_keyboard()
        )


# ---------- word bank management (owner only) ----------

def cmd_addcategory(update, context):
    user = update.effective_user
    chat = update.effective_chat
    if not is_owner(user):
        update.message.reply_text("Faqat bot egasi yangi kategoriya qo'shishi mumkin.")
        return
    if chat.type != 'private':
        update.message.reply_text("Iltimos shaxsiy chatda /addcategory <nom> yuboring.")
        return
    if not context.args:
        update.message.reply_text("Iltimos kategoriya nomini yozing: /addcategory <nom>")
        return
    cat = ' '.join(context.args).strip()
    if database.add_category(cat):
        update.message.reply_text(f"Yangi toifa qo'shildi: {cat}")
    else:
        update.message.reply_text("Bu toifa allaqachon mavjud.")


def cmd_addword(update, context):
    user = update.effective_user
    chat = update.effective_chat
    if not is_owner(user):
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
    categories = database.get_categories()
    if category not in categories:
        update.message.reply_text(
            "Bunday toifa yo'q. Iltimos mavjud kategoriyalardan birini tanlang: " + ", ".join(categories)
        )
        return
    wid = database.add_word(word, user.id, category)
    update.message.reply_text(f"So'z qo'shildi (id={wid}) kategoriya: {category}.")


def cmd_listwords(update, context):
    user = update.effective_user
    if not is_owner(user):
        update.message.reply_text("Faqat bot egasi saqlangan so'zlarni ko'rishi mumkin.")
        return
    rows = database.list_words()
    if not rows:
        update.message.reply_text("Hech qanday so'z qo'shilmagan.")
        return
    lines = [f"{r[0]} [{r[1] or 'NoCategory'}]: {r[2]}" for r in rows]
    update.message.reply_text("\n".join(lines)[:4000])


def cmd_removeword(update, context):
    user = update.effective_user
    if not is_owner(user):
        update.message.reply_text("Faqat bot egasi so'zni o'chirishi mumkin.")
        return
    if not context.args:
        update.message.reply_text("Iltimos id ni ko'rsating: /removeword <id>")
        return
    try:
        wid = int(context.args[0])
    except ValueError:
        update.message.reply_text("Id butun son bo'lishi kerak.")
        return
    if database.remove_word(wid):
        update.message.reply_text("So'z o'chirildi.")
    else:
        update.message.reply_text("Bunday id topilmadi.")