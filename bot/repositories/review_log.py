from bot.database import get_pool


async def log_vocab_review(user_id: int, word_id: int, correct: bool) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO review_log (user_id, word_id, category, correct)
           VALUES ($1, $2, 'vocab', $3)""",
        user_id, word_id, correct,
    )


async def log_grammar_review(user_id: int, question_id: int, correct: bool) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO review_log (user_id, question_id, category, correct)
           VALUES ($1, $2, 'grammar', $3)""",
        user_id, question_id, correct,
    )


async def get_vocab_stats_7days(user_id: int) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT COUNT(*) AS reviewed,
                  COUNT(*) FILTER (WHERE correct) AS correct_count
           FROM review_log
           WHERE user_id = $1
             AND category = 'vocab'
             AND reviewed_at > now() - interval '7 days'""",
        user_id,
    )
    reviewed = row["reviewed"] or 0
    correct = row["correct_count"] or 0
    accuracy = round(correct / reviewed * 100) if reviewed else 0
    return {"reviewed": reviewed, "correct": correct, "accuracy": accuracy}


async def get_grammar_stats_7days(user_id: int) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT COUNT(*) AS answered,
                  COUNT(*) FILTER (WHERE correct) AS correct_count
           FROM review_log
           WHERE user_id = $1
             AND category = 'grammar'
             AND reviewed_at > now() - interval '7 days'""",
        user_id,
    )
    answered = row["answered"] or 0
    correct = row["correct_count"] or 0
    accuracy = round(correct / answered * 100) if answered else 0
    return {"answered": answered, "correct": correct, "accuracy": accuracy}


async def get_new_words_7days(user_id: int) -> int:
    pool = get_pool()
    return await pool.fetchval(
        """SELECT COUNT(*) FROM vocabulary
           WHERE user_id = $1
             AND created_at > now() - interval '7 days'""",
        user_id,
    ) or 0
