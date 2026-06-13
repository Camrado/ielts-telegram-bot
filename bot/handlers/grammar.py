import html
import json
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

from bot.models.grammar import (
    get_all_questions,
    get_all_topics,
    get_or_create_progress,
    get_questions_for_topic,
    get_questions_for_topics,
    get_rules_for_topic,
    get_topic_by_id,
    get_unpracticed_topic_ids,
    get_weak_topic_ids,
    update_progress,
)
from bot.models.user import get_or_create_user
from bot.utils import levenshtein

logger = logging.getLogger(__name__)

# ── States ──────────────────────────────────────────────────────────────────

GQ_WAITING_ANSWER = 30
GQ_WAITING_NEXT = 31

# ── Keyboards ───────────────────────────────────────────────────────────────

GRAMMAR_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📖 Learn", callback_data="grammar_learn")],
    [InlineKeyboardButton("🎯 Quiz", callback_data="grammar_quiz")],
    [InlineKeyboardButton("➕ Add Topic", callback_data="grammar_add_topic")],
    [InlineKeyboardButton("📊 Stats", callback_data="grammar_stats")],
    [InlineKeyboardButton("◀️ Back", callback_data="back_main")],
])

BACK_TO_GRAMMAR = InlineKeyboardMarkup(
    [[InlineKeyboardButton("◀️ Back to Grammar", callback_data="menu_grammar")]]
)

QUIZ_TYPE_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📌 By Topic", callback_data="gquiz_by_topic")],
    [InlineKeyboardButton("🔀 Mixed", callback_data="gquiz_mixed")],
    [InlineKeyboardButton("🔥 Weak Areas", callback_data="gquiz_weak")],
    [InlineKeyboardButton("◀️ Back", callback_data="menu_grammar")],
])

COMING_SOON = "🚧 Coming soon — this feature will be available in the next update."


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _ensure_user(update: Update) -> int:
    user = update.effective_user
    return await get_or_create_user(user.id, user.first_name, user.username)


def _gq_session(ctx: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return ctx.user_data.get("gq_session")


def _gq_clear(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("gq_session", None)


def _learn_state(ctx: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return ctx.user_data.get("grammar_learn")


def _learn_clear(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("grammar_learn", None)


def _normalize_for_compare(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[.!?;:,]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


# ── Grammar menu ────────────────────────────────────────────────────────────


async def grammar_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    _learn_clear(context)
    await query.edit_message_text(
        "📖 <b>Grammar</b>\nChoose an option:",
        reply_markup=GRAMMAR_MENU_KEYBOARD,
        parse_mode="HTML",
    )


async def grammar_stub_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        COMING_SOON,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back", callback_data="menu_grammar")],
        ]),
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════════════════
# LEARN MODE
# ═══════════════════════════════════════════════════════════════════════════


async def _show_topic_list(query, user_db_id: int, *, for_quiz: bool = False) -> None:
    topics = await get_all_topics(user_db_id)
    if not topics:
        await query.edit_message_text(
            "No grammar topics found. Run the seed script first.",
            reply_markup=BACK_TO_GRAMMAR,
            parse_mode="HTML",
        )
        return

    buttons = [
        [InlineKeyboardButton(
            t["name"],
            callback_data=f"{'gquiz_topic' if for_quiz else 'glearn_topic'}_{t['id']}",
        )]
        for t in topics
    ]
    back_data = "grammar_quiz" if for_quiz else "menu_grammar"
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data=back_data)])

    title = "🎯 Choose a topic to quiz:" if for_quiz else "📖 Choose a topic to learn:"
    await query.edit_message_text(
        title,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def learn_topics_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)
    await _show_topic_list(query, user_db_id)


