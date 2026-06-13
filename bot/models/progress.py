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
