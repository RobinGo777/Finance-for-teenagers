from aiogram import Bot
from aiogram.types import BufferedInputFile
import base64
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, MODERATOR_CHAT_ID
from data.redis_client import (
    get_autopilot,
    save_quiz_pending,
    add_quiz_pending_id,
    clear_quiz_pending,
)

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ─────────────────────────────────────────
# ГОЛОВНА ФУНКЦІЯ ПУБЛІКАЦІЇ
# ─────────────────────────────────────────

async def publish(post_data: dict) -> None:
    """
    Головна функція. Перевіряє autopilot:
    - ON  → публікує одразу в канал
    - OFF → відправляє тобі на модерацію
    """
    if not post_data:
        return

    autopilot = await get_autopilot()

    if autopilot:
        await publish_to_channel(post_data)
    else:
        await send_to_moderator(post_data)


# ─────────────────────────────────────────
# ПУБЛІКАЦІЯ В КАНАЛ
# ─────────────────────────────────────────

async def publish_to_channel(post_data: dict) -> int | None:
    """
    Публікує пост в Telegram канал.
    Повертає message_id опублікованого поста.
    """
    rubric   = post_data.get("rubric", "")
    text     = post_data.get("post", "")
    image    = post_data.get("image")          # bytes (Pillow)
    image_url = post_data.get("image_url")     # str (YouTube thumbnail)

    # ── Квіз → Telegram Poll ──
    if rubric == "quiz":
        return await _publish_quiz(post_data)

    # ── Пост з опитуванням (#ФінТруКрайм) ──
    if post_data.get("poll_options"):
        return await _publish_with_poll(post_data)

    # ── Пост з картинкою (Pillow bytes) ──
    if image:
        photo = BufferedInputFile(image, filename="post.png")
        msg = await bot.send_photo(
            chat_id=TELEGRAM_CHANNEL_ID,
            photo=photo,
            caption=text,
            parse_mode="HTML",
        )
        return msg.message_id

    # ── Пост з YouTube thumbnail ──
    if image_url:
        msg = await bot.send_photo(
            chat_id=TELEGRAM_CHANNEL_ID,
            photo=image_url,
            caption=text,
            parse_mode="HTML",
        )
        return msg.message_id

    # ── Текстовий пост ──
    msg = await bot.send_message(
        chat_id=TELEGRAM_CHANNEL_ID,
        text=text,
        parse_mode="HTML",
    )
    return msg.message_id


async def _publish_quiz(post_data: dict) -> int | None:
    """Публікує квіз як Telegram Poll + зберігає дані для відповіді через 24 год."""

    # Спочатку картинка
    image = post_data.get("image")
    if image:
        photo = BufferedInputFile(image, filename="quiz.png")
        await bot.send_photo(
            chat_id=TELEGRAM_CHANNEL_ID,
            photo=photo,
            caption=f"🎮 #ФінКвіз\n\n{post_data.get('question', '')}",
        )

    # Потім опитування
    msg = await bot.send_poll(
        chat_id=TELEGRAM_CHANNEL_ID,
        question=post_data.get("question", ""),
        options=post_data.get("options", []),
        is_anonymous=False,
        allows_multiple_answers=False,
    )

    # Зберігаємо в Redis для відповіді через 24 год
    await save_quiz_pending(msg.poll.id, {
        "correct_index": post_data.get("correct_index", 0),
        "lamp_post": post_data.get("lamp_post", ""),
        "message_id": msg.message_id,
    })
    await add_quiz_pending_id(msg.poll.id)

    return msg.message_id


async def _publish_with_poll(post_data: dict) -> int | None:
    """Публікує пост з картинкою і окремим опитуванням (#ФінТруКрайм)."""

    image = post_data.get("image")
    text  = post_data.get("post", "")

    # Пост з картинкою
    if image:
        photo = BufferedInputFile(image, filename="post.png")
        await bot.send_photo(
            chat_id=TELEGRAM_CHANNEL_ID,
            photo=photo,
            caption=text,
            parse_mode="HTML",
        )

    # Опитування під постом
    msg = await bot.send_poll(
        chat_id=TELEGRAM_CHANNEL_ID,
        question="Який факт — брехня шахрая?",
        options=post_data.get("poll_options", []),
        is_anonymous=False,
    )

    return msg.message_id


async def publish_quiz_answer(poll_id: str, poll_results: dict) -> None:
    """Публікує 💡 відповідь на квіз через 24 год."""
    from generators.quiz import generate_quiz_answer

    lamp_post = await generate_quiz_answer(poll_id, poll_results)
    if lamp_post:
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=lamp_post,
            parse_mode="HTML",
        )
        await clear_quiz_pending(poll_id)


# ─────────────────────────────────────────
# МОДЕРАЦІЯ (human-in-loop)
# ─────────────────────────────────────────

async def send_to_moderator(post_data: dict) -> None:
    """
    Надсилає пост тобі в особисті для перевірки.
    Три кнопки: ✅ Опублікувати / ✏️ Редагувати / ❌ Скасувати
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from data.redis_client import set as redis_set
    import json
    import time

    rubric  = post_data.get("rubric", "unknown")
    text    = post_data.get("post", "")
    image   = post_data.get("image")
    persona = post_data.get("persona", "")
    tmpl    = post_data.get("template", "")

    # Зберігаємо пост в Redis на 24 год
    post_id = f"pending:{rubric}:{int(time.time())}"
    image_b64 = base64.b64encode(image).decode("ascii") if image else None
    await redis_set(post_id, json.dumps({
        **post_data,
        "image": image_b64,
    }), ex=86400)

    # Клавіатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Опублікувати", callback_data=f"approve:{post_id}"),
        InlineKeyboardButton(text="❌ Скасувати",    callback_data=f"reject:{post_id}"),
    ]])

    caption = (
        f"📋 Новий пост на модерацію\n\n"
        f"Рубрика: {rubric}\n"
        f"Персона: {persona}\n"
        f"Шаблон: {tmpl}\n\n"
        f"─────────────────\n"
        f"{text[:800]}{'...' if len(text) > 800 else ''}"
    )

    if image:
        photo = BufferedInputFile(image, filename="preview.png")
        await bot.send_photo(
            chat_id=MODERATOR_CHAT_ID,
            photo=photo,
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await bot.send_message(
            chat_id=MODERATOR_CHAT_ID,
            text=caption,
            reply_markup=keyboard,
        )
