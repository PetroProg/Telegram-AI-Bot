# Telegram AI Bot

Personal Telegram client for multi-model AI conversations with isolated chat sessions, persistent PostgreSQL history, and vision support.

## Features

- **Isolated Sessions**: Unlimited independent chats per user, each bound to a specific model with a configurable sliding context window.
- **Model Providers**:
  - **AI Horde**: Free uncensored models with strict model filtering, family-specific prompt templates (ChatML, Llama 3, Gemma), and automatic refusal retry.
  - **OpenRouter**: Free-tier cloud models with automatic routing.
  - **Google Gemini**: Multimodal and image analysis support.
- **Smart Vision Routing**: Images sent to text-only chats are routed through a vision-capable model and stored back in the active chat context.
- **Streamlined Telegram UI**:
  - One-tap chat activation from the paginated chat list and dedicated settings view (model switch, rename, history preview, context clear, delete).
  - Auto-cleanup of intermediate service menus and command triggers to keep the chat feed clean.
  - Live status message (`Generating...`) edited in place into the final HTML-formatted response.
  - Responses exceeding Telegram's 4096-character limit are truncated to a preview and attached as `response.md`.
- **Chat Cleanup**:
  - `/clean` clears recent physical messages from the Telegram feed (up to 500 messages within Telegram's 48-hour Bot API limit) while preserving database context.
  - `/clear` wipes both Telegram messages and database conversation history for the active chat.
- **Access Control**: Strict user whitelist via `ALLOWED_USER_IDS`.

## Tech Stack

- Python 3.12+
- [aiogram 3.x](https://github.com/aiogram/aiogram) (async long polling)
- PostgreSQL 16
- SQLAlchemy 2.0 (`asyncio` + `asyncpg`)
- Pydantic Settings v2
- HTTPX (HTTP/2)
- Docker & Docker Compose

## Commands

- `/start` — Initialize bot and display main keyboard
- `/chats` — List chats (one-tap switch and settings)
- `/new` — Create a new chat session
- `/current` — Inspect and manage the active chat
- `/clean` — Clear visible Telegram feed without deleting AI context
- `/clear` — Clear active chat context and Telegram messages
- `/delete` — Delete a chat session
- `/help` — Show command reference

## Deployment

### 1. Clone the repository

```bash
git clone https://github.com/PetroProg/Telegram-AI-Bot.git
cd Telegram-AI-Bot
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Required variables in `.env`:

- `BOT_TOKEN` — Telegram Bot API token from BotFather
- `ALLOWED_USER_IDS` — Comma-separated Telegram numeric user IDs
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — PostgreSQL connection settings
- `OPENROUTER_API_KEY` — OpenRouter API key (for OpenRouter models)
- `GEMINI_API_KEY` — Google AI Studio API key (for Gemini / Vision)
- `AI_HORDE_API_KEY` — AI Horde API key (`0000000000` for anonymous access)

### 3. Run with Docker Compose

Ensure the external Docker network defined in `docker-compose.yml` (`news-ai_default`) exists, or adjust `docker-compose.yml` to match your PostgreSQL network.

```bash
docker compose up -d --build
```

Inspect logs:

```bash
docker compose logs -f
```

## Project Structure

```text
├── app/
│   ├── bot/
│   │   ├── handlers/       # Command, chat management, text, and photo handlers
│   │   ├── keyboards/      # Reply and inline keyboards
│   │   ├── middlewares/    # Whitelist authorization middleware
│   │   ├── states.py       # FSM states (chat creation and renaming)
│   │   └── ui.py           # Menu tracking and message cleanup helpers
│   ├── core/
│   │   ├── config.py       # Pydantic settings
│   │   ├── logger.py       # Logging configuration
│   │   └── text_utils.py   # Response sanitization and Markdown-to-HTML conversion
│   ├── db/
│   │   ├── base.py         # Declarative base
│   │   ├── models.py       # ORM models: User, Chat, Message, ModelCatalog
│   │   ├── repository.py   # Async database operations
│   │   └── session.py      # Async engine, session factory, schema initialization
│   ├── providers/
│   │   ├── base.py         # Base LLM provider interface
│   │   ├── horde.py        # AI Horde client (uncensored filtering & retry)
│   │   ├── openrouter.py   # OpenRouter client
│   │   ├── gemini.py       # Google Gemini Vision client
│   │   └── manager.py      # Provider routing and Smart Vision fallback
│   └── main.py             # Application entry point
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```