async def _show_rule(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _learn_state(context)
    rules = state["rules"]
    idx = state["current"]
    rule = rules[idx]
    total = len(rules)
    topic_id = state["topic_id"]

    text = (
        f"📖 <b>{html.escape(rule['rule_title'])}</b> ({idx + 1}/{total})\n\n"
        f"📝 <b>Rule:</b> {html.escape(rule['rule_text'])}\n\n"
        f"✅ {html.escape(rule['correct_example'])}\n"
        f"❌ {html.escape(rule['incorrect_example'])}\n\n"
        f"💡 {html.escape(rule['tip'])}"
    )

    nav_row = []
    if idx > 0:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data="glearn_prev"))
    if idx < total - 1:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data="glearn_next"))

    buttons = []
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🎯 Quiz This Topic", callback_data=f"gquiz_topic_{topic_id}")])
    buttons.append([InlineKeyboardButton("◀️ Back to Topics", callback_data="grammar_learn")])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def learn_topic_selected(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    topic_id = int(query.data.split("_")[-1])
    topic = await get_topic_by_id(topic_id, user_db_id)
    if not topic:
        await query.edit_message_text("Topic not found.", reply_markup=BACK_TO_GRAMMAR)
        return

    rules = await get_rules_for_topic(topic_id, user_db_id)
    if not rules:
        await query.edit_message_text(
            "No rules found for this topic.",
            reply_markup=BACK_TO_GRAMMAR,
        )
        return

    context.user_data["grammar_learn"] = {
        "topic_id": topic_id,
        "rules": rules,
        "current": 0,
    }
    await _show_rule(query, context)


async def learn_nav_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    state = _learn_state(context)
    if not state:
        await query.edit_message_text("Session expired.", reply_markup=BACK_TO_GRAMMAR)
        return

    if query.data == "glearn_next":
        state["current"] = min(state["current"] + 1, len(state["rules"]) - 1)
    elif query.data == "glearn_prev":
        state["current"] = max(state["current"] - 1, 0)

    await _show_rule(query, context)


# ═══════════════════════════════════════════════════════════════════════════
# QUIZ MODE
# ═══════════════════════════════════════════════════════════════════════════


async def quiz_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    await _ensure_user(update)
    await query.edit_message_text(
        "🎯 <b>Grammar Quiz</b>\nChoose quiz type:",
        reply_markup=QUIZ_TYPE_KEYBOARD,
        parse_mode="HTML",
    )


async def quiz_by_topic_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)
    await _show_topic_list(query, user_db_id, for_quiz=True)


def _build_session(user_db_id: int, questions: list[dict]) -> dict:
    random.shuffle(questions)
    limit = min(len(questions), 15)
    selected = questions[:limit]
    return {
        "user_db_id": user_db_id,
        "questions": selected,
        "current": 0,
        "correct": 0,
        "answered": 0,
        "total": len(selected),
        "topic_results": {},
        "_answered_indices": [],
    }


async def _start_quiz_with_questions(
    query, context: ContextTypes.DEFAULT_TYPE, user_db_id: int, questions: list[dict]
) -> int:
    if not questions:
        await query.edit_message_text(
            "No questions available for this selection.",
            reply_markup=BACK_TO_GRAMMAR,
        )
        return ConversationHandler.END

    context.user_data["gq_session"] = _build_session(user_db_id, questions)
    return await _show_question(query.message, context)


async def quiz_topic_selected(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)
    _learn_clear(context)

    topic_id = int(query.data.split("_")[-1])
    questions = await get_questions_for_topic(topic_id, user_db_id)
    return await _start_quiz_with_questions(query, context, user_db_id, questions)


async def quiz_mixed_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    questions = await get_all_questions(user_db_id)
    return await _start_quiz_with_questions(query, context, user_db_id, questions)


