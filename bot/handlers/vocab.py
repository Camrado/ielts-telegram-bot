import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.models.progress import create_vocab_progress
from bot.models.user import get_or_create_user
from bot.models.vocabulary import (
    check_duplicates_bulk,
    find_duplicate,
    insert_word,
    insert_words_bulk,
    update_word,
)
from bot.services.ai import generate_vocab_entries_bulk, generate_vocab_entry

logger = logging.getLogger(__name__)

# ── Conversation states ──────────────────────────────────────────────────────

ADD_WAITING = 1
ADD_CONFIRM = 2
ADD_DUPLICATE = 3
ADD_EDITING = 4
BULK_WAITING = 5
BULK_CONFIRM = 6
BULK_REVIEWING = 7

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

COMING_SOON = "🚧 Coming soon — this feature will be available in the next update."


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


# ── Vocab menu (standalone handlers) ─────────────────────────────────────────


async def vocab_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await query.edit_message_text(
        "📚 <b>Vocabulary</b>\nChoose an option:",
        reply_markup=VOCAB_MENU_KEYBOARD,
        parse_mode="HTML",
    )


async def vocab_stub_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await query.edit_message_text(
        COMING_SOON,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀️ Back", callback_data="menu_vocab")]]
        ),
    )


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
        "Send me a list of words, one per line:\n\n"
        "<code>exacerbate\nmeticulous\nunprecedented\ndetrimental</code>",
        parse_mode="HTML",
    )
    return BULK_WAITING


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

    await progress_msg.edit_text(
        summary,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Save All", callback_data="vbulk_save")],
                [
                    InlineKeyboardButton(
                        "📝 Review First", callback_data="vbulk_review"
                    )
                ],
                [InlineKeyboardButton("❌ Discard", callback_data="vbulk_discard")],
            ]
        ),
    )
    return BULK_CONFIRM


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
    text = f"📝 Word 1/{len(entries)}:\n\n{format_entry(word, entry)}"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Keep", callback_data="vbulk_keep"),
                    InlineKeyboardButton("❌ Skip", callback_data="vbulk_skip"),
                ]
            ]
        ),
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
        text = f"📝 Word {index + 1}/{len(entries)}:\n\n{format_entry(word, entry)}"

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Keep", callback_data="vbulk_keep"),
                        InlineKeyboardButton("❌ Skip", callback_data="vbulk_skip"),
                    ]
                ]
            ),
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
            ],
            BULK_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_list),
            ],
            BULK_CONFIRM: [
                CallbackQueryHandler(bulk_save_all, pattern="^vbulk_save$"),
                CallbackQueryHandler(bulk_review_start, pattern="^vbulk_review$"),
                CallbackQueryHandler(bulk_discard, pattern="^vbulk_discard$"),
            ],
            BULK_REVIEWING: [
                CallbackQueryHandler(review_keep, pattern="^vbulk_keep$"),
                CallbackQueryHandler(review_skip, pattern="^vbulk_skip$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
        ],
        allow_reentry=True,
    )
