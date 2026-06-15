import json
import logging
import re

from openai import AsyncOpenAI

from bot.config import OPENAI_API_KEY
from bot.services.ai.prompts import vocab as vocab_prompts
from bot.services.ai.prompts import grammar as grammar_prompts

logger = logging.getLogger(__name__)

_PROVIDED_RE = re.compile(r"^PROVIDED\s*\((.+)\)$", re.IGNORECASE | re.DOTALL)


def _parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _strip_provided_wrapper(value: str) -> str:
    if not isinstance(value, str):
        return value
    m = _PROVIDED_RE.match(value.strip())
    return m.group(1).strip() if m else value


def _normalize_entry(entry: dict) -> dict:
    for key in vocab_prompts.VOCAB_FIELDS:
        val = entry.get(key)
        if isinstance(val, list):
            entry[key] = ", ".join(str(v) for v in val)
        elif val is not None and not isinstance(val, str):
            entry[key] = str(val)
        if isinstance(entry.get(key), str):
            entry[key] = _strip_provided_wrapper(entry[key])
    return entry


class OpenAIContentGeneratorService:
    def __init__(self) -> None:
        if OPENAI_API_KEY:
            self._client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        else:
            self._client = None
        self._model = "gpt-5.4-mini"

    def _ensure_client(self) -> AsyncOpenAI:
        if self._client is None:
            raise ValueError(
                "OpenAI API key is not configured. "
                "Set the OPENAI_API_KEY environment variable."
            )
        return self._client

    async def generate_vocab_entry(
        self, word: str, provided: dict[str, str]
    ) -> dict[str, str]:
        missing = [f for f in vocab_prompts.VOCAB_FIELDS if f not in provided]
        if not missing:
            return dict(provided)

        client = self._ensure_client()
        user_msg = vocab_prompts.build_single_word_message(word, provided)

        for attempt in range(2):
            resp = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": vocab_prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
            )
            content = resp.choices[0].message.content
            try:
                result = _normalize_entry(_parse_json(content))
                for field in missing:
                    if not result.get(field):
                        result[field] = ""
                        logger.warning(
                            "AI omitted field '%s' for word '%s'", field, word
                        )
                return result
            except json.JSONDecodeError:
                if attempt == 0:
                    logger.warning(
                        "JSON parse failed for '%s', retrying. Raw: %s",
                        word,
                        content[:200],
                    )
                    continue
                raise ValueError(f"Failed to parse AI response for '{word}'")

    async def generate_vocab_entries_bulk(
        self, words: list[str]
    ) -> list[dict[str, str]]:
        client = self._ensure_client()
        user_msg = vocab_prompts.build_bulk_message(words)

        for attempt in range(2):
            resp = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": vocab_prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
            )
            content = resp.choices[0].message.content
            try:
                entries = _parse_json(content)
                if not isinstance(entries, list):
                    raise ValueError("Expected a JSON array")
                for i, entry in enumerate(entries):
                    _normalize_entry(entry)
                    if i < len(words):
                        entry["word_phrase"] = words[i]
                    for field in vocab_prompts.VOCAB_FIELDS:
                        if not entry.get(field):
                            entry[field] = ""
                return entries[: len(words)]
            except (json.JSONDecodeError, ValueError):
                if attempt == 0:
                    logger.warning(
                        "JSON parse failed for bulk, retrying. Raw: %s",
                        content[:300],
                    )
                    continue
                raise ValueError(
                    "Failed to parse AI response for bulk generation"
                )

    async def generate_vocab_entries_partial(
        self, entries: list[dict]
    ) -> list[dict[str, str]]:
        client = self._ensure_client()
        user_msg = vocab_prompts.build_partial_message(entries)

        for attempt in range(2):
            resp = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": vocab_prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
            )
            content = resp.choices[0].message.content
            try:
                results = _parse_json(content)
                if not isinstance(results, list):
                    raise ValueError("Expected a JSON array")

                merged = []
                for i, result in enumerate(results):
                    _normalize_entry(result)
                    if i >= len(entries):
                        break
                    original = entries[i]
                    final = {"word_phrase": original["word_phrase"]}
                    for field in vocab_prompts.VOCAB_FIELDS:
                        original_val = original.get(field)
                        if original_val:
                            final[field] = original_val
                        elif result.get(field):
                            final[field] = result[field]
                        else:
                            final[field] = ""
                    merged.append(final)
                return merged
            except (json.JSONDecodeError, ValueError):
                if attempt == 0:
                    logger.warning(
                        "JSON parse failed for partial bulk, retrying. Raw: %s",
                        content[:300],
                    )
                    continue
                raise ValueError(
                    "Failed to parse AI response for partial bulk generation"
                )

    async def generate_grammar_module(
        self, description: str, existing_topic_names: list[str] | None = None
    ) -> dict:
        client = self._ensure_client()
        user_msg = grammar_prompts.build_module_message(
            description, existing_topic_names
        )

        for attempt in range(2):
            resp = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": grammar_prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
            )
            content = resp.choices[0].message.content
            try:
                data = _parse_json(content)
                if (
                    not isinstance(data, dict)
                    or "topic" not in data
                    or "rules" not in data
                ):
                    raise ValueError("Missing required keys in response")
                return data
            except (json.JSONDecodeError, ValueError):
                if attempt == 0:
                    logger.warning(
                        "Grammar module JSON parse failed, retrying. Raw: %s",
                        content[:300],
                    )
                    continue
                raise ValueError(
                    "Failed to parse AI response for grammar module generation"
                )

    async def check_vocab_answer(
        self, definition: str, expected: str, user_answer: str
    ) -> bool:
        client = self._ensure_client()
        try:
            resp = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": vocab_prompts.ANSWER_CHECK_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": vocab_prompts.build_answer_check_message(
                            definition, expected, user_answer
                        ),
                    },
                ],
                temperature=0,
                max_tokens=3,
            )
            return (
                resp.choices[0].message.content.strip().upper().startswith("YES")
            )
        except Exception:
            logger.warning(
                "AI answer check failed for '%s', falling back to incorrect",
                user_answer,
                exc_info=True,
            )
            return False
