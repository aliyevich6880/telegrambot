from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def claim_host_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎤 Boshlovchi bo'lish", callback_data='claim_host')]
    ])


def category_keyboard(categories, callback_prefix='setcat:', show_back=True, back_target='host_panel'):
    buttons = [[InlineKeyboardButton(cat, callback_data=f'{callback_prefix}{cat}')] for cat in categories]
    if show_back:
        buttons.append([InlineKeyboardButton('🔙 Orqaga', callback_data=back_target)])
    return InlineKeyboardMarkup(buttons)


def host_panel_keyboard():
    buttons = [
        [InlineKeyboardButton("👀 So'zni ko'rish", callback_data='show_word')],
        [InlineKeyboardButton("⏭ Keyingi so'z", callback_data='next_word')],
        [InlineKeyboardButton("📂 Kategoriya", callback_data='choose_category')],
        [
            InlineKeyboardButton("🏆 Reyting", callback_data='score'),
            InlineKeyboardButton("⛔ Stop", callback_data='stop'),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def join_keyboard(bot_username):
    url_group = f'https://t.me/{bot_username}?startgroup=true'
    url_channel = f'https://t.me/{bot_username}?startchannel=true'
    buttons = [
        [InlineKeyboardButton('Guruhga qo‘shish', url=url_group)],
        [InlineKeyboardButton('Kanalga qo‘shish', url=url_channel)],
    ]
    return InlineKeyboardMarkup(buttons)


def settings_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("➕ Yangi so'z qo'shish", callback_data='aw_start')],
        [InlineKeyboardButton("📂 Yangi kategoriya qo'shish", callback_data='ac_start')],
        [InlineKeyboardButton("📋 So'zlarni ko'rish", callback_data='lw_start')],
    ]
    return InlineKeyboardMarkup(buttons)


def group_select_keyboard(groups, callback_prefix):
    """groups: list of (chat_id, title) tuples."""
    buttons = [
        [InlineKeyboardButton(title, callback_data=f'{callback_prefix}{chat_id}')]
        for chat_id, title in groups
    ]
    buttons.append([InlineKeyboardButton('🔙 Orqaga', callback_data='settings_menu')])
    return InlineKeyboardMarkup(buttons)