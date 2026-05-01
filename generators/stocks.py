from datetime import datetime
from generators.gemini import generate_json, pick_persona, pick_template, build_base_prompt
from data.redis_client import get_used_topics, save_topic, add_weekly_topic
from data.fetchers import fetch_stocks, fetch_nbu_rates
from images.generator import generate_chart_image, generate_post_image

RUBRIC_KEY     = "stocks"
RUBRIC_NAME    = "#БіржаДляДітей"
RUBRIC_HASHTAG = "📈 #БіржаДляДітей"

SYMBOLS = ["AAPL", "TSLA", "GOOGL", "NVDA", "MSFT", "META"]


async def generate_stocks() -> dict:
    """
    Генерує освітній пост про фондовий ринок для підлітків.
    Без заклику інвестувати — тільки навчання і розуміння ринку.
    """

    # 1. Отримуємо дані
    stocks     = await fetch_stocks(SYMBOLS)
    nbu_rates  = await fetch_nbu_rates(["USD", "EUR"])
    used_topics = await get_used_topics(RUBRIC_KEY)

    persona  = pick_persona()
    template = await pick_template()

    # 2. Формуємо зведення для промпту
    stocks_str = "\n".join(
        f"- {s['symbol']}: ${s['price']} ({s['change_percent']})"
        for s in stocks
    )
    usd_rate = nbu_rates.get("USD", "N/A")

    extra = f"Дані акцій за тиждень:\n{stocks_str}\nКурс USD/UAH: {usd_rate} грн"

    task = (
        "Напиши ОСВІТНІЙ пост про фондовий ринок. "
        "НЕ закликай інвестувати. Мета — навчання і розуміння як працює ринок. "
        "Структура: поняття тижня → що сталося на ринку → слово тижня → питання для роздумів."
    )

    base = build_base_prompt(
        rubric_name=RUBRIC_NAME,
        rubric_hashtag=RUBRIC_HASHTAG,
        task=task,
        used_topics=used_topics,
        persona=persona,
        extra_data=extra,
    )

    prompt = base + f"""
ФОРМАТ ВІДПОВІДІ (тільки JSON):
{{
  "topic": "коротка назва теми (3-5 слів)",
  "title": "заголовок для картинки (макс 8 слів)",
  "word_of_week": "фінансовий термін",
  "chart_labels": ["AAPL", "TSLA", "GOOGL"],
  "chart_values": [1.2, -0.8, 2.1],
  "post": "{RUBRIC_HASHTAG}\\n\\n📚 Що таке [поняття]?\\n[пояснення 1-2 речення]\\n\\n🗞️ Новина тижня:\\n[що сталося + ЧОМУ простими словами]\\n\\n📖 Слово тижня: [термін] — [визначення]\\n\\n🤔 Питання для роздумів:\\n[відкрите питання]",
  "body_preview": "1-2 речення для картинки (без емодзі)"
}}
"""

    data = await generate_json(prompt)

    # 3. Генеруємо chart якщо є дані, інакше звичайну картинку
    try:
        image_bytes = generate_chart_image(
            labels=data.get("chart_labels", [s["symbol"] for s in stocks[:4]]),
            values=data.get("chart_values", []),
            title=data.get("title", RUBRIC_NAME),
            template=template,
        )
    except Exception:
        image_bytes = generate_post_image(
            title=data.get("title", RUBRIC_NAME),
            body=data.get("body_preview", ""),
            rubric=RUBRIC_HASHTAG,
            persona_name=persona["name"],
            template=template,
        )

    await save_topic(RUBRIC_KEY, data["topic"])
    await add_weekly_topic(data["topic"])

    return {
        "rubric": RUBRIC_KEY,
        "topic": data["topic"],
        "post": data["post"],
        "image": image_bytes,
        "persona": persona["name"],
        "template": template["name"],
    }
