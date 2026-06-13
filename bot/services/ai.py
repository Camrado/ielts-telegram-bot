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


def _normalize_entry(entry: dict) -> dict:
    for key in VOCAB_FIELDS:
        val = entry.get(key)
        if isinstance(val, list):
            entry[key] = ", ".join(str(v) for v in val)
        elif val is not None and not isinstance(val, str):
            entry[key] = str(val)
    return entry


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
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
        )
        content = resp.choices[0].message.content
        try:
            return _normalize_entry(_parse_json(content))
        except json.JSONDecodeError:
            if attempt == 0:
                logger.warning("JSON parse failed for '%s', retrying. Raw: %s", word, content[:200])
                continue
            raise ValueError(f"Failed to parse AI response for '{word}'")


async def generate_vocab_entries_partial(
    entries: list[dict],
) -> list[dict[str, str]]:
    client = _get_client()

    parts = []
    for i, entry in enumerate(entries, 1):
        lines = [f"Word {i}: {entry['word_phrase']}"]
        for field in VOCAB_FIELDS:
            val = entry.get(field)
            if val:
                lines.append(f"- {field}: PROVIDED ({val})")
            else:
                lines.append(f"- {field}: MISSING")
        parts.append("\n".join(lines))

    user_msg = (
        "For each word below, generate ONLY the fields marked as MISSING. "
        "Do not overwrite fields marked as PROVIDED. "
        "Return a JSON array with one object per word.\n\n"
        + "\n\n".join(parts)
        + '\n\nFor each word, return: {"word_phrase": "...", "definition": "...", '
        '"synonyms": "...", "collocations": "...", "example": "...", "cefr_level": "..."}\n'
        "Include ALL fields in the response — copy PROVIDED values as-is "
        "and fill in MISSING ones.\n"
        "Respond ONLY with a valid JSON array, no markdown, no preamble."
    )

    for attempt in range(2):
        resp = await client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
        )
        content = resp.choices[0].message.content
        try:
            results = _parse_json(content)
            if not isinstance(results, list):
                raise ValueError("Expected a JSON array")
            for i, result in enumerate(results):
                _normalize_entry(result)
                if i < len(entries):
                    result["word_phrase"] = entries[i]["word_phrase"]
            return results[: len(entries)]
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


GRAMMAR_MODULE_SYSTEM_PROMPT = """\
You are a senior IELTS examiner who designs grammar study materials for candidates targeting Band 7–9. You understand exactly which grammatical features examiners look for and which errors cost candidates bands.

Generate a complete grammar study module with rules and quiz questions based on the user's request.

RULES (generate 6-10):
- rule_title: short descriptive name
- rule_text: state the rule in plain language a B2 learner can understand. Include when it applies AND common exceptions.
- correct_example: a sentence demonstrating correct usage, using a common IELTS topic (education, technology, environment, health, urbanization, globalization, government policy, social issues, work, crime, media, culture).
- incorrect_example: the SAME idea with the specific grammatical error this rule addresses. Change only the grammar, not the content.
- tip: a practical test or mnemonic the learner can apply, or a note about common L1 interference patterns.
- sort_order: sequential integer starting from 1.

QUESTIONS (generate 3-5 per rule, so 20-40 total):
- question_type: one of fill_blank, correct_or_incorrect, pick_correct, error_correction
- linked_rule_title: must exactly match a rule_title from the rules array
- prompt: the question text the user sees. For fill_blank, use ___ for the blank.
- correct_answer: the right answer. For correct_or_incorrect, use "correct" or "incorrect". For error_correction and pick_correct, use the full correct sentence. For fill_blank, use the word/punctuation that fills the blank.
- wrong_answers: array of 2-3 plausible distractors. For correct_or_incorrect, this is empty. For error_correction, this is empty (user types answer). For fill_blank and pick_correct, provide realistic wrong options.
- explanation: 1-2 sentences explaining why the answer is correct, referencing the rule.

All sentences must use IELTS-relevant academic topics.
Mix question types roughly evenly across the set.

Respond ONLY with valid JSON, no markdown fences, no preamble:
{
  "topic": {
    "name": "...",
    "description": "...",
    "skill_tag": "writing" or "speaking" or "both",
    "band_target": "7" or "7.5" or "8+"
  },
  "rules": [...],
  "questions": [...]
}"""


async def generate_grammar_module(description: str) -> dict:
    client = _get_client()

    for attempt in range(2):
        resp = await client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": GRAMMAR_MODULE_SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
            temperature=0.7,
        )
        content = resp.choices[0].message.content
        try:
            data = _parse_json(content)
            if not isinstance(data, dict) or "topic" not in data or "rules" not in data:
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
            model="gpt-5.4-mini",
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
                _normalize_entry(entry)
                if i < len(words):
                    entry["word_phrase"] = words[i]
            return entries[: len(words)]
        except (json.JSONDecodeError, ValueError):
            if attempt == 0:
                logger.warning("JSON parse failed for bulk, retrying. Raw: %s", content[:300])
                continue
            raise ValueError("Failed to parse AI response for bulk generation")
