import html
import logging
import random
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.handlers.menu_utils import delete_old_menu
from bot.models.progress import (
    count_due_tomorrow,
    get_due_cards,
    get_earliest_review,
    update_vocab_progress,
)
from bot.models.review_log import log_vocab_review
from bot.models.user import get_or_create_user, update_streak
from bot.models.vocabulary import (
    count_user_words,
    get_random_distractors,
    get_random_user_words,
)
from bot.services.srs import sm2_update
from bot.utils import levenshtein

logger = logging.getLogger(__name__)

FC_WAITING_ANSWER = 20
FC_WAITING_NEXT = 21

BACK_TO_VOCAB = InlineKeyboardMarkup(
    [[InlineKeyboardButton("◀️ Back to Vocabulary", callback_data="menu_vocab")]]
)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _ensure_user(update: Update) -> int:
    u = update.effective_user
    return await get_or_create_user(u.id, u.first_name, u.username)


def _session(ctx: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return ctx.user_data.get("fc_session")


def _clear(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("fc_session", None)


# ── Cloze helpers ────────────────────────────────────────────────────────────


def _create_cloze(text: str, word_phrase: str) -> tuple[str, str] | None:
    pattern = re.compile(rf"(?i)\b{re.escape(word_phrase)}\w*\b")
    m = pattern.search(text)
    if m:
        return text[: m.start()] + "___" + text[m.end() :], m.group()
    return None


def _get_vocab_hint(card: dict, ctype: int) -> str:
    if ctype == 1:
        if card.get("synonyms"):
            return f"🔄 Synonyms: {card['synonyms']}"
        if card.get("example"):
            return f'📝 Example: "{card["example"]}"'
    elif ctype == 2:
        if card.get("example"):
            return f'📝 Example: "{card["example"]}"'
        if card.get("synonyms"):
            return f"🔄 Synonyms: {card['synonyms']}"
    elif ctype == 3:
        if card.get("definition"):
            return f"📖 Definition: {card['definition']}"
    elif ctype == 4:
        if card.get("definition"):
            return f"📖 Definition: {card['definition']}"
    elif ctype == 5:
        if card.get("definition"):
            return f"📖 Definition: {card['definition']}"
    return ""


# ── Card-type selection ──────────────────────────────────────────────────────


def _pick_card_type(card: dict, word_count: int) -> int:
    types: list[int] = []
    weights: list[float] = []

    if card.get("definition"):
        types.append(1)
        weights.append(30)

    if word_count >= 4 and card.get("definition"):
        types.append(2)
        weights.append(17.5)

    if card.get("collocations"):
        colls = [c.strip() for c in card["collocations"].split(",") if c.strip()]
        if any(_create_cloze(c, card["word_phrase"]) for c in colls):
            types.append(3)
            weights.append(17.5)

    if word_count >= 4 and card.get("synonyms"):
        syns = [s.strip() for s in card["synonyms"].split(",") if s.strip()]
        if syns:
            types.append(4)
            weights.append(17.5)

    if card.get("example") and _create_cloze(card["example"], card["word_phrase"]):
        types.append(5)
        weights.append(17.5)

    if not types:
        return 1

    return random.choices(types, weights=weights, k=1)[0]


# ── Question generation ─────────────────────────────────────────────────────


async def _make_question(
    card: dict, ctype: int, user_db_id: int
) -> tuple[str, InlineKeyboardMarkup | None, str, int | None]:
    """Returns (text, keyboard|None, correct_answer, correct_option_index|None)."""
    word = card["word_phrase"]

    if ctype == 1:
        return (
            f"📖 What word matches this definition?\n\n"
            f"\"{html.escape(card.get('definition', ''))}\"\n\n"
            f"Type your answer:",
            None,
            word,
            None,
        )

    if ctype == 2:
        correct_def = card["definition"]
        distractors = await get_random_distractors(user_db_id, card["id"], "definition", 3)
        if len(distractors) < 3:
            return await _make_question(card, 1, user_db_id)
        options = [correct_def] + distractors
        random.shuffle(options)
        idx = options.index(correct_def)
        labels = "ABCD"
        option_lines = "\n".join(
            f"<b>{labels[i]}.</b> {html.escape(o)}" for i, o in enumerate(options)
        )
        buttons = [[
            InlineKeyboardButton(labels[i], callback_data=f"fc_ans_{i}")
            for i in range(len(options))
        ]]
        return (
            f"🔤 What does \"<b>{html.escape(word)}</b>\" mean?\n\n{option_lines}",
            InlineKeyboardMarkup(buttons),
            correct_def,
            idx,
        )

    if ctype == 3:
        colls = [c.strip() for c in card["collocations"].split(",") if c.strip()]
        valid = [(c, _create_cloze(c, word)) for c in colls]
        valid = [(c, r) for c, r in valid if r is not None]
        if not valid:
            return await _make_question(card, 1, user_db_id)
        _, (cloze, answer) = random.choice(valid)
        return (
            f"🤝 Complete the collocation:\n\n"
            f"\"{html.escape(cloze)}\"\n\n"
            f"Type the missing word:",
            None,
            answer,
            None,
        )

    if ctype == 4:
        syns = [s.strip() for s in card["synonyms"].split(",") if s.strip()]
        correct_syn = random.choice(syns)
        distractors = await get_random_distractors(user_db_id, card["id"], "word_phrase", 3)
        if len(distractors) < 3:
            return await _make_question(card, 1, user_db_id)
        options = [correct_syn] + distractors
        random.shuffle(options)
        idx = options.index(correct_syn)
        labels = "ABCD"
        option_lines = "\n".join(
            f"<b>{labels[i]}.</b> {html.escape(o)}" for i, o in enumerate(options)
        )
        buttons = [[
            InlineKeyboardButton(labels[i], callback_data=f"fc_ans_{i}")
            for i in range(len(options))
        ]]
        return (
            f"🔄 Which word is a synonym of \"<b>{html.escape(word)}</b>\"?\n\n{option_lines}",
            InlineKeyboardMarkup(buttons),
            correct_syn,
            idx,
        )

    if ctype == 5:
        result = _create_cloze(card["example"], word)
        if not result:
            return await _make_question(card, 1, user_db_id)
        cloze, answer = result
        return (
            f"📝 Fill in the blank:\n\n"
            f"\"{html.escape(cloze)}\"\n\n"
            f"Type the missing word:",
            None,
            answer,
            None,
        )

    return await _make_question(card, 1, user_db_id)


# ── Show a card ──────────────────────────────────────────────────────────────


async def _show_card(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    *,
    edit_message=None,
) -> int:
    ses = _session(ctx)
    card = ses["cards"][ses["current"]]
    user_db_id = ses["user_db_id"]

    wc = await count_user_words(user_db_id)
    ctype = _pick_card_type(card, wc)
    ses["card_type"] = ctype

    question, kb, answer, correct_idx = await _make_question(card, ctype, user_db_id)
    ses["correct_answer"] = answer
    ses["correct_option_index"] = correct_idx

    hint = _get_vocab_hint(card, ctype)
    ses["hint_text"] = hint

    idk_row = [InlineKeyboardButton("🤷 I don't know", callback_data="fc_idk")]
    bottom_row = []
    if hint:
        bottom_row.append(InlineKeyboardButton("💡 Hint", callback_data="fc_hint"))
    bottom_row.append(InlineKeyboardButton("❌ Quit", callback_data="fc_quit"))
    if kb:
        kb = InlineKeyboardMarkup(kb.inline_keyboard + [idk_row, bottom_row])
    else:
        kb = InlineKeyboardMarkup([idk_row, bottom_row])

    cur = ses["current"] + 1
    total = ses["total"]
    prefix = "📚 Review" if ses["mode"] == "flashcard" else "🎯 Quiz"
    text = f"{prefix}: {cur}/{total}\n\n{question}"

    if edit_message:
        await edit_message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        chat = update.effective_chat.id
        await ctx.bot.send_message(chat, text, reply_markup=kb, parse_mode="HTML")

    return FC_WAITING_ANSWER


# ── Entry points ─────────────────────────────────────────────────────────────


async def flashcards_start(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    cards = await get_due_cards(user_db_id, limit=20)

    if not cards:
        earliest = await get_earliest_review(user_db_id)
        if earliest:
            ts = earliest.strftime("%b %d, %H:%M")
            text = (
                f"🎉 No cards due for review! Next review: {ts}.\n\n"
                "Want to do a random quiz instead?"
            )
        else:
            text = (
                "🎉 No cards due for review!\n\n"
                "Add some words first, then come back for flashcards."
            )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Quiz", callback_data="vocab_quiz")],
            [InlineKeyboardButton("◀️ Back", callback_data="menu_vocab")],
        ])
        await query.edit_message_text(text, reply_markup=kb)
        return ConversationHandler.END

    count = len(cards)
    ctx.user_data["fc_session"] = {
        "mode": "flashcard",
        "user_db_id": user_db_id,
        "cards": cards,
        "current": 0,
        "correct": 0,
        "answered": 0,
        "total": count,
        "card_type": None,
        "correct_answer": None,
        "correct_option_index": None,
        "_answered_indices": [],
    }

    return await _show_card(update, ctx, edit_message=query.message)


async def quick_review_command(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    await delete_old_menu(ctx, update.effective_chat.id)
    user_db_id = await _ensure_user(update)
    cards = await get_due_cards(user_db_id, limit=20)

    if not cards:
        earliest = await get_earliest_review(user_db_id)
        if earliest:
            ts = earliest.strftime("%b %d, %H:%M")
            text = f"🎉 No cards due for review! Next review: {ts}."
        else:
            text = "🎉 No cards due! Add some words first."
        await update.message.reply_text(text, reply_markup=BACK_TO_VOCAB)
        return ConversationHandler.END

    count = len(cards)
    ctx.user_data["fc_session"] = {
        "mode": "flashcard",
        "user_db_id": user_db_id,
        "cards": cards,
        "current": 0,
        "correct": 0,
        "answered": 0,
        "total": count,
        "card_type": None,
        "correct_answer": None,
        "correct_option_index": None,
        "_answered_indices": [],
    }

    return await _show_card(update, ctx)


async def quiz_start(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    wc = await count_user_words(user_db_id)
    if wc < 4:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Word", callback_data="vocab_add")],
            [InlineKeyboardButton("◀️ Back", callback_data="menu_vocab")],
        ])
        await query.edit_message_text(
            "You need at least 4 words in your vocabulary to start a quiz. "
            "Add some words first!",
            reply_markup=kb,
        )
        return ConversationHandler.END

    cards = await get_random_user_words(user_db_id, limit=10)
    count = len(cards)

    ctx.user_data["fc_session"] = {
        "mode": "quiz",
        "user_db_id": user_db_id,
        "cards": cards,
        "current": 0,
        "correct": 0,
        "answered": 0,
        "total": count,
        "card_type": None,
        "correct_answer": None,
        "correct_option_index": None,
        "_answered_indices": [],
    }

    return await _show_card(update, ctx, edit_message=query.message)


# ── Answer processing ────────────────────────────────────────────────────────


def _check_text(user_answer: str, correct: str) -> bool:
    u = user_answer.strip().lower()
    c = correct.strip().lower()
    return u == c or levenshtein(u, c) <= 1


def _result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Next →", callback_data="fc_next"),
        InlineKeyboardButton("❌ Quit", callback_data="fc_quit"),
    ]])


