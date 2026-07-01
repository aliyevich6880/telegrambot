import logging

from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

import database
import handlers
from config import TOKEN, OWNER_ID

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


PUBLIC_COMMANDS = [
    BotCommand('start', "Botni ishga tushirish"),
    BotCommand('game', "Guruhda yangi o'yin boshlash"),
    BotCommand('score', "Joriy reytingni ko'rish"),
    BotCommand('stop', "O'yinni to'xtatish"),
    BotCommand('help', "Yordam"),
]

OWNER_ONLY_COMMANDS = [
    BotCommand('settings', "Sozlamalar: so'z/kategoriya qo'shish menyusi"),
    BotCommand('addcategory', "Yangi kategoriya qo'shish"),
    BotCommand('addword', "So'z qo'shish"),
    BotCommand('listwords', "Saqlangan so'zlarni ko'rish"),
    BotCommand('removeword', "So'zni o'chirish"),
]


def setup_bot_commands(bot):
    """Registers the '/' command menu: everyone sees the public commands,
    the owner additionally sees the word-bank management commands."""
    bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
    if OWNER_ID:
        try:
            bot.set_my_commands(
                PUBLIC_COMMANDS + OWNER_ONLY_COMMANDS,
                scope=BotCommandScopeChat(chat_id=OWNER_ID)
            )
        except Exception as e:
            # This fails harmlessly if the owner hasn't started a private chat with the bot yet.
            logger.warning("Owner uchun buyruqlar ro'yxatini o'rnatib bo'lmadi: %s", e)


def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # commands
    dp.add_handler(CommandHandler('start', handlers.start_private))
    dp.add_handler(CommandHandler('help', handlers.help_cmd))
    dp.add_handler(CommandHandler('game', handlers.cmd_game))
    dp.add_handler(CommandHandler('score', handlers.cmd_score))
    dp.add_handler(CommandHandler('stop', handlers.cmd_stop))
    dp.add_handler(CommandHandler('addcategory', handlers.cmd_addcategory, pass_args=True))
    dp.add_handler(CommandHandler('addword', handlers.cmd_addword, pass_args=True))
    dp.add_handler(CommandHandler('listwords', handlers.cmd_listwords))
    dp.add_handler(CommandHandler('removeword', handlers.cmd_removeword, pass_args=True))
    dp.add_handler(CommandHandler('settings', handlers.cmd_settings))

    # inline button callbacks
    dp.add_handler(CallbackQueryHandler(handlers.cb_claim_host, pattern='^claim_host$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_choose_category, pattern='^choose_category$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_set_category, pattern='^setcat:'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_host_panel, pattern='^host_panel$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_show_word, pattern='^show_word$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_next_word, pattern='^next_word$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_score, pattern='^score$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_stop, pattern='^stop$'))

    # /settings menu callbacks (owner only)
    dp.add_handler(CallbackQueryHandler(handlers.cb_settings_menu, pattern='^settings_menu$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_aw_start, pattern='^aw_start$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_aw_choose_group, pattern='^awgroup:'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_aw_choose_category, pattern='^awcat:'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_ac_start, pattern='^ac_start$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_lw_start, pattern='^lw_start$'))
    dp.add_handler(CallbackQueryHandler(handlers.cb_lw_choose_group, pattern='^lwgroup:'))

    # word guessing in group chats
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handlers.handle_group_text), group=0)
    # /settings add-word / add-category text capture (private chat only)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handlers.handle_private_text), group=1)

    database.init_db()
    setup_bot_commands(updater.bot)
    print("Bot ishga tushmoqda...")
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()