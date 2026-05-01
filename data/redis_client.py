import json
import httpx
from config import UPSTASH_REDIS_URL, UPSTASH_REDIS_TOKEN, MAX_USED_TOPICS_IN_PROMPT

# ─────────────────────────────────────────
# Базовий клієнт Upstash Redis (REST API)
# ─────────────────────────────────────────

HEADERS = {
    "Authorization": f"Bearer {UPSTASH_REDIS_TOKEN}",
    "Content-Type": "application/json",
}


async def _request(command: list) -> dict:
    """Виконує Redis команду через Upstash REST API."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            UPSTASH_REDIS_URL,
            headers=HEADERS,
            json=command,
        )
        response.raise_for_status()
        return response.json()


# ─────────────────────────────────────────
# БАЗОВІ ОПЕРАЦІЇ
# ─────────────────────────────────────────

async def get(key: str) -> str | None:
    result = await _request(["GET", key])
    return result.get("result")


async def set(key: str, value: str, ex: int = None) -> bool:
    """Зберігає значення. ex — TTL в секундах (необов'язково)."""
    cmd = ["SET", key, value]
    if ex:
        cmd += ["EX", ex]
    result = await _request(cmd)
    return result.get("result") == "OK"


async def delete(key: str) -> bool:
    result = await _request(["DEL", key])
    return result.get("result", 0) > 0


async def incr(key: str) -> int:
    result = await _request(["INCR", key])
    return result.get("result", 0)


# ─────────────────────────────────────────
# SET ОПЕРАЦІЇ (для унікальних тем)
# ─────────────────────────────────────────

async def sadd(key: str, *values: str) -> int:
    """Додає значення в Set."""
    result = await _request(["SADD", key, *values])
    return result.get("result", 0)


async def smembers(key: str) -> set:
    """Повертає всі елементи Set."""
    result = await _request(["SMEMBERS", key])
    return set(result.get("result", []))


async def sismember(key: str, value: str) -> bool:
    """Перевіряє чи є значення в Set."""
    result = await _request(["SISMEMBER", key, value])
    return result.get("result", 0) == 1


# ─────────────────────────────────────────
# LIST ОПЕРАЦІЇ (для черги постів)
# ─────────────────────────────────────────

async def lpush(key: str, value: str) -> int:
    result = await _request(["LPUSH", key, value])
    return result.get("result", 0)


async def rpop(key: str) -> str | None:
    result = await _request(["RPOP", key])
    return result.get("result")


async def lrange(key: str, start: int = 0, end: int = -1) -> list:
    result = await _request(["LRANGE", key, start, end])
    return result.get("result", [])


async def lrem(key: str, count: int, value: str) -> int:
    result = await _request(["LREM", key, count, value])
    return result.get("result", 0)


# ─────────────────────────────────────────
# HASH ОПЕРАЦІЇ (для збереження даних квізу)
# ─────────────────────────────────────────

async def hset(key: str, field: str, value: str) -> int:
    result = await _request(["HSET", key, field, value])
    return result.get("result", 0)


async def hget(key: str, field: str) -> str | None:
    result = await _request(["HGET", key, field])
    return result.get("result")


async def hgetall(key: str) -> dict:
    result = await _request(["HGETALL", key])
    raw = result.get("result", [])
    # Upstash повертає плоский список [key, val, key, val...]
    return dict(zip(raw[::2], raw[1::2])) if raw else {}


async def hdel(key: str, field: str) -> int:
    result = await _request(["HDEL", key, field])
    return result.get("result", 0)


# ─────────────────────────────────────────
# EXPIRE
# ─────────────────────────────────────────

async def expire(key: str, seconds: int) -> bool:
    result = await _request(["EXPIRE", key, seconds])
    return result.get("result", 0) == 1


# ─────────────────────────────────────────
# ДОПОМІЖНІ ФУНКЦІЇ ДЛЯ БОТА
# ─────────────────────────────────────────

async def get_used_topics(rubric_key: str) -> list:
    """Повертає список використаних тем для рубрики (макс MAX_USED_TOPICS_IN_PROMPT)."""
    topics = await smembers(f"{rubric_key}:used_topics")
    return list(topics)[:MAX_USED_TOPICS_IN_PROMPT]


async def save_topic(rubric_key: str, topic: str) -> None:
    """Зберігає використану тему для рубрики."""
    await sadd(f"{rubric_key}:used_topics", topic)


async def get_autopilot() -> bool:
    """Перевіряє чи увімкнений автопілот."""
    value = await get("settings:autopilot")
    return value == "on"


async def set_autopilot(enabled: bool) -> None:
    """Вмикає або вимикає автопілот."""
    await set("settings:autopilot", "on" if enabled else "off")


async def get_last_template() -> list:
    """Повертає останні 2 використаних шаблони (щоб не повторювати)."""
    value = await get("settings:last_templates")
    return json.loads(value) if value else []


async def save_last_template(template_name: str) -> None:
    """Зберігає останні 2 шаблони."""
    last = await get_last_template()
    last.append(template_name)
    await set("settings:last_templates", json.dumps(last[-2:]))


async def get_monitor_count_today() -> int:
    """Скільки реалтайм постів опубліковано сьогодні."""
    value = await get("monitor:daily_count")
    return int(value) if value else 0


async def increment_monitor_count() -> None:
    """+1 до лічильника реалтайм постів. Скидається о півночі."""
    key = "monitor:daily_count"
    await incr(key)
    await expire(key, 86400)  # 24 години


async def is_published(item_id: str) -> bool:
    """Перевіряє чи вже публікували цей пост/відео."""
    return await sismember("monitor:published_ids", item_id)


async def mark_published(item_id: str) -> None:
    """Позначає пост як опублікований."""
    await sadd("monitor:published_ids", item_id)


async def save_quiz_pending(poll_id: str, data: dict) -> None:
    """Зберігає дані квізу для відповіді через 24 год."""
    await set(f"quiz:pending:{poll_id}", json.dumps(data), ex=172800)  # 48 год


async def add_quiz_pending_id(poll_id: str) -> None:
    """Додає poll_id у список pending квізів."""
    await lpush("quiz:pending_ids", poll_id)


async def get_quiz_pending(poll_id: str) -> dict | None:
    """Витягує дані квізу за poll_id."""
    value = await get(f"quiz:pending:{poll_id}")
    return json.loads(value) if value else None


async def clear_quiz_pending(poll_id: str) -> None:
    """Видаляє pending-дані та poll_id зі списку."""
    await delete(f"quiz:pending:{poll_id}")
    await lrem("quiz:pending_ids", 0, poll_id)


async def clear_weekly_topics() -> None:
    """Очищає список тем тижня (запускається в неділю для дайджесту)."""
    await delete("weekly:posts")


async def add_weekly_topic(topic: str) -> None:
    """Додає тему до списку тижня для дайджесту."""
    await lpush("weekly:posts", topic)


async def get_weekly_topics() -> list:
    """Повертає всі теми тижня."""
    return await lrange("weekly:posts")