async def quiz_weak_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    weak_ids = await get_weak_topic_ids(user_db_id)
    unpracticed_ids = await get_unpracticed_topic_ids(user_db_id)
    all_weak = list(set(weak_ids + unpracticed_ids))

    if not all_weak:
        await query.edit_message_text(
            "🎉 No weak areas found! All your practised topics are at 'familiar' or 'mastered' level.\n\n"
            "Try a Mixed quiz to keep practising.",
            reply_markup=QUIZ_TYPE_KEYBOARD,
            parse_mode="HTML",
        )
        return ConversationHandler.END

    questions = await get_questions_for_topics(all_weak, user_db_id)
    return await _start_quiz_with_questions(query, context, user_db_id, questions)


# ── Question display ────────────────────────────────────────────────────────


async def _show_question(
    message, context: ContextTypes.DEFAULT_TYPE
) -> int:
    ses = _gq_session(context)
    q = ses["questions"][ses["current"]]
    qtype = q["question_type"]
    cur = ses["current"] + 1
    total = ses["total"]

    prompt_text = html.escape(q["prompt"])

    if qtype == "fill_blank":
        wrong = q["wrong_answers"]
        if wrong:
            options = [q["correct_answer"]] + list(wrong)
            random.shuffle(options)
            ses["_correct_idx"] = options.index(q["correct_answer"])
            labels = "ABCD"
            option_lines = "\n".join(
                f"<b>{labels[i]}.</b> {html.escape(o)}" for i, o in enumerate(options)
            )
            buttons = [[
                InlineKeyboardButton(labels[i], callback_data=f"gq_ans_{i}")
                for i in range(len(options))
            ]]
            text = f"🎯 Quiz: {cur}/{total}\n\n📝 Fill in the blank:\n\n{prompt_text}\n\n{option_lines}"
            buttons.append([InlineKeyboardButton("❌ Quit", callback_data="gq_quit")])
            await message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML",
            )
        else:
            text = f"🎯 Quiz: {cur}/{total}\n\n📝 Fill in the blank:\n\n{prompt_text}\n\nType your answer:"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Quit", callback_data="gq_quit")]])
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    elif qtype == "correct_or_incorrect":
        text = f"🎯 Quiz: {cur}/{total}\n\n🔍 Is this sentence correct or incorrect?\n\n<i>{prompt_text}</i>"
        buttons = [
            [
                InlineKeyboardButton("✅ Correct", callback_data="gq_ci_correct"),
                InlineKeyboardButton("❌ Incorrect", callback_data="gq_ci_incorrect"),
            ],
            [InlineKeyboardButton("❌ Quit", callback_data="gq_quit")],
        ]
        await message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    elif qtype == "pick_correct":
        wrong = q["wrong_answers"]
        options = [q["correct_answer"]] + list(wrong)
        random.shuffle(options)
        ses["_correct_idx"] = options.index(q["correct_answer"])
        labels = "ABCD"
        option_lines = "\n".join(
            f"<b>{labels[i]}.</b> {html.escape(o)}" for i, o in enumerate(options)
        )
        buttons = [[
            InlineKeyboardButton(labels[i], callback_data=f"gq_ans_{i}")
            for i in range(len(options))
        ]]
        text = f"🎯 Quiz: {cur}/{total}\n\n{prompt_text}\n\n{option_lines}"
        buttons.append([InlineKeyboardButton("❌ Quit", callback_data="gq_quit")])
        await message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    elif qtype == "error_correction":
        text = (
            f"🎯 Quiz: {cur}/{total}\n\n"
            f"✏️ Correct the error in this sentence:\n\n"
            f"<i>{prompt_text}</i>\n\n"
            f"Type the corrected sentence:"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Quit", callback_data="gq_quit")]])
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    return GQ_WAITING_ANSWER


# ── Answer processing ───────────────────────────────────────────────────────


def _result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Next →", callback_data="gq_next"),
        InlineKeyboardButton("❌ Quit", callback_data="gq_quit"),
    ]])


def _record_result(ses: dict, is_correct: bool) -> None:
    q = ses["questions"][ses["current"]]
    topic_id = q.get("topic_id")
    if topic_id is None:
        return
    if topic_id not in ses["topic_results"]:
        ses["topic_results"][topic_id] = {"attempted": 0, "correct": 0}
    ses["topic_results"][topic_id]["attempted"] += 1
    if is_correct:
        ses["topic_results"][topic_id]["correct"] += 1


