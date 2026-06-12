import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.models.user import get_or_create_user

logger = logging.getLogger(__name__)

MAIN_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📚 Vocabulary", callback_data="menu_vocab")],
    [InlineKeyboardButton("📖 Grammar", callback_data="menu_grammar")],
])

HELP_TEXT = (
    "🎓 *IELTS Preparation Bot*\n\n"
    "This bot helps you prepare for the IELTS exam\\.\n\n"
    "📚 *Vocabulary* — flashcards, quizzes, and spaced repetition\n"
    "📖 *Grammar* — topics, rules, and practice questions\n\n"
    "Use /start to open the main menu\\."
)


async def _ensure_user(update: Update) -> int:
    user = update.effective_user
    return await get_or_create_user(user.id, user.first_name, user.username)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update)
    await update.message.reply_text(
        "Welcome to the *IELTS Preparation Bot*\\! 🎓\nChoose a section:",
        reply_markup=MAIN_MENU_KEYBOARD,
        parse_mode="MarkdownV2",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update)
    await update.message.reply_text(HELP_TEXT, parse_mode="MarkdownV2")


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await query.edit_message_text(
        "Choose a section:",
        reply_markup=MAIN_MENU_KEYBOARD,
        parse_mode="MarkdownV2",
    )
