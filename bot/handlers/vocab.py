import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.models.user import get_or_create_user

logger = logging.getLogger(__name__)

VOCAB_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔁 Flashcards", callback_data="vocab_flashcards")],
    [InlineKeyboardButton("🎯 Quiz", callback_data="vocab_quiz")],
    [InlineKeyboardButton("➕ Add Word", callback_data="vocab_add")],
    [InlineKeyboardButton("📋 Bulk Add", callback_data="vocab_bulk_add")],
    [InlineKeyboardButton("📊 Stats", callback_data="vocab_stats")],
    [InlineKeyboardButton("◀️ Back", callback_data="back_main")],
])

COMING_SOON = "🚧 Coming soon — this feature will be available in the next update\\."


async def _ensure_user(update: Update) -> int:
    user = update.effective_user
    return await get_or_create_user(user.id, user.first_name, user.username)


async def vocab_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await query.edit_message_text(
        "📚 *Vocabulary*\nChoose an option:",
        reply_markup=VOCAB_MENU_KEYBOARD,
        parse_mode="MarkdownV2",
    )


async def vocab_stub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await query.edit_message_text(
        COMING_SOON,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back", callback_data="menu_vocab")],
        ]),
        parse_mode="MarkdownV2",
    )