async def _handle_gq_answer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_correct: bool,
    *,
    almost: bool = False,
    difference: str = "",
    edit_message=None,
) -> int:
    ses = _gq_session(context)
    if not ses:
        text = "Session expired. Please start again."
        if edit_message:
            await edit_message.edit_text(text, reply_markup=BACK_TO_GRAMMAR)
        else:
            await update.message.reply_text(text, reply_markup=BACK_TO_GRAMMAR)
        return ConversationHandler.END

    current_idx = ses["current"]
    q = ses["questions"][current_idx]

    if current_idx not in ses["_answered_indices"]:
        _record_result(ses, is_correct)
        ses["answered"] += 1
        if is_correct:
            ses["correct"] += 1
        ses["_answered_indices"].append(current_idx)

    accuracy = round(ses["correct"] / ses["answered"] * 100) if ses["answered"] else 0

    if almost:
        result = f"🤔 Almost! Check: <b>{html.escape(difference)}</b>\n\nCorrect answer: <b>{html.escape(q['correct_answer'])}</b>"
    elif is_correct:
        result = "✅ Correct!"
    else:
        result = f"❌ Incorrect.\n\nCorrect answer: <b>{html.escape(q['correct_answer'])}</b>"

    explanation = q.get("explanation", "")
    exp_text = f"\n\n💡 {html.escape(explanation)}" if explanation else ""

    text = f"{result}{exp_text}\n\nProgress: {ses['answered']}/{ses['total']} | Accuracy: {accuracy}%"

    if edit_message:
        await edit_message.edit_text(text, reply_markup=_result_kb(), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=_result_kb(), parse_mode="HTML")

    return GQ_WAITING_NEXT


