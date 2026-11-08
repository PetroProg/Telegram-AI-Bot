# 🤖 Telegram AI Bot

Продвинутый персональный клиент для Telegram с поддержкой изолированных сессий (чатов) и мультимодельности (AI Horde Uncensored, OpenRouter Free Tier, Google Gemini).

## ✨ Ключевые возможности

- 💬 **Изолированные диалоги**: Создавайте неограниченное число независимых чатов (сессий). За каждым диалогом закрепляется собственная нейросеть.
- 🔄 **Смена модели на лету**: Возможность в любой момент переключить модель у существующего чата.
- 📱 **Двухуровневый UX**:
  - Быстрое нижнее меню (Reply Keyboard): `💬 Мои чаты`, `➕ Новый чат`, `ℹ️ Активный чат`, `⚙️ Помощь`.
  - Интерактивные Inline-кнопки под сообщениями: пагинация по 5 чатов на страницу, меню управления (активация, просмотр истории, очистка контекста, переименование, удаление).
- 🧠 **Поддерживаемые модели**:
  - 🏴‍☠️ **AI Horde (Qwen 2.5 72B / Stheno)** — 100% бесплатно и без цензуры (работает в анонимном режиме без регистрации).
  - 🌐 **OpenRouter Auto Free** — автоматический роутинг на лучшие бесплатные облачные модели.
  - ⚡ **NVIDIA Nemotron 3.5 Lightning Free** — сверхбыстрые и качественные ответы.
  - 💎 **Google Gemma 4 31B Free** — открытая модель от Google без затрат.
  - 📸 **Google Gemini 2.0 Flash** — анализ фотографий и скриншотов.
- 👁 **Smart Vision Router**: Если вы отправляете фотографию или скриншот в чат с чисто текстовой моделью (например, Qwen или Nemotron), бот автоматически перенаправляет изображение в мультимодальную модель, получает анализ и аккуратно сохраняет результат в текущую ветку диалога.
- 📄 **Умная обработка длинных ответов**: Если ответ ИИ превышает лимит Telegram (4096 символов), бот присылает краткое превью и прикрепляет полный файл в формате `response.md` с сохранением форматирования и блоков кода.
- ⏳ **Плавный индикатор набора**: Во время ожидания ответа ИИ бот отображает естественный статус `печатает...`.
- 🔒 **Строгий белый список**: Доступ к боту ограничен только указанными в `.env` Telegram User ID (`ALLOWED_USER_IDS`).

---

## 🛠 Технологический стек

- **Язык**: Python 3.12+
- **Фреймворк бота**: [aiogram 3.x](https://github.com/aiogram/aiogram) (асинхронный Long Polling)
- **СУБД**: PostgreSQL 16
- **ORM / Миграции**: SQLAlchemy 2.0 (asyncio + asyncpg)
- **Валидация настроек**: Pydantic v2 Settings
- **HTTP Клиент**: HTTPX (с поддержкой HTTP/2)
- **Контейнеризация**: Docker & Docker Compose

---

## 🚀 Быстрый старт (Развертывание в Docker)

### 1. Клонирование репозитория
```bash
git clone https://github.com/PetroProg/Telegram-AI-Bot.git
cd Telegram-AI-Bot
```

### 2. Настройка переменных окружения
Скопируйте пример файла конфигурации:
```bash
cp .env.example .env
```
Заполните обязательные поля:
- `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather)
- `ALLOWED_USER_IDS` — ваш числовой Telegram User ID (например, `905176577`)
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` — параметры подключения к PostgreSQL
- `OPENROUTER_API_KEY` — ключ от OpenRouter для бесплатных моделей
- `GEMINI_API_KEY` — ключ Google AI Studio (для анализа изображений)

### 3. Запуск через Docker Compose
```bash
docker compose up -d --build
```

Просмотр логов:
```bash
docker compose logs -f
```

---

## 📂 Структура проекта

```text
├── app/
│   ├── bot/
│   │   ├── handlers/       # Обработчики команд, сообщений и фото
│   │   ├── keyboards/      # Постоянные Reply и инлайн Inline клавиатуры
│   │   ├── middlewares/    # Проверка белого списка (Whitelist)
│   │   └── states.py       # FSM состояния (создание, переименование чатов)
│   ├── core/
│   │   ├── config.py       # Pydantic Settings с валидацией
│   │   └── logger.py       # Настройка логирования
│   ├── db/
│   │   ├── base.py         # Declarative Base
│   │   ├── models.py       # ORM модели: User, Chat, Message, ModelCatalog
│   │   ├── repository.py   # Асинхронные CRUD операции с базой данных
│   │   └── session.py      # Пул соединений и инициализация схемы
│   ├── providers/
│   │   ├── base.py         # Базовый интерфейс LLM провайдера
│   │   ├── horde.py        # Клиент к кластеру AI Horde (Uncensored)
│   │   ├── openrouter.py   # Клиент к OpenRouter (Strictly Free)
│   │   ├── gemini.py       # Клиент к Google Gemini (Vision & Multimodal)
│   │   └── manager.py      # Умный роутинг моделей и фото (Smart Vision)
│   └── main.py             # Точка входа в приложение
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```
