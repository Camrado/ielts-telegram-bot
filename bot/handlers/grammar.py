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
    delete_topic_cascade,
    find_duplicate_topic,
    get_all_progress,
    get_all_questions,
    get_all_topics,
    get_or_create_progress,
    get_questions_for_topic,
    get_questions_for_topics,
    get_rules_for_topic,
    get_topic_by_id,
    get_unpracticed_topic_ids,
    get_weak_topic_ids,
    save_grammar_module,
    update_progress,
)
from bot.models.review_log import get_grammar_stats_7days, log_grammar_review
from bot.models.user import get_or_create_user, update_streak
from bot.services.ai import generate_grammar_module
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


MASTERY_EMOJI = {
    "new": "🆕",
    "learning": "📖",
    "familiar": "📗",
    "mastered": "✅",
}


async def grammar_stats_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)

    all_topics = await get_all_topics(user_db_id)
    progress_list = await get_all_progress(user_db_id)

    total_topics = len(all_topics)
    mastered = sum(1 for p in progress_list if p["mastery_level"] == "mastered")
    in_progress = sum(1 for p in progress_list if p["mastery_level"] in ("learning", "familiar"))

    topic_lines = []
    for p in progress_list:
        emoji = MASTERY_EMOJI.get(p["mastery_level"], "🆕")
        attempted = p["questions_attempted"]
        correct = p["questions_correct"]
        acc = round(correct / attempted * 100) if attempted else 0
        topic_lines.append(
            f"  • {p['topic_name']}: {emoji} {acc}% ({attempted} questions)"
        )

    week = await get_grammar_stats_7days(user_db_id)

    text = (
        "📊 <b>Grammar Statistics</b>\n\n"
        f"📖 Topics: {total_topics} ({mastered} mastered, {in_progress} in progress)\n\n"
    )

    if topic_lines:
        text += "<b>Topic Breakdown:</b>\n" + "\n".join(topic_lines) + "\n\n"

    text += (
        "📈 <b>Last 7 days:</b>\n"
        f"  • Questions answered: {week['answered']}\n"
        f"  • Accuracy: {week['accuracy']}%"
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Back", callback_data="menu_grammar")]]
    )
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


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
        await log_grammar_review(ses["user_db_id"], q["id"], is_correct)
        await update_streak(ses["user_db_id"])
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


# ═══════════════════════════════════════════════════════════════════════════
# ADD TOPIC MODE (AI generation)
# ═══════════════════════════════════════════════════════════════════════════

GAT_WAITING_DESC = 40
GAT_PREVIEW = 41
GAT_PREVIEW_MORE = 42
GAT_DUPLICATE = 43
GAT_WAITING_RENAME = 44


def _gat_pending(ctx: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return ctx.user_data.get("gat_pending")


def _gat_clear(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("gat_pending", None)


# ── Display helpers ────────────────────────────────────────────────────────


def _gat_build_rule_page(pending: dict) -> tuple[str, InlineKeyboardMarkup]:
    idx = pending["current_rule_idx"]
    rules = pending["rules"]
    rule = rules[idx]
    total = len(rules)
    saved = pending["saved_rule_indices"]
    is_saved = idx in saved

    title_suffix = " ✅" if is_saved else ""
    text = (
        f"📖 Rule {idx + 1}/{total}: "
        f"<b>{html.escape(rule.get('rule_title', 'Untitled'))}{title_suffix}</b>\n\n"
        f"📝 {html.escape(rule.get('rule_text', ''))}\n\n"
        f"✅ {html.escape(rule.get('correct_example', ''))}\n"
        f"❌ {html.escape(rule.get('incorrect_example', ''))}\n\n"
        f"💡 {html.escape(rule.get('tip', ''))}"
    )

    nav_row = []
    if idx > 0:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data="gat_prev"))
    if idx < total - 1:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data="gat_next"))

    action_row = []
    if is_saved:
        action_row.append(InlineKeyboardButton("✅ Saved", callback_data="gat_noop"))
    else:
        action_row.append(InlineKeyboardButton("✅ Save", callback_data="gat_save_single"))

    unsaved_count = sum(1 for i in range(total) if i not in saved)
    if unsaved_count > 0:
        action_row.append(
            InlineKeyboardButton(
                f"✅ Save All ({unsaved_count})", callback_data="gat_save_all"
            )
        )

    buttons = []
    if nav_row:
        buttons.append(nav_row)
    buttons.append(action_row)
    buttons.append([InlineKeyboardButton("❌ Discard", callback_data="gat_discard")])

    return text, InlineKeyboardMarkup(buttons)


