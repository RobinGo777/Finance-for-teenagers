import json
import random
import httpx
from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    PERSONAS,
    VISUAL_TEMPLATES,
)
from data.redis_client import get_last_template, save_last_template

# ─────────────────────────────────────────
# БАЗОВИЙ КЛІЄНТ GEMINI API
# ─────────────────────────────────────────

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)


async def generate(prompt: str, use_search: bool = False) -> str:
    """
    Відправляє промпт до Gemini і повертає текст відповіді.
    use_search=True — вмикає Google Search Grounding (свіжі новини).
    """
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 1024,
        },
    }

    if use_search:
        payload["tools"] = [{"google_search_retrieval": {}}]

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GEMINI_URL, json=payload)
        response.raise_for_status()
        data = response.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Невірна відповідь Gemini: {data}") from e


async def generate_json(prompt: str, use_search: bool = False) -> dict:
    """
    Генерує відповідь і парсить як JSON.
    Автоматично очищає markdown-блоки ```json ... ```
    """
    raw = await generate(prompt, use_search=use_search)
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini повернув не JSON:\n{raw}") from e


# ─────────────────────────────────────────
# ВИБІР ПЕРСОНИ
# ─────────────────────────────────────────

def pick_persona() -> dict:
    """Випадково обирає одну з 4 персон."""
    return random.choice(PERSONAS)


# ─────────────────────────────────────────
# ВИБІР ВІЗУАЛЬНОГО ШАБЛОНУ
# ─────────────────────────────────────────

async def pick_template() -> dict:
    """
    Випадково обирає шаблон, але не той що був останні 2 рази.
    Зберігає вибір в Redis.
    """
    last = await get_last_template()
    available = [t for t in VISUAL_TEMPLATES if t["name"] not in last]

    # якщо всі були (малоймовірно) — беремо будь-який крім останнього
    if not available:
        available = [t for t in VISUAL_TEMPLATES if t["name"] != last[-1]]

    template = random.choice(available)
    await save_last_template(template["name"])
    return template


# ─────────────────────────────────────────
# БАЗОВИЙ БУДІВНИК ПРОМПТУ
# ─────────────────────────────────────────

def build_base_prompt(
    rubric_name: str,
    rubric_hashtag: str,
    task: str,
    used_topics: list,
    persona: dict,
    extra_data: str = "",
) -> str:
    """
    Збирає базовий промпт з персоною, рубрикою і використаними темами.
    Кожен генератор рубрики викликає цю функцію і додає свій ФОРМАТ.
    """
    used_str = ", ".join(used_topics) if used_topics else "немає"

    return f"""Ти — {persona['name']}, {persona['role']}.
Канал "ФінПро для дітей" — Telegram-канал для підлітків України 12–20 років.
Твій стиль: {persona['style']}
Тип емодзі: {persona['emoji_style']}
Заклик до дії: {persona['cta_style']}

Рубрика: {rubric_name} ({rubric_hashtag})
Завдання: {task}

Теми що вже були (НЕ повторювати): {used_str}
{f'Додаткові дані:{chr(10)}{extra_data}' if extra_data else ''}
Вимоги:
- Мова: українська, розмовна, без канцеляриту
- Довжина посту: максимум 150 слів
- Аудиторія: підліток 14 років має зрозуміти без словника
- Відповідай ТІЛЬКИ валідним JSON, без зайвого тексту і без ```
"""
