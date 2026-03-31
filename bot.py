"""
🤖 Telegram-бот: Фінанси для підлітків
Платформа: Render.com (з keep-alive)
AI: Google Gemini API  |  Медіа: Pexels API  |  Пам'ять: Upstash Redis
Режим: Повна автоматизація за розкладом
"""

import os
import logging
import asyncio
from datetime import datetime
import pytz

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

from content_generator import ContentGenerator
from media_fetcher import MediaFetcher
from schedule_config import get_todays_topic
from redis_tracker import RedisTracker

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config з ENV ──────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID       = os.environ["TELEGRAM_CHANNEL_ID"]   # @mychannel або -100...
ADMIN_ID         = int(os.environ["ADMIN_TELEGRAM_ID"])
GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]
PEXELS_API_KEY   = os.environ["PEXELS_API_KEY"]
UPSTASH_URL      = os.environ["UPSTASH_REDIS_URL"]      # https://xxx.upstash.io
UPSTASH_TOKEN    = os.environ["UPSTASH_REDIS_TOKEN"]
TIMEZONE         = os.environ.get("BOT_TIMEZONE", "Europe/Kyiv")
POST_HOUR        = int(os.environ.get("POST_HOUR", "10"))
POST_MINUTE      = int(os.environ.get("POST_MINUTE", "0"))
PORT             = int(os.environ.get("PORT", "8080"))
RENDER_URL       = os.environ.get("RENDER_URL", "")

# ── Singleton Redis ───────────────────────────────────────────────────────────
redis = RedisTracker(UPSTASH_URL, UPSTASH_TOKEN)


# ── Публікація в канал ────────────────────────────────────────────────────────
async def publish_to_channel(app: Application, post: dict) -> None:
    """Надсилає пост напряму в канал."""
    caption   = post.get("caption", "")
    photo_url = post.get("photo_url")
    poll      = post.get("poll")

    try:
        if poll:
            await app.bot.send_poll(
                chat_id=CHANNEL_ID,
                question=poll["question"],
                options=poll["options"],
                is_anonymous=True,
            )
            logger.info("✅ Опитування опубліковано")

        elif photo_url:
            await app.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_url,
                caption=caption,
                parse_mode="HTML",
            )
            logger.info("✅ Пост з фото опубліковано")

        else:
            await app.bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode="HTML",
            )
            logger.info("✅ Текстовий пост опубліковано")

        # Повідомлення адміну
        tz  = pytz.timezone(TIMEZONE)
        now = datetime.now(tz).strftime("%H:%M")
        topic_label = post.get("topic_label", "")
        current_topic = post.get("current_topic", "")
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"✅ <b>Пост опубліковано</b> о {now}\n"
                f"📌 {topic_label}\n"
                f"💡 {current_topic}"
            ),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"❌ Помилка публікації: {e}")
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❌ <b>Помилка публікації!</b>\n<code>{e}</code>",
            parse_mode="HTML",
        )


# ── Щоденна задача ────────────────────────────────────────────────────────────
async def daily_post_job(app: Application) -> None:
    """Генерує та публікує пост. Redis гарантує що теми не повторюються."""
    tz      = pytz.timezone(TIMEZONE)
    weekday = datetime.now(tz).weekday()   # 0=Пн … 6=Нд
    topic   = get_todays_topic(weekday)

    topics_list = topic.get("topics", [])

    # ── Обираємо тему через Redis (без повторів) ──────────────────────────────
    if topics_list:
        chosen_topic = await redis.get_unused_topic(weekday, topics_list)
        topic["current_topic"] = chosen_topic
    else:
        chosen_topic = None   # дайджест — тема генерується динамічно

    logger.info(f"📅 {topic['label']} | {chosen_topic or 'дайджест'}")

    generator = ContentGenerator(GEMINI_API_KEY)
    media     = MediaFetcher(PEXELS_API_KEY)

    try:
        post = await generator.generate(topic)

        if not post.get("poll"):
            photo_url = await media.fetch(topic["photo_query"])
            post["photo_url"] = photo_url

        post["topic_label"]   = topic["label"]
        post["current_topic"] = chosen_topic or ""

        await publish_to_channel(app, post)

        # ── Позначаємо тему як використану в Redis ────────────────────────────
        if chosen_topic:
            await redis.mark_published(weekday, chosen_topic)

    except Exception as e:
        logger.error(f"❌ Помилка генерації: {e}")
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❌ <b>Помилка генерації!</b>\n<code>{e}</code>",
            parse_mode="HTML",
        )