async def _gat_show_initial_preview(message, pending: dict) -> None:
    topic = pending["topic"]
    rules = pending["rules"]
    questions = pending["questions"]
    rule = rules[0]

    text = (
        f"📝 Generated: \"<b>{html.escape(topic.get('name', ''))}</b>\"\n"
        f"📖 {html.escape(topic.get('description', ''))}\n\n"
        f"{len(rules)} rules, {len(questions)} questions\n\n"
        f"Preview of first rule:\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{html.escape(rule.get('rule_title', ''))}</b>\n\n"
        f"{html.escape(rule.get('rule_text', ''))}\n\n"
        f"✅ {html.escape(rule.get('correct_example', ''))}\n"
        f"❌ {html.escape(rule.get('incorrect_example', ''))}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Save All", callback_data="gat_save_all"),
            InlineKeyboardButton("📝 Preview More", callback_data="gat_preview_more"),
        ],
        [InlineKeyboardButton("❌ Discard", callback_data="gat_discard")],
    ])

    await message.edit_text(text, reply_markup=kb, parse_mode="HTML")


async def _gat_respond(text, reply_markup, *, edit_msg=None, reply_msg=None):
    if edit_msg:
        await edit_msg.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await reply_msg.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")


# ── Save logic ─────────────────────────────────────────────────────────────


async def _gat_execute_save(
    context: ContextTypes.DEFAULT_TYPE,
    save_mode: str,
    *,
    edit_msg=None,
    reply_msg=None,
) -> int:
    pending = _gat_pending(context)
    user_db_id = pending["user_db_id"]
    topic = pending["topic"]
    rules = pending["rules"]
    questions = pending["questions"]
    saved = set(pending["saved_rule_indices"])

    try:
        if save_mode == "all":
            unsaved = set(range(len(rules))) - saved
            if not unsaved:
                await _gat_respond(
                    "✅ All rules already saved!",
                    BACK_TO_GRAMMAR,
                    edit_msg=edit_msg,
                    reply_msg=reply_msg,
                )
                _gat_clear(context)
                return ConversationHandler.END

            indices = unsaved if saved else None
            topic_id = await save_grammar_module(
                user_db_id,
                topic,
                rules,
                questions,
                topic_id=pending["topic_db_id"],
                rule_indices=indices,
            )
            _gat_clear(context)
            await _gat_respond(
                f"✅ Saved! '<b>{html.escape(topic['name'])}</b>' is now available "
                f"in your Learn and Quiz sections.",
                BACK_TO_GRAMMAR,
                edit_msg=edit_msg,
                reply_msg=reply_msg,
            )
            return ConversationHandler.END

        idx = pending["current_rule_idx"]
        if idx in saved:
            return GAT_PREVIEW_MORE

        topic_id = await save_grammar_module(
            user_db_id,
            topic,
            rules,
            questions,
            topic_id=pending["topic_db_id"],
            rule_indices={idx},
        )
        pending["topic_db_id"] = topic_id
        pending["saved_rule_indices"].append(idx)

        text, kb = _gat_build_rule_page(pending)
        await _gat_respond(text, kb, edit_msg=edit_msg, reply_msg=reply_msg)
        return GAT_PREVIEW_MORE

    except Exception as e:
        logger.error("Failed to save grammar module: %s", e)
        await _gat_respond(
            "❌ Failed to save. Please try again.",
            BACK_TO_GRAMMAR,
            edit_msg=edit_msg,
            reply_msg=reply_msg,
        )
        _gat_clear(context)
        return ConversationHandler.END


async def _gat_show_duplicate_warning(
    pending: dict, dup: dict, *, edit_msg=None, reply_msg=None
) -> None:
    is_global = dup.get("user_id") is None
    pending["duplicate_id"] = dup["id"]
    pending["duplicate_is_global"] = is_global

    if is_global:
        text = (
            f"⚠️ A built-in topic named '<b>{html.escape(dup['name'])}</b>' "
            f"already exists.\n\nYou can save with a different name or cancel."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Save as New (rename)", callback_data="gat_dup_rename")],
            [InlineKeyboardButton("❌ Cancel", callback_data="gat_dup_cancel")],
        ])
    else:
        text = (
            f"⚠️ A topic named '<b>{html.escape(dup['name'])}</b>' already exists."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Replace Existing", callback_data="gat_dup_replace")],
            [InlineKeyboardButton("📝 Save as New (rename)", callback_data="gat_dup_rename")],
            [InlineKeyboardButton("❌ Cancel", callback_data="gat_dup_cancel")],
        ])

    await _gat_respond(text, kb, edit_msg=edit_msg, reply_msg=reply_msg)


