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


# ── Topic generation helpers ──────────────────────────────────────────────


async def get_all_topics_with_rule_titles(user_db_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT t.id, t.name, r.rule_title
           FROM grammar_topics t
           LEFT JOIN grammar_rules r
               ON r.topic_id = t.id AND (r.user_id IS NULL OR r.user_id = $1)
           WHERE t.user_id IS NULL OR t.user_id = $1
           ORDER BY t.id, r.sort_order""",
        user_db_id,
    )
    topics: dict[int, dict] = {}
    for r in rows:
        tid = r["id"]
        if tid not in topics:
            topics[tid] = {"id": tid, "name": r["name"], "rule_titles": []}
        if r["rule_title"]:
            topics[tid]["rule_titles"].append(r["rule_title"])
    return list(topics.values())


async def get_all_progress(user_db_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT gp.topic_id, gt.name AS topic_name,
                  gp.questions_attempted, gp.questions_correct, gp.mastery_level
           FROM grammar_progress gp
           JOIN grammar_topics gt ON gt.id = gp.topic_id
           WHERE gp.user_id = $1
           ORDER BY gt.name""",
        user_db_id,
    )
    return [dict(r) for r in rows]


async def find_duplicate_topic(user_db_id: int, topic_name: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT id, name, user_id FROM grammar_topics
           WHERE (user_id = $1 OR user_id IS NULL)
             AND lower(name) = lower($2)""",
        user_db_id,
        topic_name,
    )
    return dict(row) if row else None


def _topic_keywords(name: str) -> set[str]:
    stop = {"a", "an", "the", "and", "or", "in", "of", "for", "to", "with", "—", "-", "–"}
    words = set()
    for w in name.lower().replace("—", " ").replace("–", " ").replace("-", " ").split():
        w = w.strip(",.:;()[]")
        if w and w not in stop:
            words.add(w)
    return words


async def find_similar_topic(user_db_id: int, topic_name: str) -> dict | None:
    exact = await find_duplicate_topic(user_db_id, topic_name)
    if exact:
        return exact

    pool = get_pool()
    rows = await pool.fetch(
        """SELECT id, name, user_id FROM grammar_topics
           WHERE user_id = $1 OR user_id IS NULL""",
        user_db_id,
    )

    new_kw = _topic_keywords(topic_name)
    if not new_kw:
        return None

    best, best_score = None, 0.0
    for row in rows:
        existing_kw = _topic_keywords(row["name"])
        if not existing_kw:
            continue
        overlap = len(new_kw & existing_kw)
        score = overlap / min(len(new_kw), len(existing_kw))
        if score > best_score:
            best_score = score
            best = row

    if best_score >= 0.5:
        return dict(best)
    return None


async def save_grammar_module(
    user_db_id: int,
    topic_data: dict,
    rules: list[dict],
    questions: list[dict],
    *,
    topic_id: int | None = None,
    rule_indices: set[int] | None = None,
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            sort_offset = 0
            if topic_id is None:
                topic_id = await conn.fetchval(
                    """INSERT INTO grammar_topics
                       (user_id, name, description, skill_tag, band_target)
                       VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                    user_db_id,
                    topic_data["name"],
                    topic_data["description"],
                    topic_data.get("skill_tag", "both"),
                    topic_data.get("band_target", "7"),
                )
                await conn.execute(
                    "INSERT INTO grammar_progress (user_id, topic_id) VALUES ($1, $2)",
                    user_db_id,
                    topic_id,
                )
            else:
                max_order = await conn.fetchval(
                    """SELECT COALESCE(MAX(sort_order), 0)
                       FROM grammar_rules WHERE topic_id = $1""",
                    topic_id,
                )
                sort_offset = max_order

            rule_title_to_id = {}
            for i, rule in enumerate(rules):
                if rule_indices is not None and i not in rule_indices:
                    continue
                rid = await conn.fetchval(
                    """INSERT INTO grammar_rules
                       (user_id, topic_id, rule_title, rule_text,
                        correct_example, incorrect_example, tip, sort_order)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
                    user_db_id,
                    topic_id,
                    rule["rule_title"],
                    rule["rule_text"],
                    rule["correct_example"],
                    rule["incorrect_example"],
                    rule.get("tip", ""),
                    sort_offset + rule.get("sort_order", i + 1),
                )
                rule_title_to_id[rule["rule_title"]] = rid

            for q in questions:
                rid = rule_title_to_id.get(q.get("linked_rule_title"))
                if rid is None:
                    continue
                wrong = json.dumps(q.get("wrong_answers") or [])
                await conn.execute(
                    """INSERT INTO grammar_questions
                       (user_id, rule_id, question_type, prompt,
                        correct_answer, wrong_answers, explanation)
                       VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)""",
                    user_db_id,
                    rid,
                    q["question_type"],
                    q["prompt"],
                    q["correct_answer"],
                    wrong,
                    q.get("explanation", ""),
                )

            return topic_id


async def delete_topic_cascade(topic_id: int, user_db_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """DELETE FROM grammar_questions
                   WHERE rule_id IN (
                       SELECT id FROM grammar_rules
                       WHERE topic_id = $1 AND user_id = $2
                   ) AND user_id = $2""",
                topic_id,
                user_db_id,
            )
            await conn.execute(
                "DELETE FROM grammar_rules WHERE topic_id = $1 AND user_id = $2",
                topic_id,
                user_db_id,
            )
            await conn.execute(
                "DELETE FROM grammar_progress WHERE topic_id = $1 AND user_id = $2",
                topic_id,
                user_db_id,
            )
            await conn.execute(
                "DELETE FROM grammar_topics WHERE id = $1 AND user_id = $2",
                topic_id,
                user_db_id,
            )
