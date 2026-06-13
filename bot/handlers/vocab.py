import html
import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.models.progress import create_vocab_progress, get_srs_status, get_vocab_by_level
from bot.models.review_log import get_new_words_7days, get_vocab_stats_7days
from bot.models.user import get_or_create_user, get_user_streak
from bot.models.vocabulary import (
    check_duplicates_bulk,
    count_user_words,
    find_duplicate,
    insert_word,
    insert_words_bulk,
    update_word,
)
from bot.services.ai import (
    generate_vocab_entries_bulk,
    generate_vocab_entries_partial,
    generate_vocab_entry,
)
from bot.handlers.menu_utils import refresh_menu
from bot.services.file_parser import get_temp_path, parse_file

logger = logging.getLogger(__name__)

# ── Conversation states ──────────────────────────────────────────────────────

ADD_WAITING = 1
ADD_CONFIRM = 2
ADD_DUPLICATE = 3
ADD_EDITING = 4
BULK_WAITING = 5
BULK_CONFIRM = 6
BULK_REVIEWING = 7
BULK_METHOD = 8
FILE_WAITING = 9

ALL_VOCAB_FIELDS = ("definition", "synonyms", "collocations", "example", "cefr_level")

# ── Keyboards ─────────────────────────────────────────────────────────────────

VOCAB_MENU_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🔁 Flashcards", callback_data="vocab_flashcards")],
        [InlineKeyboardButton("🎯 Quiz", callback_data="vocab_quiz")],
        [InlineKeyboardButton("➕ Add Word", callback_data="vocab_add")],
        [InlineKeyboardButton("📋 Bulk Add", callback_data="vocab_bulk_add")],
        [InlineKeyboardButton("📊 Stats", callback_data="vocab_stats")],
        [InlineKeyboardButton("◀️ Back", callback_data="back_main")],
    ]
)

CONFIRM_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✅ Save", callback_data="vadd_save"),
            InlineKeyboardButton("✏️ Edit", callback_data="vadd_edit"),
            InlineKeyboardButton("❌ Cancel", callback_data="vadd_cancel"),
        ]
    ]
)

DUPLICATE_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✏️ Update", callback_data="vadd_update"),
            InlineKeyboardButton("❌ Cancel", callback_data="vadd_cancel"),
        ]
    ]
)

RETRY_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("🔄 Try Again", callback_data="vadd_retry"),
            InlineKeyboardButton("❌ Cancel", callback_data="vadd_cancel"),
        ]
    ]
)

BACK_TO_VOCAB = InlineKeyboardMarkup(
    [[InlineKeyboardButton("◀️ Back to Vocabulary", callback_data="menu_vocab")]]
)

BULK_METHOD_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("📝 Word List", callback_data="vbulk_wordlist")],
        [InlineKeyboardButton("📎 Upload File", callback_data="vbulk_file")],
        [InlineKeyboardButton("◀️ Back", callback_data="vbulk_back")],
    ]
)

BULK_RESULT_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("✅ Save All", callback_data="vbulk_save")],
        [InlineKeyboardButton("📝 Review First", callback_data="vbulk_review")],
        [InlineKeyboardButton("❌ Discard", callback_data="vbulk_discard")],
    ]
)



# ── Helpers ───────────────────────────────────────────────────────────────────


async def _ensure_user(update: Update) -> int:
    user = update.effective_user
    return await get_or_create_user(user.id, user.first_name, user.username)


def _clear_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        "pending_word",
        "pending_provided",
        "pending_entry",
        "is_update",
        "existing_word_id",
        "bulk_entries",
        "bulk_kept",
        "review_index",
        "bulk_skipped_count",
    ):
        context.user_data.pop(key, None)


