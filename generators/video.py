from generators.gemini import generate_json, pick_persona, build_base_prompt
from data.redis_client import get_used_topics, save_topic, is_published, mark_published
from data.fetchers import fetch_youtube_videos
from config import VISUAL_TEMPLATES

RUBRIC_KEY     = "video"
RUBRIC_NAME    = "#ВідеоТижня"
RUBRIC_HASHTAG = "🎥 #ВідеоТижня"

# Пошукові запити — чередуємо для різноманіття
SEARCH_QUERIES = [
    "AI breakthrough 2026",
    "robot technology amazing 2026",
    "space mission 2026",
    "science discovery incredible",
    "future technology invention",
    "artificial intelligence new",
    "robotics innovation 2026",
    "NASA space exploration 2026",
]


async def generate_video() -> dict | None:
    """
    Знаходить свіже топове відео на YouTube і генерує коментар.
    Повертає None якщо нічого цікавого не знайдено.
    Публікується у будь-який час коли знайдено (не вночі).
    """

    persona     = pick_persona()
    used_topics = await get_used_topics(RUBRIC_KEY)

    # Organic Growth шаблон для відео
    template = next((t for t in VISUAL_TEMPLATES if t["name"] == "Organic Growth"), None)

    # Шукаємо відео по всіх запитах
    all_videos = []
    for query in SEARCH_QUERIES:
        try:
            videos = await fetch_youtube_videos(
                query=query,
                max_results=5,
                published_after_hours=48,
            )
            all_videos.extend(videos)
        except Exception:
            continue

    if not all_videos:
        return None

    # Фільтруємо вже опубліковані
    new_videos = []
    for v in all_videos:
        if not await is_published(v["video_id"]):
            new_videos.append(v)

    if not new_videos:
        return None

    # Топ 5 по переглядах для промпту
    top_videos = sorted(new_videos, key=lambda x: x["views"], reverse=True)[:5]

    videos_str = "\n".join(
        f"- ID: {v['video_id']} | {v['title']} | {v['channel']} | {v['views']:,} переглядів"
        for v in top_videos
    )

    task = (
        "Вибери ОДНЕ найцікавіше відео зі списку для підлітків 12-20 років. "
        "Напиши захопливий коментар українською — що відбувається у відео і чому це вражає. "
        "Додай фінансовий або науковий кут якщо можливо."
    )

    base = build_base_prompt(
        rubric_name=RUBRIC_NAME,
        rubric_hashtag=RUBRIC_HASHTAG,
        task=task,
        used_topics=used_topics,
        persona=persona,
        extra_data=f"Доступні відео:\n{videos_str}",
    )

    prompt = base + """
ФОРМАТ ВІДПОВІДІ (тільки JSON):
{
  "video_id": "YouTube ID обраного відео",
  "topic": "тема відео (3-5 слів)",
  "post": "🎥 #ВідеоТижня\\n\\n[emoji] [що відбувається — 1-2 захопливі речення]\\n\\n[чому це важливо або вражає — 1-2 речення]\\n\\n💰 Цікавий факт: [фінансовий або науковий кут]\\n\\n💬 [питання читачам]\\n\\n👇 Дивись відео:"
}
"""

    data = await generate_json(prompt)

    video_id = data.get("video_id", "")

    # Перевіряємо що відео є в нашому списку
    selected = next((v for v in top_videos if v["video_id"] == video_id), top_videos[0])

    post_with_link = data["post"] + f"\nhttps://youtu.be/{selected['video_id']}"

    await save_topic(RUBRIC_KEY, data["topic"])
    await mark_published(selected["video_id"])

    return {
        "rubric": RUBRIC_KEY,
        "topic": data["topic"],
        "post": post_with_link,
        "image_url": selected["thumbnail"],  # YouTube thumbnail
        "video_id": selected["video_id"],
        "persona": persona["name"],
        "template": template["name"] if template else "Organic Growth",
    }
