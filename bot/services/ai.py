import json
import logging

from openai import AsyncOpenAI

from bot.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

VOCAB_FIELDS = ("definition", "synonyms", "collocations", "example", "cefr_level")

SYSTEM_PROMPT = """\
You are a senior IELTS examiner and vocabulary specialist with deep expertise in Academic English at Band 7-9 level. Generate vocabulary entries for IELTS learners.

For each word/phrase, produce ONLY the missing fields from this set. The user may provide some fields - never overwrite those.

Fields to generate:

definition: Clear, precise, 1-2 sentences. Prioritize the meaning most relevant in IELTS academic contexts. Never use the word to define itself.

synonyms: 3-5 synonyms genuinely interchangeable in IELTS contexts. Order from most common to most sophisticated. Include at least one Band 7+ synonym. Avoid slang.

collocations: 4-6 collocations frequent in academic writing or formal speech. Mix verb+noun, adjective+noun, adverb+adjective/verb patterns. Each must sound natural in a Task 2 essay or Part 3 speaking response.

example: ONE sentence, Band 8 quality, 15-30 words. Use a common IELTS topic (education, technology, environment, health, urbanization, globalization, government policy, social issues). Include at least one sophisticated vocabulary item or grammatical structure so the example itself models high-band English.

cefr_level: Exactly one of B2, C1, or C2. B2 = Band 5.5-6.5 territory. C1 = Band 7-8. C2 = Band 8.5-9.

Respond ONLY with valid JSON, no markdown fences, no preamble:
{"definition": "...", "synonyms": "...", "collocations": "...", "example": "...", "cefr_level": "..."}
Include only fields that need to be generated."""


def _get_client() -> AsyncOpenAI:
    global _client
    if not OPENAI_API_KEY:
        raise ValueError(
            "OpenAI API key is not configured. Set the OPENAI_API_KEY environment variable."
        )
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


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


async def generate_vocab_entry(word: str, provided: dict[str, str]) -> dict[str, str]:
    client = _get_client()

    missing = [f for f in VOCAB_FIELDS if f not in provided]
    if not missing:
        return dict(provided)

    if provided:
        already = ", ".join(f"{k}: {v}" for k, v in provided.items())
        user_msg = f"Word: {word}. Already provided — {already}. Generate the missing fields."
    else:
        user_msg = f"Generate all fields for: {word}"

    for attempt in range(2):
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
        )
        content = resp.choices[0].message.content
        try:
            return _parse_json(content)
        except json.JSONDecodeError:
            if attempt == 0:
                logger.warning("JSON parse failed for '%s', retrying. Raw: %s", word, content[:200])
                continue
            raise ValueError(f"Failed to parse AI response for '{word}'")


async def generate_vocab_entries_bulk(words: list[str]) -> list[dict[str, str]]:
    client = _get_client()

    user_msg = (
        "Generate entries for each word. Return a JSON array of objects, "
        "one per word, each with fields: word_phrase, definition, synonyms, "
        "collocations, example, cefr_level.\n\n"
        f"Words: {', '.join(words)}"
    )

    for attempt in range(2):
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
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
                if i < len(words):
                    entry["word_phrase"] = words[i]
            return entries[: len(words)]
        except (json.JSONDecodeError, ValueError):
            if attempt == 0:
                logger.warning("JSON parse failed for bulk, retrying. Raw: %s", content[:300])
                continue
            raise ValueError("Failed to parse AI response for bulk generation")
