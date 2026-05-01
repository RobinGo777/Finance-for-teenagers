import json
import base64
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from bot.publisher import publish_to_channel, bot
from data.redis_client import get, delete, set_autopilot, get_autopilot
from config import MODERATOR_CHAT_ID

router = Router()

# ─────────────────────────────────────────
# ОБРОБКА КНОПОК МОДЕРАЦІЇ
# ─────────────────────────────────────────

@router.callback_query(F.data.startswith("approve:"))
async def approve_post(callback: CallbackQuery) -> None:
    """✅ Модератор схвалив — публікуємо в канал."""
    post_id = callback.data.replace("approve:", "")

    raw = await get(post_id)
    if not raw:
        await callback.answer("❌ Пост не знайдено або вже застарів")
        return

    post_data = json.loads(raw)
    if post_data.get("image"):
        post_data["image"] = base64.b64decode(post_data["image"])
    await publish_to_channel(post_data)
    await delete(post_id)

    if callback.message.caption:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ Опубліковано!",
            reply_markup=None,
        )
    else:
        await callback.message.edit_text(
            text=callback.message.text + "\n\n✅ Опубліковано!",
            reply_markup=None,
        )
    await callback.answer("✅ Опубліковано в канал!")


@router.callback_query(F.data.startswith("reject:"))
async def reject_post(callback: CallbackQuery) -> None:
    """❌ Модератор скасував — видаляємо з черги."""
    post_id = callback.data.replace("reject:", "")
    await delete(post_id)

    if callback.message.caption:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ Скасовано",
            reply_markup=None,
        )
    else:
        await callback.message.edit_text(
            text=callback.message.text + "\n\n❌ Скасовано",
            reply_markup=None,
        )
    await callback.answer("❌ Пост скасовано")


# ─────────────────────────────────────────
# КОМАНДИ УПРАВЛІННЯ БОТОМ
# ─────────────────────────────────────────

@router.message(Command("autopilot"), F.chat.id == MODERATOR_CHAT_ID)
async def cmd_autopilot(message: Message) -> None:
    """
    /autopilot on  — вмикає автопілот
    /autopilot off — вимикає автопілот
    """
    parts = message.text.strip().split()
    if len(parts) < 2 or parts[1] not in ("on", "off"):
        current = await get_autopilot()
        status = "✅ увімкнений" if current else "❌ вимкнений"
        await message.answer(
            f"Автопілот зараз: {status}\n\n"
            f"Використання:\n/autopilot on\n/autopilot off"
        )
        return

    enabled = parts[1] == "on"
    await set_autopilot(enabled)

    if enabled:
        await message.answer(
            "✅ Автопілот увімкнений!\n"
            "Бот публікує пости автоматично без твоєї перевірки."
        )
    else:
        await message.answer(
            "❌ Автопілот вимкнений.\n"
            "Кожен пост буде надходити тобі на перевірку."
        )


@router.message(Command("status"), F.chat.id == MODERATOR_CHAT_ID)
async def cmd_status(message: Message) -> None:
    """/status — показує поточний стан бота."""
    from data.redis_client import get_monitor_count_today
    from datetime import datetime
    import pytz

    autopilot = await get_autopilot()
    monitor_count = await get_monitor_count_today()
    kyiv_time = datetime.now(pytz.timezone("Europe/Kyiv")).strftime("%H:%M %d.%m.%Y")

    await message.answer(
        f"📊 Статус бота\n\n"
        f"🕐 Час (Київ): {kyiv_time}\n"
        f"🤖 Автопілот: {'✅ увімкнений' if autopilot else '❌ вимкнений'}\n"
        f"📡 Реалтайм постів сьогодні: {monitor_count}/4\n"
    )


@router.message(Command("pause"), F.chat.id == MODERATOR_CHAT_ID)
async def cmd_pause(message: Message) -> None:
    """/pause — тимчасово зупиняє публікації."""
    from data.redis_client import set as redis_set
    await redis_set("settings:paused", "1")
    await message.answer("⏸ Бот на паузі. Для продовження: /resume")


@router.message(Command("resume"), F.chat.id == MODERATOR_CHAT_ID)
async def cmd_resume(message: Message) -> None:
    """/resume — відновлює публікації після паузи."""
    from data.redis_client import delete
    await delete("settings:paused")
    await message.answer("▶️ Бот відновлено!")


@router.message(Command("help"), F.chat.id == MODERATOR_CHAT_ID)
async def cmd_help(message: Message) -> None:
    """/help — список команд."""
    await message.answer(
        "🤖 Команди управління ботом\n\n"
        "/autopilot on|off — увімк/вимк автопілот\n"
        "/status — стан бота\n"
        "/pause — пауза публікацій\n"
        "/resume — відновити публікації\n"
        "/help — ця довідка"
    )
