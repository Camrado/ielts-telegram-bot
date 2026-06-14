import asyncio
import functools
import logging

logger = logging.getLogger(__name__)


_FORCE_NEW = "_force_new_menu"


def with_retry(retries=2, delay=1.0):
    """Retry a callback/command handler on transient failures."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            for attempt in range(retries + 1):
                try:
                    result = await func(update, context, *args, **kwargs)
                    wait_msg = getattr(update, "_retry_wait_msg", None)
                    if wait_msg:
                        try:
                            await wait_msg.delete()
                        except Exception:
                            pass
                    context.user_data.pop(_FORCE_NEW, None)
                    return result
                except Exception:
                    if attempt < retries:
                        logger.warning(
                            "Retry %d/%d for %s",
                            attempt + 1, retries, func.__name__,
                        )
                        q = update.callback_query
                        if q and not getattr(q, "_patched", False):
                            q._patched = True
                            _real = q.answer
                            async def _safe(*a, _f=_real, **kw):
                                try:
                                    return await _f(*a, **kw)
                                except Exception:
                                    return True
                            q.answer = _safe
                        chat = update.effective_chat
                        if chat and not getattr(update, "_retry_wait_msg", None):
                            try:
                                update._retry_wait_msg = (
                                    await context.bot.send_message(
                                        chat_id=chat.id,
                                        text="⏳ Taking a bit longer than usual, please wait…",
                                    )
                                )
                            except Exception:
                                pass
                        context.user_data[_FORCE_NEW] = True
                        await asyncio.sleep(delay)
                    else:
                        wait_msg = getattr(update, "_retry_wait_msg", None)
                        if wait_msg:
                            try:
                                await wait_msg.delete()
                            except Exception:
                                pass
                        context.user_data.pop(_FORCE_NEW, None)
                        raise
        return wrapper
    return decorator

_KEY = "_last_menu_msg_id"


async def track_menu(context, message):
    context.user_data[_KEY] = (message.chat_id, message.message_id)


async def delete_old_menu(context, chat_id):
    data = context.user_data.pop(_KEY, None)
    if data:
        old_chat, old_msg = data
        if old_chat == chat_id:
            try:
                await context.bot.delete_message(chat_id=old_chat, message_id=old_msg)
            except Exception:
                pass


async def refresh_menu(query, context, text, reply_markup=None, parse_mode=None):
    chat_id = query.message.chat_id
    force_new = context.user_data.pop(_FORCE_NEW, False)
    if not force_new:
        try:
            edited = await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
            msg_id = edited.message_id if hasattr(edited, 'message_id') else query.message.message_id
            context.user_data[_KEY] = (chat_id, msg_id)
            return edited if hasattr(edited, 'message_id') else query.message
        except Exception as e:
            if "not modified" in str(e).lower():
                context.user_data[_KEY] = (chat_id, query.message.message_id)
                return query.message
    try:
        await query.delete_message()
    except Exception:
        pass
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    context.user_data[_KEY] = (chat_id, msg.message_id)
    return msg