def parse_word_input(raw: str) -> tuple[str, dict[str, str]]:
    parts = [p.strip() for p in raw.split("|")]
    word = parts[0].strip()
    provided: dict[str, str] = {}

    for part in parts[1:]:
        if not part:
            continue
        lower = part.lower()
        if lower.startswith(("syn:", "synonyms:")):
            provided["synonyms"] = part.split(":", 1)[1].strip()
        elif lower.startswith(("def:", "definition:")):
            provided["definition"] = part.split(":", 1)[1].strip()
        elif lower.startswith(("coll:", "collocations:")):
            provided["collocations"] = part.split(":", 1)[1].strip()
        elif lower.startswith(("ex:", "example:")):
            provided["example"] = part.split(":", 1)[1].strip()
        else:
            if word.lower() in part.lower() and "," in part:
                provided.setdefault("collocations", part)
            elif len(part.split()) > 5 and part.rstrip()[-1:] in ".!?":
                provided.setdefault("example", part)
            elif part.count(",") >= 2 and all(
                len(w.strip().split()) <= 2 for w in part.split(",")
            ):
                provided.setdefault("synonyms", part)
            else:
                provided.setdefault("definition", part)

    return word, provided


FIELD_ALIASES = {
    "def": "definition",
    "definition": "definition",
    "syn": "synonyms",
    "synonyms": "synonyms",
    "synonym": "synonyms",
    "coll": "collocations",
    "collocations": "collocations",
    "collocation": "collocations",
    "ex": "example",
    "example": "example",
    "level": "cefr_level",
    "cefr": "cefr_level",
    "cefr_level": "cefr_level",
}


def format_entry(word: str, entry: dict, label: str = "New entry") -> str:
    w = html.escape(word)
    lines = [f'📝 {label} for "<b>{w}</b>":\n']
    if entry.get("definition"):
        lines.append(f'📖 <b>Definition:</b> {html.escape(entry["definition"])}')
    if entry.get("synonyms"):
        lines.append(f'🔄 <b>Synonyms:</b> {html.escape(entry["synonyms"])}')
    if entry.get("collocations"):
        lines.append(f'🤝 <b>Collocations:</b> {html.escape(entry["collocations"])}')
    if entry.get("example"):
        lines.append(f'📝 <b>Example:</b> "{html.escape(entry["example"])}"')
    if entry.get("cefr_level"):
        lines.append(f'📊 <b>Level:</b> {html.escape(entry["cefr_level"])}')
    return "\n".join(lines)


def _source_label(entry: dict) -> str:
    source = entry.get("_source", "")
    if source == "file_complete":
        return "📄 From file"
    elif source == "ai_generated":
        return "🤖 AI-generated"
    elif source == "ai_completed":
        return "🤖 AI-completed (partial)"
    return ""


def _review_keyboard(remaining: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("✅ Keep", callback_data="vbulk_keep"),
            InlineKeyboardButton("❌ Skip", callback_data="vbulk_skip"),
        ],
    ]
    if remaining > 1:
        rows.append(
            [InlineKeyboardButton("✅ Save Remaining", callback_data="vbulk_save_rest")]
        )
    return InlineKeyboardMarkup(rows)


# ── Vocab menu (standalone handlers) ─────────────────────────────────────────


async def vocab_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await refresh_menu(
        query, context,
        "📚 <b>Vocabulary</b>\nChoose an option:",
        reply_markup=VOCAB_MENU_KEYBOARD,
        parse_mode="HTML",
    )


async def vocab_stats_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    total = await count_user_words(user_db_id)
    by_level = await get_vocab_by_level(user_db_id)
    srs = await get_srs_status(user_db_id)
    week = await get_vocab_stats_7days(user_db_id)
    new_words = await get_new_words_7days(user_db_id)
    streak = await get_user_streak(user_db_id)

    level_parts = []
    for lvl in ("B2", "C1", "C2"):
        n = by_level.get(lvl, 0)
        if n:
            level_parts.append(f"{lvl}: {n}")
    others = sum(v for k, v in by_level.items() if k not in ("B2", "C1", "C2"))
    if others:
        level_parts.append(f"Other: {others}")
    level_str = " | ".join(level_parts) if level_parts else "—"

    text = (
        "📊 <b>Vocabulary Statistics</b>\n\n"
        f"📚 Total words: {total}\n"
        f"📊 By level: {level_str}\n\n"
        "🔁 <b>SRS Status:</b>\n"
        f"  • Due now: {srs['due_now']}\n"
        f"  • Learning (interval &lt; 7 days): {srs['learning']}\n"
        f"  • Young (7–21 days): {srs['young']}\n"
        f"  • Mature (21+ days): {srs['mature']}\n\n"
        "📈 <b>Last 7 days:</b>\n"
        f"  • Cards reviewed: {week['reviewed']}\n"
        f"  • Accuracy: {week['accuracy']}%\n"
        f"  • New words added: {new_words}\n\n"
        f"🔥 Streak: {streak['current_streak']} days"
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Back", callback_data="menu_vocab")]]
    )
    await refresh_menu(query, context, text, reply_markup=kb, parse_mode="HTML")


