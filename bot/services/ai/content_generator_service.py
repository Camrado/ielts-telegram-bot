from typing import Protocol


class ContentGeneratorService(Protocol):
    async def generate_vocab_entry(
        self, word: str, provided: dict[str, str]
    ) -> dict[str, str]: ...

    async def generate_vocab_entries_bulk(
        self, words: list[str]
    ) -> list[dict[str, str]]: ...

    async def generate_vocab_entries_partial(
        self, entries: list[dict]
    ) -> list[dict[str, str]]: ...

    async def generate_grammar_module(
        self, description: str, existing_topics: list[dict] | None = None
    ) -> dict: ...

    async def check_vocab_answer(
        self, definition: str, expected: str, user_answer: str
    ) -> bool: ...
