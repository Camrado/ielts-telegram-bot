import asyncio
import logging
from datetime import timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

from bot.database import get_pool
from bot.repositories.progress import count_due_now

logger = logging.getLogger(__name__)

BAKU_TZ = timezone(timedelta(hours=4))

_scheduler: AsyncIOScheduler | None = None

REMINDER_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📚 Start Review", callback_data="vocab_flashcards"),
        InlineKeyboardButton("📖 Grammar Quiz", callback_data="gquiz_mixed"),
    ],
])

REMINDER_MESSAGES = {
    "morning": lambda due, streak: (
        f"☀️ Good morning! You have {due} vocabulary cards due for review.\n"
        + (f"🔥 Keep your {streak}-day streak alive!\n" if streak > 0 else "")
    ),
    "afternoon": lambda due, streak: (
        f"📚 Quick afternoon check-in — {due} cards are waiting.\n"
        "A 5-minute session on your commute makes a difference.\n"
    ),
    "evening": lambda due, streak: (
        f"🌆 Evening study time? You still have {due} cards due today.\n"
        + (f"Don't break your {streak}-day streak!\n" if streak > 0 else "")
    ),
    "last_call": lambda due, streak: (
        f"🌙 Last reminder for today — {due} cards still due.\n"
        "Even 5 cards is better than zero.\n"
    ),
}


async def send_reminders(bot, reminder_slot: str) -> None:
    logger.info("Reminder job fired for slot: %s", reminder_slot)
    try:
        pool = get_pool()
    except RuntimeError:
        logger.warning("DB pool not ready, skipping reminder")
        return

    rows = await pool.fetch(
        """SELECT id, telegram_user_id, last_active_today,
                  current_streak, reminders_enabled
           FROM users"""
    )
    logger.info("Reminder slot %s — %d users fetched", reminder_slot, len(rows))

    for user in rows:
        if not user["reminders_enabled"]:
            logger.debug("User %d: reminders disabled, skipping", user["telegram_user_id"])
            continue
        if user["last_active_today"]:
            logger.debug("User %d: already active today, skipping", user["telegram_user_id"])
            continue

        user_id = user["id"]
        telegram_id = user["telegram_user_id"]
        streak = user["current_streak"] or 0

        try:
            has_content = await pool.fetchval(
                """SELECT EXISTS(
                       SELECT 1 FROM vocabulary WHERE user_id = $1
                   ) OR EXISTS(
                       SELECT 1 FROM grammar_progress WHERE user_id = $1
                   )""",
                user_id,
            )
            if not has_content:
                continue

            due = await count_due_now(user_id)

            if due == 0 and reminder_slot != "morning":
                continue

            msg_fn = REMINDER_MESSAGES[reminder_slot]
            text = msg_fn(due, streak)

            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=REMINDER_KEYBOARD,
            )
        except Forbidden:
            logger.info("User %d blocked the bot, skipping reminder", telegram_id)
        except Exception:
            logger.exception("Failed to send reminder to user %d", telegram_id)

        await asyncio.sleep(0.05)


async def reset_daily_activity() -> None:
    try:
        pool = get_pool()
        await pool.execute("UPDATE users SET last_active_today = false")
        logger.info("Daily activity flag reset for all users")
    except Exception:
        logger.exception("Failed to reset daily activity")


def setup_scheduler(bot) -> AsyncIOScheduler:
    global _scheduler

    scheduler = AsyncIOScheduler()

    for hour, slot in [(10, "morning"), (14, "afternoon"), (19, "evening"), (21, "last_call")]:
        scheduler.add_job(
            send_reminders,
            CronTrigger(hour=hour, minute=0, timezone=BAKU_TZ),
            args=[bot, slot],
            id=f"reminder_{slot}",
            replace_existing=True,
        )

    scheduler.add_job(
        reset_daily_activity,
        CronTrigger(hour=0, minute=0, timezone=BAKU_TZ),
        id="daily_reset",
        replace_existing=True,
    )

    scheduler.start()
    _scheduler = scheduler

    for job in scheduler.get_jobs():
        logger.info("Scheduled job %s — next fire: %s", job.id, job.next_run_time)

    return scheduler
