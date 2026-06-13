import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from bot.config import TELEGRAM_BOT_TOKEN
from bot.database import close_pool, create_pool, init_db
from bot.handlers.grammar import grammar_menu_callback, grammar_stub_callback
from bot.handlers.start import help_command, main_menu_callback, start_command
from bot.handlers.vocab import (
    build_vocab_conversation_handler,
    vocab_menu_callback,
    vocab_stub_callback,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await create_pool()
    await init_db()
    logger.info("Bot initialized — database ready")


async def post_shutdown(application: Application) -> None:
    await close_pool()
    logger.info("Bot shut down — database pool closed")


async def error_handler(update: object, context) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Something went wrong. Please try again later."
        )


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

    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(vocab_menu_callback, pattern="^menu_vocab$"))
    app.add_handler(CallbackQueryHandler(grammar_menu_callback, pattern="^menu_grammar$"))

    app.add_handler(build_vocab_conversation_handler())

    app.add_handler(CallbackQueryHandler(vocab_stub_callback, pattern="^vocab_"))
    app.add_handler(CallbackQueryHandler(grammar_stub_callback, pattern="^grammar_"))

    app.add_error_handler(error_handler)

    logger.info("Starting bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
