from datetime import datetime

from bot.database import get_pool


async def create_vocab_progress(user_id: int, word_id: int) -> int:
    pool = get_pool()
    return await pool.fetchval(
        """INSERT INTO vocab_progress
               (user_id, word_id, ease_factor, interval_days, repetitions, next_review)
           VALUES ($1, $2, 2.5, 0, 0, now())
           RETURNING id""",
        user_id,
        word_id,
    )


async def get_due_cards(user_id: int, limit: int = 20) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT v.id, v.word_phrase, v.definition, v.synonyms, v.collocations,
                  v.example, v.cefr_level,
                  vp.id AS progress_id, vp.ease_factor, vp.interval_days, vp.repetitions
           FROM vocabulary v
           JOIN vocab_progress vp ON v.id = vp.word_id
           WHERE vp.user_id = $1 AND vp.next_review <= now()
           ORDER BY vp.next_review ASC
           LIMIT $2""",
        user_id,
        limit,
    )
    return [dict(row) for row in rows]


async def get_earliest_review(user_id: int) -> datetime | None:
    pool = get_pool()
    return await pool.fetchval(
        """SELECT MIN(next_review) FROM vocab_progress
           WHERE user_id = $1 AND next_review > now()""",
        user_id,
    )


async def update_vocab_progress(
    progress_id: int,
    ease_factor: float,
    interval_days: int,
    repetitions: int,
) -> None:
    pool = get_pool()
    await pool.execute(
        """UPDATE vocab_progress
           SET ease_factor = $1, interval_days = $2, repetitions = $3,
               next_review = now() + make_interval(days => $2),
               last_reviewed = now()
           WHERE id = $4""",
        ease_factor,
        interval_days,
        repetitions,
        progress_id,
    )


async def count_due_tomorrow(user_id: int) -> int:
    pool = get_pool()
    return await pool.fetchval(
        """SELECT COUNT(*) FROM vocab_progress
           WHERE user_id = $1 AND next_review::date <= CURRENT_DATE + 1""",
        user_id,
    ) or 0
