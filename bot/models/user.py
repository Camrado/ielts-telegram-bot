from bot.database import get_pool


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