# ── Add Word flow ─────────────────────────────────────────────────────────────


async def vocab_add_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    _clear_pending(context)

    await query.edit_message_text(
        "Send me a word or phrase to add. You can include extra info using "
        "<code>|</code> as separator:\n\n"
        "• Just the word: <code>reluctant</code>\n"
        "• Word + definition: <code>reluctant | unwilling to do something</code>\n"
        "• Word + any fields: <code>reluctant | syn: hesitant, unwilling "
        "| coll: reluctant to admit</code>\n\n"
        "I'll use AI to fill in anything you don't provide.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀️ Back", callback_data="vadd_back_vocab")]]
        ),
    )
    return ADD_WAITING


async def _generate_and_show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    word: str,
    provided: dict[str, str],
    message_to_edit=None,
) -> int:
    all_fields = ("definition", "synonyms", "collocations", "example", "cefr_level")
    missing = [f for f in all_fields if f not in provided]

    if not missing:
        entry = {**provided, "word_phrase": word}
        context.user_data["pending_entry"] = entry
        text = format_entry(word, entry)
        if message_to_edit:
            await message_to_edit.edit_text(
                text, reply_markup=CONFIRM_KEYBOARD, parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                text, reply_markup=CONFIRM_KEYBOARD, parse_mode="HTML"
            )
        return ADD_CONFIRM

    if message_to_edit:
        await message_to_edit.edit_text("⏳ Generating vocabulary entry...")
        target_msg = message_to_edit
    else:
        target_msg = await update.message.reply_text(
            "⏳ Generating vocabulary entry..."
        )

    try:
        ai_result = await generate_vocab_entry(word, provided)
        entry = {**ai_result, **provided, "word_phrase": word}
        context.user_data["pending_entry"] = entry
        text = format_entry(word, entry)
        await target_msg.edit_text(
            text, reply_markup=CONFIRM_KEYBOARD, parse_mode="HTML"
        )
        return ADD_CONFIRM
    except Exception as e:
        logger.error("AI generation failed for '%s': %s", word, e)
        await target_msg.edit_text(
            "⚠️ Failed to generate vocabulary entry. "
            "This might be due to an API issue.",
            reply_markup=RETRY_KEYBOARD,
        )
        return ADD_CONFIRM


async def receive_word(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_db_id = await _ensure_user(update)
    raw = update.message.text.strip()
    word, provided = parse_word_input(raw)

    if not word:
        await update.message.reply_text("Please send a valid word or phrase.")
        return ADD_WAITING

    context.user_data["pending_word"] = word
    context.user_data["pending_provided"] = provided
    context.user_data["is_update"] = False

    dup = await find_duplicate(user_db_id, word)
    if dup:
        context.user_data["existing_word_id"] = dup["id"]
        text = f'⚠️ This word already exists in your vocabulary:\n\n📖 <b>{html.escape(dup["word_phrase"])}</b>\n'
        if dup.get("definition"):
            text += f'📖 Definition: {html.escape(dup["definition"])}\n'
        if dup.get("synonyms"):
            text += f'🔄 Synonyms: {html.escape(dup["synonyms"])}\n'
        text += "\nDo you want to update it with new data?"

        await update.message.reply_text(
            text, reply_markup=DUPLICATE_KEYBOARD, parse_mode="HTML"
        )
        return ADD_DUPLICATE

    return await _generate_and_show(update, context, word, provided)


async def handle_duplicate_update(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["is_update"] = True

    word = context.user_data["pending_word"]
    provided = context.user_data["pending_provided"]
    return await _generate_and_show(
        update, context, word, provided, message_to_edit=query.message
    )


async def retry_ai_add(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer("Retrying...")

    word = context.user_data["pending_word"]
    provided = context.user_data["pending_provided"]
    return await _generate_and_show(
        update, context, word, provided, message_to_edit=query.message
    )


async def save_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    entry = context.user_data["pending_entry"]
    is_update = context.user_data.get("is_update", False)
    w = html.escape(entry["word_phrase"])

    if is_update:
        word_id = context.user_data["existing_word_id"]
        await update_word(word_id, entry)
        await query.edit_message_text(
            f'✅ Updated "<b>{w}</b>" in your vocabulary.',
            parse_mode="HTML",
            reply_markup=BACK_TO_VOCAB,
        )
    else:
        word_id = await insert_word(user_db_id, entry)
        await create_vocab_progress(user_db_id, word_id)
        await query.edit_message_text(
            f'✅ Saved "<b>{w}</b>" to your vocabulary.',
            parse_mode="HTML",
            reply_markup=BACK_TO_VOCAB,
        )

    _clear_pending(context)
    return ConversationHandler.END


async def start_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Which field do you want to change? Send it in format:\n\n"
        "<code>field: new value</code>\n\n"
        "Fields: definition, synonyms, collocations, example, cefr_level\n\n"
        "Example: <code>definition: a new definition here</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel Edit", callback_data="vadd_cancel_edit")]]
        ),
    )
    return ADD_EDITING


