import json

from bot.database import get_pool


# ── Topics ──────────────────────────────────────────────────────────────────


async def get_all_topics(user_db_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT id, name, description
           FROM grammar_topics
           WHERE user_id IS NULL OR user_id = $1
           ORDER BY id""",
        user_db_id,
    )
    return [dict(r) for r in rows]


async def get_topic_by_id(topic_id: int, user_db_id: int) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT id, name, description
           FROM grammar_topics
           WHERE id = $1 AND (user_id IS NULL OR user_id = $2)""",
        topic_id,
        user_db_id,
    )
    return dict(row) if row else None


# ── Rules ───────────────────────────────────────────────────────────────────


async def get_rules_for_topic(topic_id: int, user_db_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT id, rule_title, rule_text, correct_example,
                  incorrect_example, tip, sort_order
           FROM grammar_rules
           WHERE topic_id = $1 AND (user_id IS NULL OR user_id = $2)
           ORDER BY sort_order""",
        topic_id,
        user_db_id,
    )
    return [dict(r) for r in rows]


# ── Questions ───────────────────────────────────────────────────────────────


async def get_questions_for_topic(topic_id: int, user_db_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT q.id, q.rule_id, q.question_type, q.prompt,
                  q.correct_answer, q.wrong_answers, q.explanation,
                  r.topic_id
           FROM grammar_questions q
           JOIN grammar_rules r ON r.id = q.rule_id
           WHERE r.topic_id = $1
             AND (q.user_id IS NULL OR q.user_id = $2)
           ORDER BY random()""",
        topic_id,
        user_db_id,
    )
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d["wrong_answers"], str):
            d["wrong_answers"] = json.loads(d["wrong_answers"])
        result.append(d)
    return result


async def get_all_questions(user_db_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT q.id, q.rule_id, q.question_type, q.prompt,
                  q.correct_answer, q.wrong_answers, q.explanation,
                  r.topic_id
           FROM grammar_questions q
           JOIN grammar_rules r ON r.id = q.rule_id
           WHERE (q.user_id IS NULL OR q.user_id = $1)
           ORDER BY random()""",
        user_db_id,
    )
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d["wrong_answers"], str):
            d["wrong_answers"] = json.loads(d["wrong_answers"])
        result.append(d)
    return result


async def get_questions_for_topics(topic_ids: list[int], user_db_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT q.id, q.rule_id, q.question_type, q.prompt,
                  q.correct_answer, q.wrong_answers, q.explanation,
                  r.topic_id
           FROM grammar_questions q
           JOIN grammar_rules r ON r.id = q.rule_id
           WHERE r.topic_id = ANY($1)
             AND (q.user_id IS NULL OR q.user_id = $2)
           ORDER BY random()""",
        topic_ids,
        user_db_id,
    )
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d["wrong_answers"], str):
            d["wrong_answers"] = json.loads(d["wrong_answers"])
        result.append(d)
    return result


# ── Progress ────────────────────────────────────────────────────────────────


async def get_or_create_progress(user_db_id: int, topic_id: int) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT id, questions_attempted, questions_correct,
                  last_practiced, mastery_level
           FROM grammar_progress
           WHERE user_id = $1 AND topic_id = $2""",
        user_db_id,
        topic_id,
    )
    if row:
        return dict(row)
    row = await pool.fetchrow(
        """INSERT INTO grammar_progress (user_id, topic_id)
           VALUES ($1, $2) RETURNING id, questions_attempted,
           questions_correct, last_practiced, mastery_level""",
        user_db_id,
        topic_id,
    )
    return dict(row)


async def update_progress(
    user_db_id: int,
    topic_id: int,
    additional_attempted: int,
    additional_correct: int,
) -> None:
    pool = get_pool()
    prog = await get_or_create_progress(user_db_id, topic_id)
    new_attempted = prog["questions_attempted"] + additional_attempted
    new_correct = prog["questions_correct"] + additional_correct
    accuracy = new_correct / new_attempted if new_attempted > 0 else 0

    if accuracy >= 0.85:
        mastery = "mastered"
    elif accuracy >= 0.70:
        mastery = "familiar"
    elif accuracy >= 0.50:
        mastery = "learning"
    else:
        mastery = "new"

    await pool.execute(
        """UPDATE grammar_progress
           SET questions_attempted = $1,
               questions_correct = $2,
               mastery_level = $3,
               last_practiced = now()
           WHERE user_id = $4 AND topic_id = $5""",
        new_attempted,
        new_correct,
        mastery,
        user_db_id,
        topic_id,
    )


async def get_weak_topic_ids(user_db_id: int) -> list[int]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT topic_id FROM grammar_progress
           WHERE user_id = $1 AND mastery_level IN ('new', 'learning')""",
        user_db_id,
    )
    return [r["topic_id"] for r in rows]


async def get_unpracticed_topic_ids(user_db_id: int) -> list[int]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT t.id FROM grammar_topics t
           LEFT JOIN grammar_progress gp
               ON gp.topic_id = t.id AND gp.user_id = $1
           WHERE (t.user_id IS NULL OR t.user_id = $1)
             AND gp.id IS NULL""",
        user_db_id,
    )
    return [r["id"] for r in rows]