async def process_gq_mcq(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    ses = _gq_session(context)
    if not ses:
        await query.edit_message_text("Session expired.", reply_markup=BACK_TO_GRAMMAR)
        return ConversationHandler.END

    selected = int(query.data.split("_")[-1])
    is_correct = selected == ses.get("_correct_idx")
    return await _handle_gq_answer(
        update, context, is_correct, edit_message=query.message,
    )


async def process_gq_correct_incorrect(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    ses = _gq_session(context)
    if not ses:
        await query.edit_message_text("Session expired.", reply_markup=BACK_TO_GRAMMAR)
        return ConversationHandler.END

    user_choice = "Correct" if query.data == "gq_ci_correct" else "Incorrect"
    q = ses["questions"][ses["current"]]
    is_correct = user_choice == q["correct_answer"]
    return await _handle_gq_answer(
        update, context, is_correct, edit_message=query.message,
    )


async def process_gq_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    ses = _gq_session(context)
    if not ses:
        await update.message.reply_text("Session expired.", reply_markup=BACK_TO_GRAMMAR)
        return ConversationHandler.END

    q = ses["questions"][ses["current"]]
    qtype = q["question_type"]

    is_mcq = qtype not in ("error_correction", "fill_blank")
    if qtype == "fill_blank" and q["wrong_answers"]:
        is_mcq = True
    if is_mcq:
        await update.message.reply_text("👆 Tap one of the buttons above to answer.")
        return GQ_WAITING_ANSWER

    user_text = update.message.text.strip()
    correct = q["correct_answer"]

    if qtype == "error_correction":
        norm_user = _normalize_for_compare(user_text)
        norm_correct = _normalize_for_compare(correct)

        if norm_user == norm_correct:
            return await _handle_gq_answer(update, context, True)

        dist = levenshtein(norm_user, norm_correct)
        if dist <= 2:
            diff_parts = []
            for i, (a, b) in enumerate(zip(norm_user, norm_correct)):
                if a != b:
                    diff_parts.append(f"position {i + 1}: '{a}' should be '{b}'")
            if len(norm_user) != len(norm_correct):
                diff_parts.append("check word length/spacing")
            return await _handle_gq_answer(
                update, context, False,
                almost=True,
                difference=", ".join(diff_parts) if diff_parts else "minor difference",
            )

        return await _handle_gq_answer(update, context, False)

    norm_user = _normalize_for_compare(user_text)
    norm_correct = _normalize_for_compare(correct)
    is_correct = norm_user == norm_correct
    return await _handle_gq_answer(update, context, is_correct)


# ── Navigation ──────────────────────────────────────────────────────────────


async def _show_summary(
    query, context: ContextTypes.DEFAULT_TYPE
) -> int:
    ses = _gq_session(context)
    answered = ses["answered"]
    correct = ses["correct"]
    accuracy = round(correct / answered * 100) if answered else 0

    lines = [
        "📊 <b>Grammar Quiz Complete!</b>\n",
        f"• Questions answered: {answered}",
        f"• Correct: {correct} ({accuracy}%)",
    ]

    user_db_id = ses["user_db_id"]
    for topic_id, results in ses["topic_results"].items():
        await update_progress(
            user_db_id, topic_id,
            results["attempted"], results["correct"],
        )

    if ses["topic_results"]:
        lines.append("\n📈 <b>Topic breakdown:</b>")
        topics = await get_all_topics(user_db_id)
        topic_names = {t["id"]: t["name"] for t in topics}
        for tid, res in ses["topic_results"].items():
            name = topic_names.get(tid, f"Topic {tid}")
            tacc = round(res["correct"] / res["attempted"] * 100) if res["attempted"] else 0
            prog = await get_or_create_progress(user_db_id, tid)
            mastery = prog["mastery_level"].capitalize()
            lines.append(f"  • {name}: {res['correct']}/{res['attempted']} ({tacc}%) — {mastery}")

    await query.message.edit_text(
        "\n".join(lines),
        reply_markup=BACK_TO_GRAMMAR,
        parse_mode="HTML",
    )
    _gq_clear(context)
    return ConversationHandler.END


async def gq_next_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    ses = _gq_session(context)
    if not ses:
        await query.edit_message_text("Session expired.", reply_markup=BACK_TO_GRAMMAR)
        return ConversationHandler.END

    ses["current"] += 1
    if ses["current"] >= ses["total"]:
        return await _show_summary(query, context)

    return await _show_question(query.message, context)


async def gq_quit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    ses = _gq_session(context)
    if ses and ses["answered"] > 0:
        return await _show_summary(query, context)

    _gq_clear(context)
    await query.edit_message_text("Session ended.", reply_markup=BACK_TO_GRAMMAR)
    return ConversationHandler.END


async def gq_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _gq_clear(context)
    await update.message.reply_text("❌ Quiz cancelled.", reply_markup=BACK_TO_GRAMMAR)
    return ConversationHandler.END


# ── ConversationHandler builder ─────────────────────────────────────────────


def build_grammar_quiz_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(quiz_topic_selected, pattern=r"^gquiz_topic_\d+$"),
            CallbackQueryHandler(quiz_mixed_start, pattern="^gquiz_mixed$"),
            CallbackQueryHandler(quiz_weak_start, pattern="^gquiz_weak$"),
        ],
        states={
            GQ_WAITING_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_gq_text),
                CallbackQueryHandler(process_gq_mcq, pattern=r"^gq_ans_\d$"),
                CallbackQueryHandler(process_gq_correct_incorrect, pattern=r"^gq_ci_"),
                CallbackQueryHandler(gq_quit, pattern="^gq_quit$"),
            ],
            GQ_WAITING_NEXT: [
                CallbackQueryHandler(gq_next_card, pattern="^gq_next$"),
                CallbackQueryHandler(gq_quit, pattern="^gq_quit$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", gq_cancel),
        ],
        allow_reentry=True,
    )
