"""
Redis-трекер опублікованих тем через Upstash Redis REST API.
Upstash надає HTTP REST API — не потрібен redis-py, працює через httpx.
Безкоштовний план: 10 000 req/день, 256 MB.
"""

import hashlib
import logging
from datetime import date
import httpx

logger = logging.getLogger(__name__)


class RedisTracker:
    """
    Зберігає в Redis які теми вже були опубліковані по кожному дню тижня.
    Структура ключів:
      published:{weekday}        → Redis SET зі списком хешів опублікованих тем
      last_published:{weekday}   → останній опублікований топік (рядок)
      stats:total                → загальний лічильник постів
      stats:{weekday}            → лічильник по дню тижня
    """

    def __init__(self, redis_url: str, redis_token: str):
        # Upstash REST URL та токен з dashboard
        self.url   = redis_url.rstrip("/")
        self.token = redis_token
        self.headers = {
            "Authorization": f"Bearer {redis_token}",
            "Content-Type": "application/json",
        }

    # ── Публічний інтерфейс ───────────────────────────────────────────────────

    async def get_unused_topic(self, weekday: int, topics: list[str]) -> str:
        """
        Повертає тему, яка ще не публікувалась для цього дня тижня.
        Якщо всі теми використані — скидає лічильник і починає спочатку.
        """
        if not topics:
            return ""

        used = await self._get_used_topics(weekday)

        # Фільтруємо невикористані
        unused = [t for t in topics if self._hash(t) not in used]

        if not unused:
            logger.info(f"♻️ День {weekday}: всі теми використано — скидаємо цикл")
            await self._reset_weekday(weekday)
            unused = list(topics)

        # Беремо першу невикористану (порядок визначається schedule_config)
        chosen = unused[0]
        logger.info(f"✅ Обрана тема: {chosen[:60]}")
        return chosen

    async def mark_published(self, weekday: int, topic: str) -> None:
        """Позначає тему як опубліковану."""
        topic_hash = self._hash(topic)
        key = f"published:{weekday}"

        # Додаємо хеш до SET
        await self._command("SADD", key, topic_hash)

        # Зберігаємо останній топік (для /status)
        await self._command("SET", f"last_published:{weekday}", topic)

        # Лічильники
        await self._command("INCR", "stats:total")
        await self._command("INCR", f"stats:{weekday}")

        # TTL 365 днів — щоб Redis не переповнювався
        await self._command("EXPIRE", key, 365 * 24 * 3600)

        logger.info(f"📝 Збережено в Redis: день={weekday}, хеш={topic_hash[:8]}…")

    async def get_stats(self) -> dict:
        """Повертає статистику публікацій."""
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
        stats = {}

        total_raw = await self._command("GET", "stats:total")
        stats["total"] = int(total_raw) if total_raw else 0

        per_day = {}
        for i, day_name in enumerate(days):
            count_raw = await self._command("GET", f"stats:{i}")
            per_day[day_name] = int(count_raw) if count_raw else 0
        stats["per_day"] = per_day

        return stats

    async def get_last_published(self, weekday: int) -> str | None:
        """Повертає останню опубліковану тему для дня тижня."""
        result = await self._command("GET", f"last_published:{weekday}")
        return result

    async def get_last_daily_post_ymd(self) -> str | None:
        """Остання календарна дата (YYYY-MM-DD), коли успішно вийшов щоденний пост."""
        result = await self._command("GET", "last_daily_post_ymd")
        return result if result else None

    async def set_last_daily_post_ymd(self, ymd: str) -> None:
        """Позначає що за цей календарний день щоденний пост уже вийшов."""
        await self._command("SET", "last_daily_post_ymd", ymd)
        await self._command("EXPIRE", "last_daily_post_ymd", 10 * 24 * 3600)

    async def ping(self) -> bool:
        """Перевіряє підключення до Redis."""
        try:
            result = await self._command("PING")
            return result == "PONG"
        except Exception:
            return False

    # ── Внутрішні методи ─────────────────────────────────────────────────────

    async def _get_used_topics(self, weekday: int) -> set[str]:
        """Повертає SET хешів вже опублікованих тем."""
        key = f"published:{weekday}"
        result = await self._command("SMEMBERS", key)
        if isinstance(result, list):
            return set(result)
        return set()

    async def _reset_weekday(self, weekday: int) -> None:
        """Видаляє список використаних тем для дня — починаємо новий цикл."""
        await self._command("DEL", f"published:{weekday}")

    @staticmethod
    def _hash(topic: str) -> str:
        """Короткий хеш теми для зберігання в Redis SET."""
        return hashlib.md5(topic.encode()).hexdigest()[:16]

    async def _command(self, *args) -> any:
        """
        Виконує Redis-команду через Upstash REST API.
        URL формат: POST /COMMAND/arg1/arg2/...
        """
        parts = [str(a) for a in args]
        url = self.url + "/" + "/".join(parts)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

        # Upstash повертає {"result": ..., "error": ...}
        if "error" in data and data["error"]:
            raise RuntimeError(f"Redis error: {data['error']}")

        return data.get("result")