async def receive_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    raw = update.message.text.strip()

    if ":" not in raw:
        await update.message.reply_text(
            "Please use the format: <code>field: new value</code>",
            parse_mode="HTML",
        )
        return ADD_EDITING

    field_name, value = raw.split(":", 1)
    field_name = field_name.strip().lower()
    value = value.strip()

    field = FIELD_ALIASES.get(field_name)
    if not field:
        await update.message.reply_text(
            f"Unknown field: <code>{html.escape(field_name)}</code>\n"
            "Valid fields: definition, synonyms, collocations, example, cefr_level",
            parse_mode="HTML",
        )
        return ADD_EDITING

    entry = context.user_data["pending_entry"]
    entry[field] = value
    context.user_data["pending_entry"] = entry

    word = context.user_data["pending_word"]
    text = format_entry(word, entry, "Updated entry")
    await update.message.reply_text(
        text, reply_markup=CONFIRM_KEYBOARD, parse_mode="HTML"
    )
    return ADD_CONFIRM


async def cancel_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    entry = context.user_data["pending_entry"]
    word = entry.get("word_phrase", "")
    text = format_entry(word, entry)
    await query.edit_message_text(
        text, reply_markup=CONFIRM_KEYBOARD, parse_mode="HTML"
    )
    return ADD_CONFIRM


async def back_to_vocab_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    _clear_pending(context)
    await refresh_menu(
        query, context,
        "📚 <b>Vocabulary</b>\nChoose an option:",
        reply_markup=VOCAB_MENU_KEYBOARD,
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel_add(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    _clear_pending(context)
    await query.edit_message_text("❌ Cancelled.", reply_markup=BACK_TO_VOCAB)
    return ConversationHandler.END


# ── Bulk Add flow ─────────────────────────────────────────────────────────────


async def bulk_add_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    _clear_pending(context)

    await query.edit_message_text(
        "📋 <b>Bulk Add</b> — choose your method:",
        reply_markup=BULK_METHOD_KEYBOARD,
        parse_mode="HTML",
    )
    return BULK_METHOD


async def bulk_word_list_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Send me a list of words, one per line:\n\n"
        "<code>exacerbate\nmeticulous\nunprecedented\ndetrimental</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀️ Back", callback_data="vbulk_back_method")]]
        ),
    )
    return BULK_WAITING


async def bulk_file_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📎 Send me an <b>.xlsx</b> or <b>.csv</b> file with your vocabulary.\n\n"
        "Expected columns (header names are flexible):\n"
        "• <b>Word/Phrase</b> (required — this is the lookup key)\n"
        "• Definition\n"
        "• Synonyms\n"
        "• Collocations\n"
        "• Example\n\n"
        "Rules:\n"
        "• Only the Word/Phrase column is required\n"
        "• Any other column can be filled, partially filled, or completely empty\n"
        "• I'll use AI to generate only the missing data\n"
        "• Duplicates already in your vocabulary will be skipped",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀️ Back", callback_data="vbulk_back_method")]]
        ),
    )
    return FILE_WAITING


