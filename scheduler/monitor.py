import asyncio
from datetime import datetime
import pytz

from config import (
    MONITOR_INTERVAL_HOURS,
    MONITOR_QUIET_START,
    MONITOR_QUIET_END,
    MONITOR_MAX_PER_DAY,
    TIMEZONE,
)
from data.redis_client import (
    get as redis_get,
    get_monitor_count_today,
    increment_monitor_count,
    is_published,
    mark_published,
)
from data.fetchers import fetch_all_rss, fetch_news, fetch_github_trending
from generators.video import generate_video
from generators.ai_news import generate_ai_news
from bot.publisher import publish

KYIV = pytz.timezone(TIMEZONE)

# Мінімальний score щоб вважати новину "breaking"
BREAKING_MIN_KEYWORDS = [
    "breaking", "just in", "urgent", "exclusive",
    "ШІ", "штучний інтелект", "OpenAI", "Google", "Apple",
    "recession", "crypto", "bitcoin", "ukraine",
]


# ─────────────────────────────────────────
# ГОЛОВНИЙ ЦИКЛ МОНІТОРИНГУ
# ─────────────────────────────────────────

async def start_monitor() -> None:
    """
    Безкінечний цикл — перевіряє нові матеріали кожні N годин.
    Не працює вночі (00:00 — 07:00 Київ).
    """
    print("[monitor] Запущено реалтайм моніторинг")

    while True:
        try:
            await asyncio.sleep(MONITOR_INTERVAL_HOURS * 3600)
            await run_monitor_cycle()
        except asyncio.CancelledError:
            print("[monitor] Зупинено")
            break
        except Exception as e:
            print(f"[monitor] Помилка циклу: {e}")
            await asyncio.sleep(60)


async def run_monitor_cycle() -> None:
    """Один цикл перевірки — викликається кожні 2 години."""

    # Перевіряємо тихий час
    if _is_quiet_time():
        return

    # Перевіряємо паузу
    paused = await redis_get("settings:paused")
    if paused:
        return

    # Перевіряємо ліміт постів на день
    count = await get_monitor_count_today()
    if count >= MONITOR_MAX_PER_DAY:
        print(f"[monitor] Ліміт {MONITOR_MAX_PER_DAY} постів досягнуто")
        return

    # Запускаємо всі перевірки паралельно
    await asyncio.gather(
        _check_video(),
        _check_breaking_news(),
        _check_github_trending(),
        return_exceptions=True,
    )


# ─────────────────────────────────────────
# ПЕРЕВІРКИ
# ─────────────────────────────────────────

async def _check_video() -> None:
    """Шукає нове топове відео на YouTube."""
    try:
        post_data = await generate_video()
        if post_data:
            count = await get_monitor_count_today()
            if count < MONITOR_MAX_PER_DAY:
                await publish(post_data)
                await increment_monitor_count()
                print(f"[monitor] Відео опубліковано: {post_data.get('topic')}")
    except Exception as e:
        print(f"[monitor] Помилка відео: {e}")


async def _check_breaking_news() -> None:
    """Перевіряє RSS і NewsAPI на breaking news."""
    try:
        rss_items  = await fetch_all_rss(limit_per_feed=2)
        news_items = await fetch_news(query="AI technology breaking", page_size=3)
        all_items  = rss_items + news_items

        for item in all_items:
            title = item.get("title", "").lower()

            # Перевіряємо чи є ключові слова
            is_breaking = any(kw.lower() in title for kw in BREAKING_MIN_KEYWORDS)
            if not is_breaking:
                continue

            # Перевіряємо чи вже публікували
            item_id = f"news:{hash(item.get('title', ''))}"
            if await is_published(item_id):
                continue

            # Публікуємо через генератор #ШІ_новини
            count = await get_monitor_count_today()
            if count >= MONITOR_MAX_PER_DAY:
                return

            post_data = await generate_ai_news()
            if post_data:
                await publish(post_data)
                await mark_published(item_id)
                await increment_monitor_count()
                print(f"[monitor] Breaking news: {item.get('title', '')[:60]}")
                return  # одна новина за цикл

    except Exception as e:
        print(f"[monitor] Помилка breaking news: {e}")


async def _check_github_trending() -> None:
    """Перевіряє GitHub Trending на нові вірусні репозиторії."""
    try:
        repos = await fetch_github_trending(topic="artificial-intelligence")

        for repo in repos:
            repo_id = f"github:{repo['name']}"
            if await is_published(repo_id):
                continue

            # Тільки якщо багато зірок (вірусний)
            if repo["stars"] < 500:
                continue

            count = await get_monitor_count_today()
            if count >= MONITOR_MAX_PER_DAY:
                return

            # Публікуємо як #ШІ_новини
            post_data = await generate_ai_news()
            if post_data:
                await publish(post_data)
                await mark_published(repo_id)
                await increment_monitor_count()
                print(f"[monitor] GitHub trending: {repo['name']} ⭐{repo['stars']}")
                return

    except Exception as e:
        print(f"[monitor] Помилка GitHub trending: {e}")


# ─────────────────────────────────────────
# ДОПОМІЖНІ ФУНКЦІЇ
# ─────────────────────────────────────────

def _is_quiet_time() -> bool:
    """Повертає True якщо зараз тихий час (не публікуємо)."""
    now_hour = datetime.now(KYIV).hour
    return MONITOR_QUIET_START <= now_hour < MONITOR_QUIET_END
