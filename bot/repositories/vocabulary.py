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
           SET definition   = COALESCE(NULLIF($1, ''), definition),
               synonyms     = COALESCE(NULLIF($2, ''), synonyms),
               collocations = COALESCE(NULLIF($3, ''), collocations),
               example      = COALESCE(NULLIF($4, ''), example),
               cefr_level   = COALESCE(NULLIF($5, ''), cefr_level)
           WHERE id = $6""",
        entry.get("definition") or "",
        entry.get("synonyms") or "",
        entry.get("collocations") or "",
        entry.get("example") or "",
        entry.get("cefr_level") or "",
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


async def count_user_words(user_id: int) -> int:
    pool = get_pool()
    return await pool.fetchval(
        "SELECT COUNT(*) FROM vocabulary WHERE user_id = $1",
        user_id,
    ) or 0


async def get_random_distractors(
    user_id: int, exclude_word_id: int, field: str, limit: int = 3
) -> list[str]:
    allowed = {"definition", "word_phrase", "synonyms"}
    if field not in allowed:
        raise ValueError(f"Invalid field: {field}")
    pool = get_pool()
    rows = await pool.fetch(
        f"""SELECT {field} FROM vocabulary
            WHERE user_id = $1 AND id != $2
              AND {field} IS NOT NULL AND {field} != ''
            ORDER BY random()
            LIMIT $3""",
        user_id,
        exclude_word_id,
        limit,
    )
    return [row[field] for row in rows]


async def get_random_user_words(user_id: int, limit: int = 10) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT id, word_phrase, definition, synonyms, collocations, example, cefr_level
           FROM vocabulary
           WHERE user_id = $1
           ORDER BY random()
           LIMIT $2""",
        user_id,
        limit,
    )
    return [dict(row) for row in rows]


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
