import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.models.user import get_or_create_user

logger = logging.getLogger(__name__)

GRAMMAR_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📖 Learn", callback_data="grammar_learn")],
    [InlineKeyboardButton("🎯 Quiz", callback_data="grammar_quiz")],
    [InlineKeyboardButton("➕ Add Topic", callback_data="grammar_add_topic")],
    [InlineKeyboardButton("📊 Stats", callback_data="grammar_stats")],
    [InlineKeyboardButton("◀️ Back", callback_data="back_main")],
])

COMING_SOON = "🚧 Coming soon — this feature will be available in the next update\\."


async def _ensure_user(update: Update) -> int:
    user = update.effective_user
    return await get_or_create_user(user.id, user.first_name, user.username)


async def grammar_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await query.edit_message_text(
        "📖 *Grammar*\nChoose an option:",
        reply_markup=GRAMMAR_MENU_KEYBOARD,
        parse_mode="MarkdownV2",
    )


async def grammar_stub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await query.edit_message_text(
        COMING_SOON,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back", callback_data="menu_grammar")],
        ]),
        parse_mode="MarkdownV2",
    )
