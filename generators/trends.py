from generators.gemini import generate_json, pick_persona, pick_template, build_base_prompt
from data.redis_client import get_used_topics, save_topic, add_weekly_topic
from data.fetchers import fetch_github_trending, fetch_reddit
from images.generator import generate_post_image

RUBRIC_KEY     = "trends"
RUBRIC_NAME    = "#ТрендТижня"
RUBRIC_HASHTAG = "🌍 #ТрендТижня"


async def generate_trends() -> dict:
    """
    Генерує пост про головний тренд тижня.
    Дані: GitHub Trending + Reddit + Gemini web search.
    Показує фінансовий бік тренду.
    """

    persona     = pick_persona()
    template    = await pick_template()
    used_topics = await get_used_topics(RUBRIC_KEY)

    # Збираємо дані
    github_repos = await fetch_github_trending(topic="artificial-intelligence")
    reddit_posts = await fetch_reddit(subreddit="technology", limit=5)

    github_str = "\n".join(
        f"- {r['name']} ⭐{r['stars']} — {r['description'][:80]}"
        for r in github_repos
    )
    reddit_str = "\n".join(
        f"- {p['title']} ({p['score']} upvotes)"
        for p in reddit_posts
    )

    extra = f"GitHub Trending цього тижня:\n{github_str}\n\nReddit Technology топ:\n{reddit_str}"

    task = (
        "Вибери ОДИН найцікавіший тренд тижня зі світу технологій або ШІ. "
        "Покажи його фінансовий бік — хто на цьому заробляє і скільки. "
        "Поясни що це означає для підлітка вже сьогодні."
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
  "topic": "назва тренду (3-5 слів)",
  "title": "заголовок для картинки (макс 8 слів)",
  "post": "🌍 #ТрендТижня\\n\\n🔥 Всі зараз говорять про [тренд]\\n\\n[що це + чому хайп, 2-3 речення]\\n\\n💰 Фінансовий бік: [хто і скільки на цьому заробляє]\\n\\n🎯 Що це означає для тебе: [практичний висновок]\\n\\n💬 [питання читачам]",
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
