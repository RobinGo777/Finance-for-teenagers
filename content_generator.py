"""
Генератор контенту через Google Gemini API.
Модель: gemini-2.0-flash (швидка, безкоштовна квота)
"""

import asyncio
import json
import logging
import os
import random

import httpx

logger = logging.getLogger(__name__)

# Повтори при 429/5xx — безкоштовна квота часто вимагає пауз 30–120+ с між спробами
_GEMINI_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "10"))
_GEMINI_BASE_DELAY_S = 2.0

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

# ── Системний промпт — база ───────────────────────────────────────────────────
BASE_SYSTEM = """Ти — автор освітнього Telegram-каналу «Фінанси для підлітків» для учнів 7–11 класу (13–17 років).

СТИЛЬ:
- Пиши як розумний старший друг, не як вчитель чи підручник
- Жива українська мова, без канцеляризмів
- Англійські терміни (ETF, blockchain, AI, S&P 500) — залишай як є, але пояснюй при першому вжитку
- 2–4 емодзі на пост, доречно і не перебільшуй

ФОРМАТ:
- Довжина: 900–1200 символів (оптимально для Telegram caption)
- HTML-теги для Telegram: <b>жирний</b>, <i>курсив</i>, <code>код</code>
- Структура: хук → пояснення → приклад з реального життя → висновок → питання читачу
- Один складний термін = одразу пояснення в дужках або після тире

ЗАБОРОНЕНО:
- Конкретні фінансові поради типу «купи Bitcoin» або «вкладай в Tesla»
- Складні терміни без пояснення
- Сухі новинні факти без контексту
- Хештеги
- Фраза «Привіт!» на початку"""

# ── Промпти по темах ──────────────────────────────────────────────────────────
TOPIC_PROMPTS = {
    "economics": "Тема: Економіка. Поясни концепцію через конкретний приклад з реального українського або світового життя. Ціни в магазині, курс валют, зарплата — це все близько підлітку.",
    "ai": "Тема: Штучний інтелект і технології. Покажи практичну користь або реальний ризик для підлітка: як це змінить навчання, роботу, повсякденне життя.",
    "stocks": "Тема: Фондовий ринок. Якщо це компанія — поясни ЩО вона робить, ЯК заробляє, ЧОМУ цікава. Якщо концепція — дай живий приклад. Без агітації купувати.",
    "crypto": "Тема: Криптовалюти. Фокус на розумінні технології та критичному мисленні. Не хайп — а чесний розбір: як працює, де ризик, де можливість.",
    "finance": "Тема: Особисті фінанси. Один конкретний лайфхак або навичка, яку підліток може застосувати вже сьогодні. Маленька звичка = великий результат через роки.",
    "poll": "Створи цікаве опитування для підлітків.",
    "digest": "Тема: Дайджест тижня. Склади огляд 3 важливих фінансових або технологічних подій. Кожна — 1–2 речення простою мовою. Поясни чому це важливо підлітку.",
}

# ── Формати постів ────────────────────────────────────────────────────────────
FORMAT_INSTRUCTIONS = {
    "explain": """Структура поста «Пояснення за 60 секунд»:
1. 🔥 Хук: несподіване запитання або шокуючий факт (1 речення)
2. Пояснення: 3–4 короткі абзаци, кожен — одна ідея
3. 💡 Приклад: конкретна ситуація з реального життя
4. ✅ Висновок: одна чітка думка на виніс
5. ❓ Питання читачу: залучаюче, не риторичне""",

    "company_or_concept": """Структура «Розбір компанії або концепції»:
🏢 <b>Хто це / що це?</b> — 2 речення
💡 <b>Як заробляє / як працює?</b> — суть без зайвих деталей
📊 <b>Чому це важливо знати?</b> — зв'язок з реальністю
🎯 <b>Що це означає для тебе?</b> — практичний висновок
❓ Питання читачу""",

    "lifehack": """Структура «Фінансовий лайфхак»:
💥 Хук: несподіваний факт або ситуація (1 речення)
🔑 Головна ідея: один конкретний принцип
📱 Як застосувати прямо зараз: 2–3 прості кроки
💬 Питання: а ти вже пробував це?""",

    "digest": """Структура «Дайджест тижня»:
🧾 <b>Що важливого сталося цього тижня</b>

📌 [Коротка назва події 1]
1–2 речення пояснення простою мовою.

📌 [Подія 2]
1–2 речення.

📌 [Подія 3]
1–2 речення.

🤔 Яка з цих новин тебе здивувала найбільше?""",
}