async def _handle_answer(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    is_correct: bool,
    correct_answer: str,
    *,
    edit_message=None,
) -> int:
    ses = _session(ctx)
    if not ses:
        text = "Session expired. Please start again."
        if edit_message:
            await edit_message.edit_text(text, reply_markup=BACK_TO_VOCAB)
        else:
            await update.message.reply_text(text, reply_markup=BACK_TO_VOCAB)
        return ConversationHandler.END

    current_idx = ses["current"]

    if current_idx not in ses["_answered_indices"]:
        card = ses["cards"][current_idx]
        if ses["mode"] == "flashcard":
            quality = 4 if is_correct else 1
            ef, interval, reps = sm2_update(
                card["ease_factor"], card["interval_days"], card["repetitions"], quality,
            )
            await update_vocab_progress(card["progress_id"], ef, interval, reps)

        await log_vocab_review(ses["user_db_id"], card["id"], is_correct)
        await update_streak(ses["user_db_id"])

        ses["answered"] += 1
        if is_correct:
            ses["correct"] += 1
        ses["_answered_indices"].append(current_idx)

    answered = ses["answered"]
    total = ses["total"]
    accuracy = round(ses["correct"] / answered * 100) if answered else 0

    if is_correct:
        result = "✅ Correct!"
    else:
        result = f"❌ The answer was: <b>{html.escape(correct_answer)}</b>"

    text = f"{result}\n\nProgress: {answered}/{total} | Session accuracy: {accuracy}%"

    if edit_message:
        await edit_message.edit_text(text, reply_markup=_result_kb(), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=_result_kb(), parse_mode="HTML")

    return FC_WAITING_NEXT


