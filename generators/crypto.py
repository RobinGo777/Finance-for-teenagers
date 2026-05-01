from generators.gemini import generate_json, pick_persona, pick_template, build_base_prompt
from data.redis_client import get_used_topics, save_topic, add_weekly_topic
from data.fetchers import fetch_crypto, fetch_trending_crypto
from images.generator import generate_post_image

RUBRIC_KEY     = "crypto"
RUBRIC_NAME    = "#КриптоАбетка"
RUBRIC_HASHTAG = "₿ #КриптоАбетка"

# Теми для ротації (Gemini обирає з тих що ще не були)
CRYPTO_TOPICS = [
    "Bitcoin", "Ethereum", "DeFi", "NFT", "Web3",
    "необанки", "NFC", "CBDC", "цифровий гаманець",
    "блокчейн", "майнінг", "стейкінг", "криптобіржа",
    "Scam-alert", "фішинг у крипті", "приватний ключ",
    "смарт-контракт", "метавсесвіт", "Layer 2", "stablecoin",
]


async def generate_crypto() -> dict:
    """
    Генерує освітній пост для рубрики #КриптоАбетка (щочетверга).
    Пояснює одне поняття зі світу крипти/цифрових фінансів.
    Якщо тема Scam-alert — додає ознаки шахрайства.
    """

    # 1. Дані
    crypto_data      = await fetch_crypto()
    trending         = await fetch_trending_crypto()
    used_topics      = await get_used_topics(RUBRIC_KEY)

    persona  = pick_persona()
    template = await pick_template()

    # Залишок тем які ще не були
    available_topics = [t for t in CRYPTO_TOPICS if t not in used_topics]
    topics_hint = ", ".join(available_topics[:10]) if available_topics else "будь-яка нова тема"

    btc = crypto_data.get("bitcoin", {})
    extra = (
        f"BTC: ${btc.get('usd', 'N/A')} ({btc.get('usd_24h_change', 0):.1f}% за 24год)\n"
        f"Трендові монети зараз: {', '.join(trending)}"
    )

    task = (
        "Поясни ОДНЕ поняття зі світу крипти або цифрових фінансів. "
        "Як старший друг пояснює за 1 хвилину — просто і з прикладом з життя підлітка. "
        f"Обери тему з цих (або схожу): {topics_hint}. "
        "Якщо тема Scam-alert — обов'язково додай 3 ознаки шахрайства і що робити якщо потрапив."
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
  "topic": "назва поняття",
  "title": "заголовок для картинки (макс 8 слів)",
  "is_scam_alert": false,
  "post": "₿ #КриптоАбетка\\n\\n[emoji] [Назва] — це...\\n\\n[пояснення 3-4 речення]\\n\\n💡 Приклад: [життєва ситуація підлітка]\\n\\n[якщо scam: 🚨 Ознаки шахрайства:\\n1. ...\\n2. ...\\n3. ...\\n\\n✅ Що робити: ...]\\n\\n💬 Ти вже стикався з [тема]?",
  "body_preview": "1-2 речення для картинки (без емодзі)"
}
"""

    data = await generate_json(prompt)

    # Для Scam-alert використовуємо Warm Alert шаблон
    if data.get("is_scam_alert"):
        from config import VISUAL_TEMPLATES
        template = next((t for t in VISUAL_TEMPLATES if t["name"] == "Warm Alert"), template)

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
