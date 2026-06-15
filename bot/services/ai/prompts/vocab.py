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

ANSWER_CHECK_SYSTEM_PROMPT = (
    "You are a vocabulary judge. The user was given a definition "
    "and asked to provide a matching word or phrase. Decide if the "
    "user's answer is a valid match for the definition. "
    "Reply with ONLY 'YES' or 'NO'."
)


def build_single_word_message(word: str, provided: dict[str, str]) -> str:
    if provided:
        already = ", ".join(f"{k}: {v}" for k, v in provided.items())
        return f"Word: {word}. Already provided — {already}. Generate the missing fields."
    return f"Generate all fields for: {word}"


def build_bulk_message(words: list[str]) -> str:
    return (
        "Generate entries for each word. Return a JSON array of objects, "
        "one per word, each with fields: word_phrase, definition, synonyms, "
        "collocations, example, cefr_level.\n\n"
        f"Words: {', '.join(words)}"
    )


def build_partial_message(entries: list[dict]) -> str:
    parts = []
    for i, entry in enumerate(entries, 1):
        missing_fields = [f for f in VOCAB_FIELDS if not entry.get(f)]
        lines = [f"Word {i}: {entry['word_phrase']}"]
        lines.append(f"  Generate these fields: {', '.join(missing_fields)}")
        parts.append("\n".join(lines))

    return (
        "For each word below, generate ONLY the listed fields. "
        "Return a JSON array with one object per word. "
        "Each object must have 'word_phrase' plus ONLY the requested fields.\n\n"
        + "\n\n".join(parts)
        + "\n\nRespond ONLY with a valid JSON array, no markdown, no preamble."
    )


def build_answer_check_message(
    definition: str, expected: str, user_answer: str
) -> str:
    return (
        f'Definition: "{definition}"\n'
        f'Expected answer: "{expected}"\n'
        f'User\'s answer: "{user_answer}"\n\n'
        "Is the user's answer a valid word/phrase for this definition?"
    )
