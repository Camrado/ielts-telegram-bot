import logging
import asyncpg
from bot.config import DATABASE_URL

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    logger.info("Database connection pool created")
    return pool


async def close_pool() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("Database connection pool closed")


def get_pool() -> asyncpg.Pool:
    if pool is None:
        raise RuntimeError("Database pool is not initialized — call create_pool() first")
    return pool


async def init_db() -> None:
    p = get_pool()
    async with p.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              serial PRIMARY KEY,
                telegram_user_id bigint UNIQUE NOT NULL,
                first_name      text,
                username        text,
                created_at      timestamp DEFAULT now(),
                last_active     timestamp DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS vocabulary (
                id              serial PRIMARY KEY,
                user_id         int NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                word_phrase     text NOT NULL,
                definition      text,
                synonyms        text,
                collocations    text,
                example         text,
                cefr_level      text,
                created_at      timestamp DEFAULT now()
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_vocabulary_user_word
                ON vocabulary (user_id, lower(word_phrase));

            CREATE TABLE IF NOT EXISTS vocab_progress (
                id              serial PRIMARY KEY,
                user_id         int NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                word_id         int NOT NULL REFERENCES vocabulary(id) ON DELETE CASCADE,
                ease_factor     float DEFAULT 2.5,
                interval_days   int DEFAULT 0,
                repetitions     int DEFAULT 0,
                next_review     timestamp DEFAULT now(),
                last_reviewed   timestamp
            );

            CREATE TABLE IF NOT EXISTS grammar_topics (
                id              serial PRIMARY KEY,
                user_id         int REFERENCES users(id) ON DELETE CASCADE,
                name            text NOT NULL,
                description     text,
                skill_tag       text,
                band_target     text,
                created_at      timestamp DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS grammar_rules (
                id              serial PRIMARY KEY,
                user_id         int REFERENCES users(id) ON DELETE CASCADE,
                topic_id        int NOT NULL REFERENCES grammar_topics(id) ON DELETE CASCADE,
                rule_title      text NOT NULL,
                rule_text       text NOT NULL,
                correct_example text,
                incorrect_example text,
                tip             text,
                sort_order      int DEFAULT 0,
                created_at      timestamp DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS grammar_questions (
                id              serial PRIMARY KEY,
                user_id         int REFERENCES users(id) ON DELETE CASCADE,
                rule_id         int NOT NULL REFERENCES grammar_rules(id) ON DELETE CASCADE,
                question_type   text NOT NULL,
                prompt          text NOT NULL,
                correct_answer  text NOT NULL,
                wrong_answers   jsonb DEFAULT '[]',
                explanation     text,
                created_at      timestamp DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS grammar_progress (
                id              serial PRIMARY KEY,
                user_id         int NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                topic_id        int NOT NULL REFERENCES grammar_topics(id) ON DELETE CASCADE,
                questions_attempted int DEFAULT 0,
                questions_correct   int DEFAULT 0,
                last_practiced  timestamp,
                mastery_level   text DEFAULT 'new'
            );

            CREATE TABLE IF NOT EXISTS grammar_structures (
                id              serial PRIMARY KEY,
                user_id         int REFERENCES users(id) ON DELETE CASCADE,
                topic_id        int REFERENCES grammar_topics(id) ON DELETE CASCADE,
                structure_name  text NOT NULL,
                pattern         text,
                explanation     text,
                example_writing text,
                example_speaking text,
                band_target     text,
                created_at      timestamp DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS review_log (
                id              serial PRIMARY KEY,
                user_id         int NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                word_id         int REFERENCES vocabulary(id) ON DELETE SET NULL,
                question_id     int REFERENCES grammar_questions(id) ON DELETE SET NULL,
                category        text NOT NULL,
                correct         boolean NOT NULL,
                reviewed_at     timestamp DEFAULT now()
            );
        """)

        for col, definition in [
            ("current_streak", "int DEFAULT 0"),
            ("longest_streak", "int DEFAULT 0"),
            ("last_review_date", "date"),
            ("last_active_today", "boolean DEFAULT false"),
            ("reminders_enabled", "boolean DEFAULT true"),
        ]:
            try:
                await conn.execute(
                    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}"
                )
            except Exception:
                pass

    logger.info("Database tables initialized")
