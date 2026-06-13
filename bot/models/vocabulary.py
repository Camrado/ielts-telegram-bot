import logging

from bot.database import get_pool

logger = logging.getLogger(__name__)


async def find_duplicate(user_id: int, word_phrase: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT id, word_phrase, definition, synonyms
           FROM vocabulary
           WHERE user_id = $1 AND lower(trim(word_phrase)) = lower(trim($2))""",
        user_id,
        word_phrase,
    )
    return dict(row) if row else None


async def insert_word(user_id: int, entry: dict) -> int:
    pool = get_pool()
    return await pool.fetchval(
        """INSERT INTO vocabulary
               (user_id, word_phrase, definition, synonyms, collocations, example, cefr_level)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           RETURNING id""",
        user_id,
        entry["word_phrase"],
        entry.get("definition"),
        entry.get("synonyms"),
        entry.get("collocations"),
        entry.get("example"),
        entry.get("cefr_level"),
    )


async def update_word(word_id: int, entry: dict) -> None:
    pool = get_pool()
    await pool.execute(
        """UPDATE vocabulary
           SET definition = $1, synonyms = $2, collocations = $3,
               example = $4, cefr_level = $5
           WHERE id = $6""",
        entry.get("definition"),
        entry.get("synonyms"),
        entry.get("collocations"),
        entry.get("example"),
        entry.get("cefr_level"),
        word_id,
    )


async def check_duplicates_bulk(user_id: int, words: list[str]) -> set[str]:
    pool = get_pool()
    lowered = [w.lower().strip() for w in words]
    rows = await pool.fetch(
        """SELECT lower(word_phrase) AS w
           FROM vocabulary
           WHERE user_id = $1 AND lower(word_phrase) = ANY($2::text[])""",
        user_id,
        lowered,
    )
    return {row["w"] for row in rows}


async def insert_words_bulk(user_id: int, entries: list[dict]) -> list[int]:
    pool = get_pool()
    word_ids = []
    async with pool.acquire() as conn, conn.transaction():
        for entry in entries:
            word_id = await conn.fetchval(
                """INSERT INTO vocabulary
                       (user_id, word_phrase, definition, synonyms,
                        collocations, example, cefr_level)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)
                   ON CONFLICT (user_id, lower(word_phrase)) DO NOTHING
                   RETURNING id""",
                user_id,
                entry["word_phrase"],
                entry.get("definition"),
                entry.get("synonyms"),
                entry.get("collocations"),
                entry.get("example"),
                entry.get("cefr_level"),
            )
            if word_id is not None:
                word_ids.append(word_id)
    return word_ids
