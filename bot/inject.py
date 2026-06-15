from functools import wraps

from bot.services.ai.content_generator_service import ContentGeneratorService
from bot.services.ai.openai_content_generator_service import OpenAIContentGeneratorService


def setup_dependencies(bot_data: dict) -> None:
    bot_data["ai"] = OpenAIContentGeneratorService()


def inject(handler):
    @wraps(handler)
    async def wrapper(update, context):
        ai: ContentGeneratorService = context.bot_data["ai"]
        return await handler(update, context, ai=ai)
    return wrapper