async def bulk_back(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    _clear_pending(context)
    await refresh_menu(
        query, context,
        "📚 <b>Vocabulary</b>\nChoose an option:",
        reply_markup=VOCAB_MENU_KEYBOARD,
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def bulk_back_to_method(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📋 <b>Bulk Add</b> — choose your method:",
        reply_markup=BULK_METHOD_KEYBOARD,
        parse_mode="HTML",
    )
    return BULK_METHOD


# ── Bulk Add: Word List ──────────────────────────────────────────────────────


async def receive_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_db_id = await _ensure_user(update)
    raw = update.message.text.strip()

    words: list[str] = []
    seen: set[str] = set()
    for line in raw.split("\n"):
        w = line.strip()
        if w and w.lower() not in seen:
            words.append(w)
            seen.add(w.lower())

    if not words:
        await update.message.reply_text("Please send at least one word.")
        return BULK_WAITING

    existing = await check_duplicates_bulk(user_db_id, words)
    new_words = [w for w in words if w.lower().strip() not in existing]
    db_dups = len(words) - len(new_words)

    if not new_words:
        await update.message.reply_text(
            "All words already exist in your vocabulary. No new words to add.",
            reply_markup=BACK_TO_VOCAB,
        )
        _clear_pending(context)
        return ConversationHandler.END

    total = len(new_words)
    progress_msg = await update.message.reply_text(
        f"Processing {total} words... ⏳ 0/{total}"
    )

    all_entries: list[dict] = []
    failed_words: list[str] = []
    processed = 0

    for i in range(0, total, 5):
        batch = new_words[i : i + 5]
        generated = False
        for attempt in range(2):
            try:
                entries = await generate_vocab_entries_bulk(batch)
                all_entries.extend(entries)
                generated = True
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning("Bulk AI failed for %s, retrying: %s", batch, e)
                else:
                    logger.error("Bulk AI failed for %s after retry: %s", batch, e)
        if not generated:
            failed_words.extend(batch)

        processed = min(i + 5, total)
        try:
            await progress_msg.edit_text(
                f"Processing {total} words... ✅ {processed}/{total}"
            )
        except Exception:
            pass

    if not all_entries:
        await progress_msg.edit_text(
            "⚠️ Failed to generate entries for all words. Please try again later.",
            reply_markup=BACK_TO_VOCAB,
        )
        _clear_pending(context)
        return ConversationHandler.END

    context.user_data["bulk_entries"] = all_entries
    context.user_data["bulk_skipped_count"] = db_dups

    summary = f"✅ Generated {len(all_entries)} new words."
    if db_dups:
        summary += f" {db_dups} duplicates skipped."
    if failed_words:
        summary += f" {len(failed_words)} failed: {', '.join(failed_words)}."

    await progress_msg.edit_text(summary, reply_markup=BULK_RESULT_KEYBOARD)
    return BULK_CONFIRM


# ── Bulk Add: File Upload ────────────────────────────────────────────────────


async def file_waiting_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    await update.message.reply_text(
        '📎 Please send an .xlsx or .csv file, not text.\n\n'
        'If you\'d like to type words instead, go back and choose "📝 Word List".',
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀️ Back", callback_data="vbulk_back_method")]]
        ),
    )
    return FILE_WAITING


async def receive_file(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_db_id = await _ensure_user(update)
    doc = update.message.document
    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Back", callback_data="vbulk_back_method")]]
    )

    filename = doc.file_name or ""
    ext = Path(filename).suffix.lower()
    if ext not in (".xlsx", ".csv"):
        await update.message.reply_text(
            "❌ Unsupported file format. Please send an .xlsx or .csv file.",
            reply_markup=back_kb,
        )
        return FILE_WAITING

    temp_path = get_temp_path(filename)
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(temp_path)
    except Exception as e:
        logger.error("Failed to download file: %s", e)
        await update.message.reply_text(
            "⚠️ Failed to download the file. Please try again.",
            reply_markup=back_kb,
        )
        return FILE_WAITING

    try:
        return await _process_uploaded_file(update, context, user_db_id, temp_path)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


async def _process_uploaded_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_db_id: int,
    temp_path: str,
) -> int:
    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Back", callback_data="vbulk_back_method")]]
    )

    result = parse_file(temp_path)
    if "error" in result:
        await update.message.reply_text(result["error"], reply_markup=back_kb)
        return FILE_WAITING

    entries = result["entries"]

    if result.get("multiple_sheets"):
        await update.message.reply_text(
            "ℹ️ Your file has multiple sheets. Using the first sheet only."
        )

    if len(entries) > 500:
        await update.message.reply_text(
            f"⚠️ File has {len(entries)} rows. Maximum is 500 per upload. "
            "Please split your file.",
            reply_markup=back_kb,
        )
        return FILE_WAITING

    total_in_file = len(entries)

    # Dedup within file
    seen: set[str] = set()
    unique_entries: list[dict] = []
    file_dups = 0
    for entry in entries:
        key = entry["word_phrase"].lower().strip()
        if key in seen:
            file_dups += 1
        else:
            seen.add(key)
            unique_entries.append(entry)

    # Dedup against DB
    words_to_check = [e["word_phrase"] for e in unique_entries]
    existing = await check_duplicates_bulk(user_db_id, words_to_check)
    new_entries = [
        e for e in unique_entries if e["word_phrase"].lower().strip() not in existing
    ]
    db_dups = len(unique_entries) - len(new_entries)

    if not new_entries:
        await update.message.reply_text(
            "All words already exist in your vocabulary. No new words to add.",
            reply_markup=BACK_TO_VOCAB,
        )
        _clear_pending(context)
        return ConversationHandler.END

    # Categorize entries
    complete_entries: list[dict] = []
    partial_entries: list[dict] = []
    empty_entries: list[dict] = []

    for entry in new_entries:
        filled = [f for f in ALL_VOCAB_FIELDS if entry.get(f)]
        if len(filled) == len(ALL_VOCAB_FIELDS):
            entry["_source"] = "file_complete"
            complete_entries.append(entry)
        elif filled:
            entry["_source"] = "ai_completed"
            partial_entries.append(entry)
        else:
            entry["_source"] = "ai_generated"
            empty_entries.append(entry)

    needs_ai = len(partial_entries) + len(empty_entries)

    summary_lines = [
        "📊 <b>Processing summary:</b>",
        f"• Total rows in file: {total_in_file}",
    ]
    if file_dups:
        summary_lines.append(f"• Duplicates within file: {file_dups} (skipped)")
    if db_dups:
        summary_lines.append(f"• Already in your vocabulary: {db_dups} (skipped)")
    summary_lines.append(f"• New words to process: {len(new_entries)}")

    if needs_ai:
        summary_lines.append(
            f"\n⏳ Generating missing data for {needs_ai} words "
            "with incomplete entries..."
        )
    else:
        summary_lines.append("\n✅ All entries are complete!")

    progress_msg = await update.message.reply_text(
        "\n".join(summary_lines), parse_mode="HTML"
    )

    # Process entries needing AI
    all_processed: list[dict] = list(complete_entries)
    failed_words: list[str] = []
    processed_count = 0
    total_ai = needs_ai

    # Empty entries → batch of 5
    for i in range(0, len(empty_entries), 5):
        batch = empty_entries[i : i + 5]
        batch_words = [e["word_phrase"] for e in batch]
        generated = False
        for attempt in range(2):
            try:
                results = await generate_vocab_entries_bulk(batch_words)
                for r in results:
                    r["_source"] = "ai_generated"
                all_processed.extend(results)
                generated = True
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning("Bulk AI failed for %s, retrying: %s", batch_words, e)
                else:
                    logger.error(
                        "Bulk AI failed for %s after retry: %s", batch_words, e
                    )
        if not generated:
            failed_words.extend(batch_words)

        processed_count += len(batch)
        if total_ai > 0:
            try:
                await progress_msg.edit_text(
                    f"⏳ Generating... {processed_count}/{total_ai}"
                )
            except Exception:
                pass

    # Partial entries → batch of 3
    for i in range(0, len(partial_entries), 3):
        batch = partial_entries[i : i + 3]
        generated = False
        for attempt in range(2):
            try:
                results = await generate_vocab_entries_partial(batch)
                for r in results:
                    r["_source"] = "ai_completed"
                all_processed.extend(results)
                generated = True
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning("Partial AI failed, retrying: %s", e)
                else:
                    logger.error("Partial AI failed after retry: %s", e)
        if not generated:
            failed_words.extend([e["word_phrase"] for e in batch])

        processed_count += len(batch)
        if total_ai > 0:
            try:
                await progress_msg.edit_text(
                    f"⏳ Generating... {processed_count}/{total_ai}"
                )
            except Exception:
                pass

    if not all_processed:
        await progress_msg.edit_text(
            "⚠️ Failed to process all words. Please try again later.",
            reply_markup=BACK_TO_VOCAB,
        )
        _clear_pending(context)
        return ConversationHandler.END

    context.user_data["bulk_entries"] = all_processed

    n_complete = len(complete_entries)
    n_ai_gen = sum(1 for e in all_processed if e.get("_source") == "ai_generated")
    n_ai_part = sum(1 for e in all_processed if e.get("_source") == "ai_completed")

    final = f"✅ All {len(all_processed)} entries ready!\n\n"
    final += f"• Complete from file (no AI needed): {n_complete}\n"
    final += f"• AI-generated (all fields): {n_ai_gen}\n"
    final += f"• AI-completed (partial fill): {n_ai_part}"
    if failed_words:
        final += f"\n• ⚠️ Failed: {len(failed_words)} ({', '.join(failed_words)})"

    await progress_msg.edit_text(final, reply_markup=BULK_RESULT_KEYBOARD)
    return BULK_CONFIRM


