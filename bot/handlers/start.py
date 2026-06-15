import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import get_pool
from bot.handlers.menu_utils import delete_old_menu, refresh_menu, track_menu
from bot.repositories.progress import count_due_now, get_srs_status
from bot.repositories.grammar import get_all_progress, get_all_topics
from bot.repositories.user import get_or_create_user, get_user_streak
from bot.repositories.vocabulary import count_user_words

logger = logging.getLogger(__name__)

MAIN_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📚 Vocabulary", callback_data="menu_vocab")],
    [InlineKeyboardButton("📖 Grammar", callback_data="menu_grammar")],
])

HELP_TEXT = (
    "📚 <b>IELTS Prep Bot — Help</b>\n\n"
    "This bot helps you prepare for IELTS by building vocabulary and mastering grammar.\n\n"
    "📚 <b>Vocabulary</b>\n"
    "  • 🔁 Flashcards — spaced repetition review of your word deck\n"
    "  • 🎯 Quiz — random practice (doesn't affect SRS schedule)\n"
    "  • ➕ Add Word — add words with AI-generated definitions\n"
    "  • 📋 Bulk Add — add multiple words at once (text or file)\n"
    "  • 📊 Stats — track your progress\n\n"
    "📖 <b>Grammar</b>\n"
    "  • 📖 Learn — study grammar rules by topic\n"
    "  • 🎯 Quiz — test yourself (by topic, mixed, or weak areas)\n"
    "  • ➕ Add Topic — generate new topics with AI\n"
    "  • 📊 Stats — track mastery per topic\n\n"
    "<b>Commands:</b>\n"
    "/start — main menu\n"
    "/help — this message\n"
    "/cancel — exit current action\n"
    "/stats — quick stats overview\n"
    "/review — jump straight into flashcard review\n"
    "/reminders — toggle daily reminders on/off"
)


async def _ensure_user(update: Update) -> int:
    user = update.effective_user
    return await get_or_create_user(user.id, user.first_name, user.username)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update)
    await delete_old_menu(context, update.effective_chat.id)
    msg = await update.message.reply_text(
        "Welcome to the <b>IELTS Preparation Bot</b>! 🎓\nChoose a section:",
        reply_markup=MAIN_MENU_KEYBOARD,
        parse_mode="HTML",
    )
    await track_menu(context, msg)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update)
    await delete_old_menu(context, update.effective_chat.id)
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await refresh_menu(
        query, context,
        "Choose a section:",
        reply_markup=MAIN_MENU_KEYBOARD,
        parse_mode="HTML",
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_db_id = await _ensure_user(update)

    total_words = await count_user_words(user_db_id)
    due_today = await count_due_now(user_db_id)
    topics = await get_all_topics(user_db_id)
    progress_list = await get_all_progress(user_db_id)
    mastered = sum(1 for p in progress_list if p["mastery_level"] == "mastered")
    streak = await get_user_streak(user_db_id)

    text = (
        "📊 <b>Quick Overview</b>\n"
        f"📚 Vocab: {total_words} words, {due_today} due today\n"
        f"📖 Grammar: {len(topics)} topics, {mastered} mastered\n"
        f"🔥 Streak: {streak['current_streak']} days"
    )
    await delete_old_menu(context, update.effective_chat.id)
    msg = await update.message.reply_text(text, parse_mode="HTML", reply_markup=MAIN_MENU_KEYBOARD)
    await track_menu(context, msg)


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_db_id = await _ensure_user(update)
    pool = get_pool()
    enabled = await pool.fetchval(
        "SELECT reminders_enabled FROM users WHERE id = $1", user_db_id,
    )
    status = "ON" if enabled else "OFF"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔔 Turn On", callback_data="reminders_on"),
            InlineKeyboardButton("🔕 Turn Off", callback_data="reminders_off"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="back_main")],
    ])
    await delete_old_menu(context, update.effective_chat.id)
    msg = await update.message.reply_text(
        f"🔔 Reminders are currently <b>{status}</b>.",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await track_menu(context, msg)


async def reminders_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)
    pool = get_pool()

    enabled = query.data == "reminders_on"
    await pool.execute(
        "UPDATE users SET reminders_enabled = $1 WHERE id = $2",
        enabled, user_db_id,
    )
    status = "ON" if enabled else "OFF"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔔 Turn On", callback_data="reminders_on"),
            InlineKeyboardButton("🔕 Turn Off", callback_data="reminders_off"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="back_main")],
    ])
    await refresh_menu(
        query, context,
        f"🔔 Reminders are now <b>{status}</b>.",
        reply_markup=kb,
        parse_mode="HTML",
    )