async def _gat_check_and_save(
    context: ContextTypes.DEFAULT_TYPE,
    save_mode: str,
    *,
    edit_msg=None,
    reply_msg=None,
) -> int:
    pending = _gat_pending(context)
    pending["save_mode"] = save_mode

    if pending["topic_db_id"] is None:
        dup = await find_duplicate_topic(
            pending["user_db_id"], pending["topic"]["name"]
        )
        if dup:
            await _gat_show_duplicate_warning(
                pending, dup, edit_msg=edit_msg, reply_msg=reply_msg
            )
            return GAT_DUPLICATE

    return await _gat_execute_save(
        context, save_mode, edit_msg=edit_msg, reply_msg=reply_msg
    )


# ── Entry point ────────────────────────────────────────────────────────────


async def gat_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    user_db_id = await _ensure_user(update)
    context.user_data["gat_pending"] = {"user_db_id": user_db_id}
    await query.edit_message_text(
        "Describe the grammar topic you want to study. "
        "You can be brief or detailed:\n\n"
        "• Brief: <i>punctuation</i>\n"
        "• Specific: <i>comma splices and run-on sentences</i>\n"
        "• Detailed: <i>I keep making mistakes with articles before "
        "abstract nouns like education, society, technology in Task 2. "
        "I write 'the education' when it should be 'education'.</i>\n\n"
        "The more detail you give, the more targeted the content.\n\n"
        "Send /cancel to go back.",
        parse_mode="HTML",
    )
    return GAT_WAITING_DESC


# ── Description received ──────────────────────────────────────────────────


