from generators.gemini import generate_json, pick_persona, pick_template, build_base_prompt
from data.redis_client import get_used_topics, save_topic, add_weekly_topic
from images.generator import generate_post_image

RUBRIC_KEY     = "business"
RUBRIC_NAME    = "#БізнесІсторії"
RUBRIC_HASHTAG = "🏢 #БізнесІсторії"

BUSINESS_TOPICS = [
    "Apple в гаражі Джобса", "як Безос почав Amazon з книг",
    "Цукерберг і перші дні Facebook", "Маск і провал SpaceX",
    "підліток що продав стартап за мільйон", "битва Pepsi vs Coca-Cola",
    "як Nike ледь не збанкрутував", "провал Nokia",
    "Airbnb — від повітряних матраців до мільярдів",
    "як Spotify врятував музичну індустрію",
    "TikTok і ByteDance — китайське диво", "провал Kodak",
    "як McDonald's заробляє насправді (не на бургерах)",
    "Netflix проти Blockbuster", "Ukrainian IT — як Україна стала ІТ-нацією",
    "Rozetka — від оголошення до маркетплейсу",
]


async def generate_business() -> dict:
    """
    Генерує захопливу міні-історію про бізнес з уроком для підлітка.
    """

    persona     = pick_persona()
    template    = await pick_template()
    used_topics = await get_used_topics(RUBRIC_KEY)

    available   = [t for t in BUSINESS_TOPICS if t not in used_topics]
    topics_hint = ", ".join(available[:8]) if available else "цікава бізнес-історія"

    task = (
        "Розкажи реальну бізнес-історію як захопливу міні-оповідь з цифрами і несподіваними фактами. "
        "Обов'язково один практичний урок для підлітка в кінці. "
        f"Обери тему з: {topics_hint}."
    )

    base = build_base_prompt(
        rubric_name=RUBRIC_NAME,
        rubric_hashtag=RUBRIC_HASHTAG,
        task=task,
        used_topics=used_topics,
        persona=persona,
    )

    prompt = base + """
ФОРМАТ ВІДПОВІДІ (тільки JSON):
{
  "topic": "назва історії (3-5 слів)",
  "title": "заголовок для картинки (макс 8 слів)",
  "post": "🏢 #БізнесІсторії\\n\\n🎬 [провокаційна зачіпка — 1 речення]\\n\\n[історія 4-5 речень з реальними цифрами і датами]\\n\\n💡 Урок: [один конкретний висновок для підлітка]\\n\\n💬 [питання читачам]",
  "body_preview": "1-2 речення для картинки (без емодзі)"
}
"""

    data = await generate_json(prompt, use_search=True)

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
