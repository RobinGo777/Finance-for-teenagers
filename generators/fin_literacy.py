from generators.gemini import generate_json, pick_persona, pick_template, build_base_prompt
from data.redis_client import get_used_topics, save_topic, add_weekly_topic
from data.fetchers import fetch_nbu_rates
from images.generator import generate_post_image

RUBRIC_KEY     = "fin_literacy"
RUBRIC_NAME    = "#ФінГрамотність"
RUBRIC_HASHTAG = "🧠 #ФінГрамотність"

FIN_TOPICS = [
    "бюджет і правило 50/30/20", "що таке інфляція",
    "як працює кредит", "депозит і відсотки",
    "податки — що це і навіщо", "страхування",
    "пенсійний фонд", "що таке ВВП",
    "різниця між активом і пасивом", "як читати ціннику",
    "чому гроші знецінюються", "фінансова подушка безпеки",
    "що таке дефолт", "як працює НБУ",
    "різниця між доходом і прибутком",
]


async def generate_fin_literacy() -> dict:
    """
    Генерує освітній пост про фінансову грамотність.
    Термін + пояснення + приклад + конкретні дії.
    """

    persona     = pick_persona()
    template    = await pick_template()
    used_topics = await get_used_topics(RUBRIC_KEY)
    nbu_rates   = await fetch_nbu_rates(["USD", "EUR"])

    available   = [t for t in FIN_TOPICS if t not in used_topics]
    topics_hint = ", ".join(available[:8]) if available else "нова фінансова тема"

    usd = nbu_rates.get("USD", "N/A")
    extra = f"Курс USD/UAH сьогодні: {usd} грн (для прикладів)"

    task = (
        "Поясни фінансовий термін або концепцію для підлітка. "
        "Обов'язково реальний приклад з життя українського підлітка і конкретні дії що можна зробити вже зараз. "
        f"Обери тему з: {topics_hint}."
    )

    base = build_base_prompt(
        rubric_name=RUBRIC_NAME,
        rubric_hashtag=RUBRIC_HASHTAG,
        task=task,
        used_topics=used_topics,
        persona=persona,
        extra_data=extra,
    )

    prompt = base + """
ФОРМАТ ВІДПОВІДІ (тільки JSON):
{
  "topic": "назва теми (3-5 слів)",
  "title": "заголовок для картинки (макс 8 слів)",
  "post": "🧠 #ФінГрамотність\\n\\n📖 [термін] — [визначення одним реченням]\\n\\n[пояснення з прикладом з життя підлітка, 3-4 речення]\\n\\n✅ Як застосувати зараз:\\n1. [дія]\\n2. [дія]\\n\\n💬 [питання для роздумів]",
  "body_preview": "1-2 речення для картинки (без емодзі)"
}
"""

    data = await generate_json(prompt)

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
