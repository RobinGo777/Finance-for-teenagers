"""
Отримання фото через Pexels API.
Безкоштовно, 200 req/год, без реєстрації картки.
"""

import random
import logging
import httpx

logger = logging.getLogger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# Запасні фото на випадок збою API
FALLBACK = {
    "economics":  "https://images.pexels.com/photos/210574/pexels-photo-210574.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "ai":         "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "stocks":     "https://images.pexels.com/photos/534216/pexels-photo-534216.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "crypto":     "https://images.pexels.com/photos/844124/pexels-photo-844124.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "finance":    "https://images.pexels.com/photos/4386321/pexels-photo-4386321.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "digest":     "https://images.pexels.com/photos/518543/pexels-photo-518543.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "default":    "https://images.pexels.com/photos/6802042/pexels-photo-6802042.jpeg?auto=compress&cs=tinysrgb&w=1200",
}


class MediaFetcher:
    def __init__(self, api_key: str):
        self.headers = {"Authorization": api_key}

    async def fetch(self, query: str | None) -> str | None:
        """
        Повертає URL landscape-фото з Pexels.
        Якщо query=None — повертає None (для опитувань).
        """
        if not query:
            return None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    PEXELS_SEARCH_URL,
                    headers=self.headers,
                    params={
                        "query": query,
                        "per_page": 20,
                        "orientation": "landscape",
                    },
                )
                resp.raise_for_status()
                photos = resp.json().get("photos", [])

            if not photos:
                logger.warning(f"Pexels: немає фото для «{query}», використовую fallback")
                return self._fallback(query)

            # Рандомне фото з топ-20 — щоб не повторювалися
            photo = random.choice(photos)
            url = photo["src"].get("large2x") or photo["src"]["original"]
            logger.info(f"📷 Pexels фото: {url[:70]}…")
            return url

        except httpx.HTTPError as e:
            logger.warning(f"Pexels API помилка: {e}")
            return self._fallback(query)

    def _fallback(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["econom", "money world", "gdp"]):
            return FALLBACK["economics"]
        if any(w in q for w in ["intelligen", "digital", "tech", "robot"]):
            return FALLBACK["ai"]
        if any(w in q for w in ["stock", "trading", "chart", "invest"]):
            return FALLBACK["stocks"]
        if any(w in q for w in ["bitcoin", "crypto", "blockchain"]):
            return FALLBACK["crypto"]
        if any(w in q for w in ["finance", "saving", "budget", "personal"]):
            return FALLBACK["finance"]
        if any(w in q for w in ["news", "weekly", "summary"]):
            return FALLBACK["digest"]
        return FALLBACK["default"]