class ContentGenerator:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate(self, topic_config: dict) -> dict:
        fmt = topic_config["format"]

        if fmt == "poll":
            return await self._generate_poll(topic_config)
        elif fmt == "digest":
            return await self._generate_digest(topic_config)
        else:
            return await self._generate_post(topic_config)

    # ── Текстовий пост ────────────────────────────────────────────────────────
    async def _generate_post(self, topic_config: dict) -> dict:
        system_key      = topic_config.get("system_key", "economics")
        topic_hint      = TOPIC_PROMPTS.get(system_key, "")
        format_hint     = FORMAT_INSTRUCTIONS.get(topic_config["format"], "")
        current_topic   = topic_config.get("current_topic", "")

        prompt = f"""{BASE_SYSTEM}

{topic_hint}

{format_hint}

ЗАВДАННЯ: Напиши пост на тему «{current_topic}».
Аудиторія: підлітки 13–17 років, Україна.

Поверни ТІЛЬКИ текст поста з HTML-тегами. Без пояснень, без коментарів."""

        text = await self._call_gemini(prompt)
        return {"caption": text}

    # ── Опитування ────────────────────────────────────────────────────────────
    async def _generate_poll(self, topic_config: dict) -> dict:
        current_topic = topic_config.get("current_topic", "Куди б ти інвестував гроші?")

        prompt = f"""Створи Telegram-опитування для підлітків 13–17 років на тему: «{current_topic}»

Вимоги:
- Запитання: цікаве, трохи провокаційне, max 255 символів
- Варіантів відповіді: рівно 4, кожен max 100 символів
- Мова: українська
- Стиль: живий, не нудний

Поверни ТІЛЬКИ валідний JSON без markdown-огорож:
{{"question": "...", "options": ["...", "...", "...", "..."]}}"""

        raw = await self._call_gemini(prompt)
        try:
            clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(clean)
            # Валідація
            if "question" in data and "options" in data and len(data["options"]) >= 2:
                return {"poll": data}
        except (json.JSONDecodeError, KeyError):
            logger.error(f"Не вдалося розпарсити poll JSON: {raw[:200]}")

        # Fallback опитування
        return {
            "poll": {
                "question": "Куди б ти вклав 1000 грн прямо зараз?",
                "options": [
                    "💰 Відклав на рахунок",
                    "₿ Купив би крипту",
                    "📈 Вклав в акції",
                    "🛍 Витратив би зараз",
                ],
            }
        }

    # ── Дайджест ──────────────────────────────────────────────────────────────
    async def _generate_digest(self, topic_config: dict) -> dict:
        prompt = f"""{BASE_SYSTEM}

{TOPIC_PROMPTS['digest']}

{FORMAT_INSTRUCTIONS['digest']}

ЗАВДАННЯ: Напиши дайджест для підлітків. Вигадай або узагальни 3 реалістичні новини цього тижня:
— Одна про світову економіку або ринки
— Одна про криптовалюти або ШІ
— Одна про Україну або особисті фінанси

Поверни ТІЛЬКИ текст поста з HTML-тегами. Без пояснень."""

        text = await self._call_gemini(prompt)
        return {"caption": text}

    # ── Виклик Gemini API ─────────────────────────────────────────────────────
    async def _call_gemini(self, prompt: str) -> str:
        url = f"{GEMINI_API_URL}?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.85,
                "maxOutputTokens": 1024,
                "topP": 0.95,
            },
        }

        for attempt in range(_GEMINI_MAX_RETRIES):
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(url, json=payload)

            if resp.status_code == 429:
                if attempt >= _GEMINI_MAX_RETRIES - 1:
                    resp.raise_for_status()
                delay = _gemini_retry_delay_s(resp, attempt)
                logger.warning(
                    "Gemini 429 (rate limit) — пауза %.1f с, спроба %d/%d",
                    delay,
                    attempt + 1,
                    _GEMINI_MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                continue

            if 500 <= resp.status_code < 600:
                if attempt >= _GEMINI_MAX_RETRIES - 1:
                    resp.raise_for_status()
                delay = min(45.0, _GEMINI_BASE_DELAY_S * (2**attempt))
                logger.warning(
                    "Gemini %s — пауза %.1f с, спроба %d/%d",
                    resp.status_code,
                    delay,
                    attempt + 1,
                    _GEMINI_MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            data = resp.json()

            try:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError) as e:
                logger.error("Несподівана відповідь Gemini: %s", data)
                raise RuntimeError(f"Gemini API: невалідна відповідь — {e}") from e

        assert False, "unreachable"


def _gemini_retry_delay_s(resp: httpx.Response, attempt: int) -> float:
    """
    Затримка перед повтором після 429.
    Google інколи шле Retry-After; інакше — довгі паузи (короткі спроби всі падають підряд).
    """
    h = resp.headers.get("Retry-After")
    if h:
        try:
            return min(300.0, float(h))
        except ValueError:
            pass
    # 20 → 40 → 80 → … (cap 180 с) + jitter; дає час відновити RPM на free tier
    base = 20.0 * (2**attempt)
    return min(180.0, base + random.uniform(2.0, 12.0))
