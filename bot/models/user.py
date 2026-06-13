from datetime import date, timedelta, timezone, datetime

from bot.database import get_pool

BAKU_TZ = timezone(timedelta(hours=4))


async def get_or_create_user(telegram_user_id: int, first_name: str, username: str | None) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM users WHERE telegram_user_id = $1",
            telegram_user_id,
        )
        if row:
            await conn.execute(
                "UPDATE users SET last_active = now() WHERE id = $1",
                row["id"],
            )
            return row["id"]

        row = await conn.fetchrow(
            """INSERT INTO users (telegram_user_id, first_name, username)
               VALUES ($1, $2, $3)
               RETURNING id""",
            telegram_user_id,
            first_name,
            username,
        )
        return row["id"]


async def update_streak(user_id: int) -> None:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT current_streak, longest_streak, last_review_date
           FROM users WHERE id = $1""",
        user_id,
    )
    if not row:
        return

    today = datetime.now(BAKU_TZ).date()
    last_review = row["last_review_date"]
    streak = row["current_streak"] or 0
    longest = row["longest_streak"] or 0

    if last_review == today:
        await pool.execute(
            "UPDATE users SET last_active_today = true WHERE id = $1",
            user_id,
        )
        return

    if last_review == today - timedelta(days=1):
        streak += 1
    else:
        streak = 1

    longest = max(longest, streak)

    await pool.execute(
        """UPDATE users
           SET current_streak = $1, longest_streak = $2,
               last_review_date = $3, last_active_today = true
           WHERE id = $4""",
        streak, longest, today, user_id,
    )


async def get_user_streak(user_id: int) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT current_streak, longest_streak, last_review_date
           FROM users WHERE id = $1""",
        user_id,
    )
    if not row:
        return {"current_streak": 0, "longest_streak": 0}
    return {
        "current_streak": row["current_streak"] or 0,
        "longest_streak": row["longest_streak"] or 0,
    }