# ── Admin-команди ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    tz      = pytz.timezone(TIMEZONE)
    now     = datetime.now(tz)
    weekday = now.weekday()
    topic   = get_todays_topic(weekday)
    await update.message.reply_text(
        f"🤖 <b>Фінанси для підлітків — бот активний</b>\n\n"
        f"📅 Сьогодні: {topic['label']}\n"
        f"🕐 Час публікації: {POST_HOUR:02d}:{POST_MINUTE:02d} ({TIMEZONE})\n"
        f"📢 Канал: {CHANNEL_ID}\n\n"
        f"<b>Команди:</b>\n"
        f"/post — опублікувати пост зараз\n"
        f"/status — статус і наступна тема\n"
        f"/stats — статистика Redis\n"
        f"/test — тест підключень",
        parse_mode="HTML",
    )


async def cmd_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("⏳ Генерую пост…")
    await daily_post_job(ctx.application)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    tz      = pytz.timezone(TIMEZONE)
    now     = datetime.now(tz)
    weekday = now.weekday()
    topic   = get_todays_topic(weekday)
    topics  = topic.get("topics", [])

    # Наступна тема з Redis
    next_topic = "—"
    if topics:
        next_topic = await redis.get_unused_topic(weekday, topics)

    # Остання опублікована
    last = await redis.get_last_published(weekday)

    await update.message.reply_text(
        f"📊 <b>Статус бота</b>\n\n"
        f"🕐 {now.strftime('%A, %d.%m.%Y %H:%M')} ({TIMEZONE})\n"
        f"📌 День: {topic['label']}\n"
        f"💡 Наступна тема: {next_topic}\n"
        f"📝 Остання: {last or '—'}\n"
        f"⏰ Публікація о: {POST_HOUR:02d}:{POST_MINUTE:02d}\n"
        f"📢 Канал: {CHANNEL_ID}",
        parse_mode="HTML",
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Статистика публікацій з Redis."""
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        stats = await redis.get_stats()
        per_day = stats.get("per_day", {})
        lines = "\n".join(f"  {day}: {cnt} постів" for day, cnt in per_day.items())
        await update.message.reply_text(
            f"📈 <b>Статистика публікацій</b>\n\n"
            f"Всього постів: <b>{stats['total']}</b>\n\n"
            f"{lines}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Redis помилка: {e}")


async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🔍 Тестую підключення…")
    results = []

    # Gemini
    try:
        gen = ContentGenerator(GEMINI_API_KEY)
        resp = await gen._call_gemini("Скажи тільки 'OK'.")
        results.append(f"✅ Gemini API: {resp[:15]}")
    except Exception as e:
        results.append(f"❌ Gemini API: {e}")

    # Pexels
    try:
        media = MediaFetcher(PEXELS_API_KEY)
        url = await media.fetch("money finance")
        results.append("✅ Pexels API: фото отримано")
    except Exception as e:
        results.append(f"❌ Pexels API: {e}")

    # Redis
    try:
        ok = await redis.ping()
        results.append(f"✅ Upstash Redis: {'PONG' if ok else 'не відповідає'}")
    except Exception as e:
        results.append(f"❌ Upstash Redis: {e}")

    # Telegram
    try:
        me = await ctx.bot.get_me()
        results.append(f"✅ Telegram Bot: @{me.username}")
    except Exception as e:
        results.append(f"❌ Telegram: {e}")

    await update.message.reply_text("\n".join(results))


# ── Keep-alive HTTP сервер ────────────────────────────────────────────────────
async def health_handler(request):
    return web.Response(text="OK", status=200)


async def start_web_server():
    web_app = web.Application()
    web_app.router.add_get("/", health_handler)
    web_app.router.add_get("/health", health_handler)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 HTTP сервер на порті {PORT}")


async def keep_alive_job():
    """Пінгує сам себе кожні 5 хв — Render не засипає."""
    if not RENDER_URL:
        return
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{RENDER_URL}/health",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                logger.info(f"Keep-alive ping → {resp.status}")
    except Exception as e:
        logger.warning(f"Keep-alive failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("post",   cmd_post))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats",  cmd_stats))
    app.add_handler(CommandHandler("test",   cmd_test))

    tz = pytz.timezone(TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)

    scheduler.add_job(
        daily_post_job,
        trigger="cron",
        hour=POST_HOUR,
        minute=POST_MINUTE,
        args=[app],
        id="daily_post",
    )
    scheduler.add_job(
        keep_alive_job,
        trigger="interval",
        minutes=5,
        id="keep_alive",
    )
    scheduler.start()

    await start_web_server()
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    logger.info(f"🤖 Бот запущено! Публікація о {POST_HOUR:02d}:{POST_MINUTE:02d} ({TIMEZONE})")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
