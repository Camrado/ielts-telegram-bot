# IELTS Prep Bot

A Telegram bot for IELTS exam preparation with AI-powered content generation, spaced repetition flashcards, and interactive grammar learning.

---

## Features

### Vocabulary

- **Flashcard Review** — SM-2 spaced repetition algorithm schedules cards at optimal intervals (learning → young → mature)
- **Quizzes** — Practice mode that doesn't interfere with your SRS schedule
- **Add Single Word** — AI generates definition, synonyms, collocations, example sentences, and CEFR level automatically
- **Bulk Import** — Upload an `.xlsx` or `.csv` file (or paste a word list); AI fills in any missing fields, then you approve entries before they're saved
- **Stats** — Progress breakdown by CEFR level, accuracy, and streak

### Grammar

- **Learn** — Browse rules with examples, tips, and navigate between topics
- **Quizzes** — Three modes: by topic, mixed, or weak areas only
- **Add Topic** — Generate a new grammar topic (rules + practice questions) with a single prompt
- **Stats** — Mastery percentage and accuracy per topic

### General

- Daily reminders (4 configurable slots, skipped if you already studied today)
- Streak tracking across both vocabulary and grammar
- Smart menu cleanup — old messages are removed to keep the chat tidy
- Automatic retry on transient Telegram API failures

---

## Tech Stack

| Layer            | Technology                             |
| ---------------- | -------------------------------------- |
| Language         | Python 3.12 (fully async)              |
| Telegram         | python-telegram-bot 21                 |
| Database         | PostgreSQL + asyncpg (connection pool) |
| AI               | OpenAI API (GPT)                       |
| Scheduling       | APScheduler 3 (cron jobs)              |
| File Parsing     | openpyxl, csv                          |
| SRS Algorithm    | SM-2                                   |
| Containerization | Docker                                 |

---

## Architecture

```
bot/
├── handlers/          # Telegram ConversationHandler flows
│   ├── vocab.py       # Vocabulary add / bulk import / quiz
│   ├── grammar.py     # Grammar learn / quiz / add topic
│   ├── flashcards.py  # SRS flashcard review
│   ├── start.py       # /start, /help, /stats, /reminders
│   └── menu_utils.py  # Retry decorator, menu refresh helpers
│
├── repositories/      # All DB access (asyncpg queries)
│   ├── vocabulary.py
│   ├── progress.py    # SRS intervals and ease factors
│   ├── grammar.py
│   ├── user.py
│   └── review_log.py
│
├── services/
│   ├── ai/
│   │   ├── content_generator_service.py            # Abstract interface
│   │   ├── openai_content_generator_service.py     # OpenAI implementation
│   │   └── prompts/                                # vocab.py, grammar.py
│   ├── srs_service.py          # SM-2 logic
│   ├── file_parser_service.py  # xlsx / csv with flexible header detection
│   └── reminders_service.py    # APScheduler setup
│
├── database.py        # Pool init, schema creation
├── seed_grammar.py    # Idempotent grammar content seed
├── config.py          # Environment variable loading
└── main.py            # Application entry point
```

Key design decisions:

- **Service abstraction for AI** — `ContentGeneratorService` is an interface; the OpenAI implementation can be swapped without touching handlers.
- **Conversation state machine** — `ConversationHandler` drives all multi-step flows (add word → preview → save). `/cancel` works at any step.
- **Batch AI generation** — Bulk imports process words in groups of 8 to reduce API latency and cost.
- **User-scoped data** — Grammar topics can be shared (`user_id = NULL`) or private; vocabulary and progress are always per-user.
- **Graceful degradation** — Missing AI-generated fields default to empty; quizzes continue even if a topic has sparse data.

---

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL
- A Telegram bot token ([@BotFather](https://t.me/BotFather))
- An OpenAI API key

### Local Development

```bash
# 1. Clone and create a virtual environment
git clone https://github.com/<your-username>/ielts-telegram-bot.git
cd ielts-telegram-bot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN, DATABASE_URL, and OPENAI_API_KEY

# 4. Run
python -m bot.main
```

The database schema and initial grammar seed data are created automatically on first run.

### Docker

```bash
docker build -t ielts-bot .
docker run --env-file .env ielts-bot
```

---

## Environment Variables

| Variable             | Description                                                          |
| -------------------- | -------------------------------------------------------------------- |
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather                                                |
| `DATABASE_URL`       | PostgreSQL connection string (`postgresql://user:pass@host:5432/db`) |
| `OPENAI_API_KEY`     | OpenAI API key                                                       |

---

## Commands

| Command      | Description                         |
| ------------ | ----------------------------------- |
| `/start`     | Open the main menu                  |
| `/help`      | Show help text                      |
| `/stats`     | View your overall progress          |
| `/review`    | Jump directly to flashcard review   |
| `/reminders` | Toggle daily reminder notifications |