async def gat_receive_description(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    pending = _gat_pending(context)
    if not pending:
        await update.message.reply_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END

    description = update.message.text.strip()
    msg = await update.message.reply_text("⏳ Generating grammar module...")

    try:
        data = await generate_grammar_module(description)
    except Exception as e:
        logger.error("Grammar module generation failed: %s", e)
        await msg.edit_text(
            "❌ Failed to generate grammar module. "
            "Please try again with a different description, "
            "or send /cancel to go back."
        )
        return GAT_WAITING_DESC

    topic = data.get("topic", {})
    rules = data.get("rules", [])
    questions = data.get("questions", [])

    if not rules:
        await msg.edit_text(
            "❌ No rules were generated. "
            "Please try a different description, or send /cancel to go back."
        )
        return GAT_WAITING_DESC

    pending.update({
        "topic": topic,
        "rules": rules,
        "questions": questions,
        "current_rule_idx": 0,
        "saved_rule_indices": [],
        "topic_db_id": None,
        "save_mode": None,
    })

    await _gat_show_initial_preview(msg, pending)
    return GAT_PREVIEW


# ── Preview actions ────────────────────────────────────────────────────────


async def gat_save_all(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    pending = _gat_pending(context)
    if not pending or "rules" not in pending:
        await query.edit_message_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END
    return await _gat_check_and_save(context, "all", edit_msg=query.message)


async def gat_preview_more(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    pending = _gat_pending(context)
    if not pending or "rules" not in pending:
        await query.edit_message_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END

    pending["current_rule_idx"] = 1 if len(pending["rules"]) > 1 else 0
    text, kb = _gat_build_rule_page(pending)
    await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    return GAT_PREVIEW_MORE


async def gat_discard(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    pending = _gat_pending(context)
    saved_count = len(pending.get("saved_rule_indices", [])) if pending else 0
    _gat_clear(context)

    if saved_count > 0:
        text = (
            f"Remaining rules discarded. "
            f"{saved_count} previously saved rule(s) remain."
        )
    else:
        text = "❌ Discarded."

    await query.edit_message_text(text, reply_markup=BACK_TO_GRAMMAR)
    return ConversationHandler.END


# ── Preview More navigation ───────────────────────────────────────────────


async def gat_nav(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    pending = _gat_pending(context)
    if not pending or "rules" not in pending:
        await query.edit_message_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END

    if query.data == "gat_next":
        pending["current_rule_idx"] = min(
            pending["current_rule_idx"] + 1, len(pending["rules"]) - 1
        )
    elif query.data == "gat_prev":
        pending["current_rule_idx"] = max(pending["current_rule_idx"] - 1, 0)

    text, kb = _gat_build_rule_page(pending)
    await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    return GAT_PREVIEW_MORE


async def gat_save_single(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    pending = _gat_pending(context)
    if not pending or "rules" not in pending:
        await query.edit_message_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END
    return await _gat_check_and_save(context, "single", edit_msg=query.message)


async def gat_noop(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer("Already saved!")
    return GAT_PREVIEW_MORE


# ── Duplicate handling ─────────────────────────────────────────────────────


async def gat_dup_replace(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    pending = _gat_pending(context)
    if not pending:
        await query.edit_message_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END

    try:
        await delete_topic_cascade(pending["duplicate_id"], pending["user_db_id"])
    except Exception as e:
        logger.error("Failed to delete existing topic: %s", e)
        await query.edit_message_text(
            "❌ Failed to replace. Please try again.",
            reply_markup=BACK_TO_GRAMMAR,
        )
        _gat_clear(context)
        return ConversationHandler.END

    pending.pop("duplicate_id", None)
    return await _gat_execute_save(
        context, pending["save_mode"], edit_msg=query.message
    )


async def gat_dup_rename(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    pending = _gat_pending(context)
    if not pending:
        await query.edit_message_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "Type a new name for this topic:\n\nSend /cancel to go back.",
        parse_mode="HTML",
    )
    return GAT_WAITING_RENAME


async def gat_dup_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    pending = _gat_pending(context)
    if not pending or "rules" not in pending:
        await query.edit_message_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END

    await _gat_show_initial_preview(query.message, pending)
    return GAT_PREVIEW


async def gat_receive_rename(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    pending = _gat_pending(context)
    if not pending:
        await update.message.reply_text(
            "Session expired.", reply_markup=BACK_TO_GRAMMAR
        )
        return ConversationHandler.END

    new_name = update.message.text.strip()
    pending["topic"]["name"] = new_name

    dup = await find_duplicate_topic(pending["user_db_id"], new_name)
    if dup:
        await _gat_show_duplicate_warning(
            pending, dup, reply_msg=update.message
        )
        return GAT_DUPLICATE

    return await _gat_execute_save(
        context, pending["save_mode"], reply_msg=update.message
    )


# ── Cancel ─────────────────────────────────────────────────────────────────


async def gat_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _gat_clear(context)
    await update.message.reply_text("❌ Cancelled.", reply_markup=BACK_TO_GRAMMAR)
    return ConversationHandler.END


# ── ConversationHandler builder ────────────────────────────────────────────


def build_grammar_add_topic_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(gat_start, pattern="^grammar_add_topic$"),
        ],
        states={
            GAT_WAITING_DESC: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, gat_receive_description
                ),
            ],
            GAT_PREVIEW: [
                CallbackQueryHandler(gat_save_all, pattern="^gat_save_all$"),
                CallbackQueryHandler(
                    gat_preview_more, pattern="^gat_preview_more$"
                ),
                CallbackQueryHandler(gat_discard, pattern="^gat_discard$"),
            ],
            GAT_PREVIEW_MORE: [
                CallbackQueryHandler(gat_nav, pattern=r"^gat_(prev|next)$"),
                CallbackQueryHandler(
                    gat_save_single, pattern="^gat_save_single$"
                ),
                CallbackQueryHandler(gat_save_all, pattern="^gat_save_all$"),
                CallbackQueryHandler(gat_discard, pattern="^gat_discard$"),
                CallbackQueryHandler(gat_noop, pattern="^gat_noop$"),
            ],
            GAT_DUPLICATE: [
                CallbackQueryHandler(
                    gat_dup_replace, pattern="^gat_dup_replace$"
                ),
                CallbackQueryHandler(
                    gat_dup_rename, pattern="^gat_dup_rename$"
                ),
                CallbackQueryHandler(
                    gat_dup_cancel, pattern="^gat_dup_cancel$"
                ),
            ],
            GAT_WAITING_RENAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, gat_receive_rename
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", gat_cancel),
        ],
        allow_reentry=True,
    )
