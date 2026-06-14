import logging

logger = logging.getLogger(__name__)

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