# ── Bulk: Save / Review / Discard (shared by both word list & file upload) ───


async def bulk_save_all(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    entries = context.user_data.get("bulk_entries", [])
    if not entries:
        await query.edit_message_text("No entries to save.", reply_markup=BACK_TO_VOCAB)
        _clear_pending(context)
        return ConversationHandler.END

    word_ids = await insert_words_bulk(user_db_id, entries)
    for wid in word_ids:
        await create_vocab_progress(user_db_id, wid)

    await query.edit_message_text(
        f"✅ Saved {len(word_ids)} words to your vocabulary.",
        reply_markup=BACK_TO_VOCAB,
    )
    _clear_pending(context)
    return ConversationHandler.END


async def bulk_review_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["review_index"] = 0
    context.user_data["bulk_kept"] = []

    entries = context.user_data.get("bulk_entries", [])
    if not entries:
        await query.edit_message_text(
            "No entries to review.", reply_markup=BACK_TO_VOCAB
        )
        _clear_pending(context)
        return ConversationHandler.END

    entry = entries[0]
    word = entry.get("word_phrase", "")
    source = _source_label(entry)
    text = format_entry(word, entry, label=f"Entry 1/{len(entries)}")
    if source:
        text += f"\n{source}"

    await query.edit_message_text(
        text,
        reply_markup=_review_keyboard(len(entries)),
        parse_mode="HTML",
    )
    return BULK_REVIEWING


async def _handle_review_next(
    update: Update, context: ContextTypes.DEFAULT_TYPE, keep: bool
) -> int:
    query = update.callback_query
    await query.answer()

    entries = context.user_data["bulk_entries"]
    index = context.user_data["review_index"]

    if keep:
        context.user_data["bulk_kept"].append(entries[index])

    index += 1
    context.user_data["review_index"] = index

    if index < len(entries):
        entry = entries[index]
        word = entry.get("word_phrase", "")
        remaining = len(entries) - index
        source = _source_label(entry)
        text = format_entry(word, entry, label=f"Entry {index + 1}/{len(entries)}")
        if source:
            text += f"\n{source}"

        await query.edit_message_text(
            text,
            reply_markup=_review_keyboard(remaining),
            parse_mode="HTML",
        )
        return BULK_REVIEWING

    kept = context.user_data["bulk_kept"]
    if kept:
        user_db_id = await _ensure_user(update)
        word_ids = await insert_words_bulk(user_db_id, kept)
        for wid in word_ids:
            await create_vocab_progress(user_db_id, wid)
        skipped = len(entries) - len(kept)
        await query.edit_message_text(
            f"✅ Saved {len(kept)} words. {skipped} skipped.",
            reply_markup=BACK_TO_VOCAB,
        )
    else:
        await query.edit_message_text(
            "No words kept. All entries discarded.",
            reply_markup=BACK_TO_VOCAB,
        )

    _clear_pending(context)
    return ConversationHandler.END


async def review_keep(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await _handle_review_next(update, context, keep=True)


async def review_skip(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await _handle_review_next(update, context, keep=False)


async def review_save_remaining(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    entries = context.user_data["bulk_entries"]
    index = context.user_data["review_index"]
    kept = context.user_data["bulk_kept"]

    all_to_save = kept + entries[index:]

    if all_to_save:
        word_ids = await insert_words_bulk(user_db_id, all_to_save)
        for wid in word_ids:
            await create_vocab_progress(user_db_id, wid)
        await query.edit_message_text(
            f"✅ Saved {len(word_ids)} words to your vocabulary.",
            reply_markup=BACK_TO_VOCAB,
        )
    else:
        await query.edit_message_text(
            "No words to save.", reply_markup=BACK_TO_VOCAB
        )

    _clear_pending(context)
    return ConversationHandler.END


async def bulk_discard(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    _clear_pending(context)
    await query.edit_message_text(
        "❌ All entries discarded.", reply_markup=BACK_TO_VOCAB
    )
    return ConversationHandler.END


# ── Cancel (shared fallback) ──────────────────────────────────────────────────


async def cancel_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _clear_pending(context)
    await update.message.reply_text("❌ Cancelled.", reply_markup=BACK_TO_VOCAB)
    return ConversationHandler.END


# ── ConversationHandler builder ───────────────────────────────────────────────


def build_vocab_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(vocab_add_start, pattern="^vocab_add$"),
            CallbackQueryHandler(bulk_add_start, pattern="^vocab_bulk_add$"),
        ],
        states={
            ADD_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_word),
                CallbackQueryHandler(back_to_vocab_menu, pattern="^vadd_back_vocab$"),
            ],
            ADD_CONFIRM: [
                CallbackQueryHandler(save_entry, pattern="^vadd_save$"),
                CallbackQueryHandler(start_edit, pattern="^vadd_edit$"),
                CallbackQueryHandler(cancel_add, pattern="^vadd_cancel$"),
                CallbackQueryHandler(retry_ai_add, pattern="^vadd_retry$"),
            ],
            ADD_DUPLICATE: [
                CallbackQueryHandler(handle_duplicate_update, pattern="^vadd_update$"),
                CallbackQueryHandler(cancel_add, pattern="^vadd_cancel$"),
            ],
            ADD_EDITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit),
                CallbackQueryHandler(cancel_edit, pattern="^vadd_cancel_edit$"),
            ],
            BULK_METHOD: [
                CallbackQueryHandler(
                    bulk_word_list_start, pattern="^vbulk_wordlist$"
                ),
                CallbackQueryHandler(bulk_file_start, pattern="^vbulk_file$"),
                CallbackQueryHandler(bulk_back, pattern="^vbulk_back$"),
            ],
            BULK_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_list),
                CallbackQueryHandler(
                    bulk_back_to_method, pattern="^vbulk_back_method$"
                ),
            ],
            FILE_WAITING: [
                MessageHandler(filters.Document.ALL, receive_file),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, file_waiting_text
                ),
                CallbackQueryHandler(
                    bulk_back_to_method, pattern="^vbulk_back_method$"
                ),
            ],
            BULK_CONFIRM: [
                CallbackQueryHandler(bulk_save_all, pattern="^vbulk_save$"),
                CallbackQueryHandler(
                    bulk_review_start, pattern="^vbulk_review$"
                ),
                CallbackQueryHandler(bulk_discard, pattern="^vbulk_discard$"),
            ],
            BULK_REVIEWING: [
                CallbackQueryHandler(review_keep, pattern="^vbulk_keep$"),
                CallbackQueryHandler(review_skip, pattern="^vbulk_skip$"),
                CallbackQueryHandler(
                    review_save_remaining, pattern="^vbulk_save_rest$"
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
        ],
        allow_reentry=True,
    )
