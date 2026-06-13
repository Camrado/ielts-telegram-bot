import logging

from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.database import close_pool, create_pool, init_db
from bot.handlers.grammar import (
    build_grammar_add_topic_conversation_handler,
    build_grammar_quiz_conversation_handler,
    grammar_menu_callback,
    grammar_stats_callback,
    learn_nav_callback,
    learn_topic_selected,
    learn_topics_callback,
    quiz_by_topic_callback,
    quiz_menu_callback,
)
from bot.handlers.start import (
    help_command,
    main_menu_callback,
    reminders_command,
    reminders_toggle_callback,
    start_command,
    stats_command,
)
from bot.handlers.flashcards import build_flashcard_conversation_handler
from bot.handlers.vocab import (
    build_vocab_conversation_handler,
    vocab_menu_callback,
    vocab_stats_callback,
)
from bot.seed_grammar import seed as seed_grammar
from bot.services.reminders import setup_scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await create_pool()
    await init_db()
    await seed_grammar()
    setup_scheduler(application.bot)
    await application.bot.set_my_commands([
        BotCommand("start", "Open main menu"),
        BotCommand("help", "How to use this bot"),
        BotCommand("stats", "Quick stats overview"),
        BotCommand("review", "Start flashcard review"),
        BotCommand("reminders", "Toggle daily reminders"),
        BotCommand("cancel", "Cancel current action"),
    ])
    logger.info("Bot initialized — database ready, scheduler started")


async def post_shutdown(application: Application) -> None:
    await close_pool()
    logger.info("Bot shut down — database pool closed")


async def error_handler(update: object, context) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong. Please try again later."
            )
        except Exception:
            pass


async def cancel_global(update: Update, context) -> None:
    for key in list(context.user_data.keys()):
        if key in ("fc_session", "gq_session", "grammar_learn", "gat_pending",
                    "pending_word", "pending_provided", "pending_entry",
                    "is_update", "existing_word_id", "bulk_entries",
                    "bulk_kept", "review_index", "bulk_skipped_count"):
            context.user_data.pop(key, None)

    from bot.handlers.menu_utils import delete_old_menu, track_menu
    from bot.handlers.start import MAIN_MENU_KEYBOARD
    await delete_old_menu(context, update.effective_chat.id)
    msg = await update.message.reply_text(
        "❌ Cancelled. Choose a section:",
        reply_markup=MAIN_MENU_KEYBOARD,
        parse_mode="HTML",
    )
    await track_menu(context, msg)


def main() -> None:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(10.0)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("reminders", reminders_command))

    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(vocab_menu_callback, pattern="^menu_vocab$"))
    app.add_handler(CallbackQueryHandler(grammar_menu_callback, pattern="^menu_grammar$"))

    app.add_handler(CallbackQueryHandler(learn_topics_callback, pattern="^grammar_learn$"))
    app.add_handler(CallbackQueryHandler(learn_topic_selected, pattern=r"^glearn_topic_\d+$"))
    app.add_handler(CallbackQueryHandler(learn_nav_callback, pattern=r"^glearn_(prev|next)$"))

    app.add_handler(CallbackQueryHandler(quiz_menu_callback, pattern="^grammar_quiz$"))
    app.add_handler(CallbackQueryHandler(quiz_by_topic_callback, pattern="^gquiz_by_topic$"))

    app.add_handler(CallbackQueryHandler(vocab_stats_callback, pattern="^vocab_stats$"))
    app.add_handler(CallbackQueryHandler(grammar_stats_callback, pattern="^grammar_stats$"))

    app.add_handler(CallbackQueryHandler(reminders_toggle_callback, pattern=r"^reminders_(on|off)$"))

    app.add_handler(build_vocab_conversation_handler())
    app.add_handler(build_flashcard_conversation_handler())
    app.add_handler(build_grammar_quiz_conversation_handler())
    app.add_handler(build_grammar_add_topic_conversation_handler())

    app.add_handler(CommandHandler("cancel", cancel_global))

    app.add_error_handler(error_handler)

    logger.info("Starting bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
