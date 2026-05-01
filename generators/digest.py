from datetime import datetime
from generators.gemini import generate_json, pick_persona, build_base_prompt
from data.redis_client import get_weekly_topics, clear_weekly_topics
from data.fetchers import fetch_news, fetch_crypto, fetch_nbu_rates
from images.generator import generate_post_image
from config import VISUAL_TEMPLATES

RUBRIC_KEY     = "digest"
RUBRIC_NAME    = "#ДайджестТижня"
RUBRIC_HASHTAG = "📊 #ДайджестТижня"


async def generate_digest() -> dict:
    """
    Генерує підсумок тижня кожної неділі.
    Збирає всі теми тижня з Redis + свіжі дані + Gemini.
    Після генерації очищає список тем тижня.
    """

    persona = pick_persona()

    # Завжди Newspaper шаблон — серйозний дайджест
    template = next((t for t in VISUAL_TEMPLATES if t["name"] == "Newspaper"), None)

    # Збираємо дані тижня
    weekly_topics = await get_weekly_topics()
    crypto_data   = await fetch_crypto()
    nbu_rates     = await fetch_nbu_rates(["USD", "EUR"])
    top_news      = await fetch_news(query="AI technology finance Ukraine", page_size=3)

    topics_str = "\n".join(f"- {t}" for t in weekly_topics) if weekly_topics else "немає даних"
    news_str   = "\n".join(f"- {n['title']}" for n in top_news)

    btc = crypto_data.get("bitcoin", {})
    usd = nbu_rates.get("USD", "N/A")

    week_num = datetime.now().isocalendar()[1]

    extra = (
        f"Теми що публікувались цього тижня:\n{topics_str}\n\n"
        f"Топ новини тижня:\n{news_str}\n\n"
        f"BTC за тиждень: ${btc.get('usd', 'N/A')} ({btc.get('usd_24h_change', 0):.1f}%)\n"
        f"USD/UAH: {usd} грн"
    )

    task = (
        "Напиши стислий і цікавий дайджест тижня. "
        "5 головних пунктів — коротко і по суті. "
        "Один головний висновок що варто запам'ятати. "
        "Легкий і позитивний тон — як підсумок від друга."
    )

    base = build_base_prompt(
        rubric_name=RUBRIC_NAME,
        rubric_hashtag=RUBRIC_HASHTAG,
        task=task,
        used_topics=[],
        persona=persona,
        extra_data=extra,
    )

    prompt = base + f"""
ФОРМАТ ВІДПОВІДІ (тільки JSON):
{{
  "topic": "дайджест тиждень {week_num}",
  "title": "заголовок для картинки (макс 8 слів)",
  "post": "📊 #ДайджестТижня | Тиждень {week_num}\\n\\n📋 Головне за тиждень:\\n\\n[emoji] [пункт 1]\\n[emoji] [пункт 2]\\n[emoji] [пункт 3]\\n[emoji] [пункт 4]\\n[emoji] [пункт 5]\\n\\n🔥 Головне що варто запам'ятати:\\n[1 речення]\\n\\n👋 До зустрічі наступного тижня!",
  "body_preview": "1-2 речення для картинки (без емодзі)"
}}
"""

    data = await generate_json(prompt, use_search=True)

    image_bytes = generate_post_image(
        title=data.get("title", RUBRIC_NAME),
        body=data.get("body_preview", ""),
        rubric=RUBRIC_HASHTAG,
        persona_name=persona["name"],
        template=template,
    )

    # Очищаємо список тем тижня після дайджесту
    await clear_weekly_topics()

    return {
        "rubric": RUBRIC_KEY,
        "topic": data["topic"],
        "post": data["post"],
        "image": image_bytes,
        "persona": persona["name"],
        "template": template["name"],
    }