async def show_hint(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    ses = _session(ctx)
    if not ses:
        await query.edit_message_text("Session expired.", reply_markup=BACK_TO_VOCAB)
        return ConversationHandler.END

    hint = ses.get("hint_text", "")
    if not hint:
        return FC_WAITING_ANSWER

    old_text = query.message.text_html
    new_text = old_text + f"\n\n💡 <b>Hint:</b> {html.escape(hint)}"

    old_kb = query.message.reply_markup
    new_rows = []
    for row in old_kb.inline_keyboard:
        new_row = [btn for btn in row if btn.callback_data != "fc_hint"]
        if new_row:
            new_rows.append(new_row)

    await query.edit_message_text(
        new_text,
        reply_markup=InlineKeyboardMarkup(new_rows),
        parse_mode="HTML",
    )
    return FC_WAITING_ANSWER


async def process_text_answer(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    ses = _session(ctx)
    if not ses:
        await update.message.reply_text("Session expired. Please start again.",
                                        reply_markup=BACK_TO_VOCAB)
        return ConversationHandler.END

    if ses["card_type"] in (2, 4):
        await update.message.reply_text("👆 Tap one of the buttons above to answer.")
        return FC_WAITING_ANSWER

    is_correct = _check_text(update.message.text, ses["correct_answer"])
    return await _handle_answer(update, ctx, is_correct, ses["correct_answer"])


async def process_mcq_answer(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    ses = _session(ctx)
    if not ses:
        await query.edit_message_text("Session expired. Please start again.",
                                      reply_markup=BACK_TO_VOCAB)
        return ConversationHandler.END

    selected = int(query.data.split("_")[-1])
    is_correct = selected == ses["correct_option_index"]
    return await _handle_answer(
        update, ctx, is_correct, ses["correct_answer"], edit_message=query.message,
    )


async def process_idk(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    ses = _session(ctx)
    if not ses:
        await query.edit_message_text("Session expired. Please start again.",
                                      reply_markup=BACK_TO_VOCAB)
        return ConversationHandler.END

    return await _handle_answer(
        update, ctx, False, ses["correct_answer"], edit_message=query.message,
    )


# ── Navigation ───────────────────────────────────────────────────────────────


async def _show_summary(
    query, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    ses = _session(ctx)
    answered = ses["answered"]
    correct = ses["correct"]
    accuracy = round(correct / answered * 100) if answered else 0

    lines = [
        "📊 Review Complete!\n",
        f"• Cards reviewed: {answered}",
        f"• Correct: {correct} ({accuracy}%)",
    ]

    if ses["mode"] == "flashcard":
        due = await count_due_tomorrow(ses["user_db_id"])
        lines.append(f"• Cards due tomorrow: {due}")

    await query.message.edit_text(
        "\n".join(lines), reply_markup=BACK_TO_VOCAB, parse_mode="HTML",
    )
    _clear(ctx)
    return ConversationHandler.END


async def show_next_card(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    ses = _session(ctx)
    if not ses:
        await query.edit_message_text("Session expired.", reply_markup=BACK_TO_VOCAB)
        return ConversationHandler.END

    ses["current"] += 1
    if ses["current"] >= ses["total"]:
        return await _show_summary(query, ctx)

    return await _show_card(update, ctx, edit_message=query.message)


async def quit_session(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    ses = _session(ctx)
    if ses and ses["answered"] > 0:
        return await _show_summary(query, ctx)

    _clear(ctx)
    await query.edit_message_text("Session ended.", reply_markup=BACK_TO_VOCAB)
    return ConversationHandler.END


async def cancel_fc(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    _clear(ctx)
    await update.message.reply_text("❌ Session cancelled.", reply_markup=BACK_TO_VOCAB)
    return ConversationHandler.END


# ── ConversationHandler builder ──────────────────────────────────────────────


def build_flashcard_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("review", quick_review_command),
            CallbackQueryHandler(flashcards_start, pattern="^vocab_flashcards$"),
            CallbackQueryHandler(quiz_start, pattern="^vocab_quiz$"),
        ],
        states={
            FC_WAITING_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_text_answer),
                CallbackQueryHandler(process_mcq_answer, pattern=r"^fc_ans_\d$"),
                CallbackQueryHandler(process_idk, pattern="^fc_idk$"),
                CallbackQueryHandler(show_hint, pattern="^fc_hint$"),
                CallbackQueryHandler(quit_session, pattern="^fc_quit$"),
            ],
            FC_WAITING_NEXT: [
                CallbackQueryHandler(show_next_card, pattern="^fc_next$"),
                CallbackQueryHandler(quit_session, pattern="^fc_quit$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_fc),
        ],
        allow_reentry=True,
    )
