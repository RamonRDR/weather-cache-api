"""Weather retrieval orchestration, independent of FastAPI."""

from weather_cache_api.cache import WeatherCache
from weather_cache_api.open_meteo import OpenMeteoClient
from weather_cache_api.schemas import WeatherResponse


class WeatherService:
    def __init__(self, provider: OpenMeteoClient, cache: WeatherCache) -> None:
        self.provider = provider
        self.cache = cache

    async def get_weather(self, city: str) -> WeatherResponse:
        normalized_city = " ".join(city.split())
        cached = await self.cache.get(normalized_city)
        if cached is not None:
            return cached.model_copy(update={"cached": True})
        result = await self.provider.fetch_weather(normalized_city)
        await self.cache.set(normalized_city, result)
        return result
