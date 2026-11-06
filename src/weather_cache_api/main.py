"""FastAPI entry point and HTTP error boundaries."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request

from weather_cache_api.cache import WeatherCache
from weather_cache_api.config import Settings
from weather_cache_api.open_meteo import (
    CityNotFoundError,
    InvalidProviderResponseError,
    OpenMeteoClient,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from weather_cache_api.schemas import WeatherResponse
from weather_cache_api.service import WeatherService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from redis import asyncio as redis  # Loaded at startup; keeps tests independent of Redis.

    settings = Settings()
    cache_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as http_client:
            app.state.weather_service = WeatherService(
                OpenMeteoClient(http_client), WeatherCache(cache_client, settings.cache_ttl_seconds)
            )
            yield
    finally:
        await cache_client.aclose()


def get_weather_service(request: Request) -> WeatherService:
    return request.app.state.weather_service


app = FastAPI(
    title="Weather Cache API",
    description="Current weather by city, backed by Open-Meteo and a Redis TTL cache.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/weather", response_model=WeatherResponse, tags=["weather"])
async def get_weather(
    city: Annotated[str, Query(min_length=1, max_length=100, description="City to search")],
    service: Annotated[WeatherService, Depends(get_weather_service)],
) -> WeatherResponse:
    city = " ".join(city.split())
    if not city:
        raise HTTPException(status_code=422, detail="City must not be blank")
    try:
        return await service.get_weather(city)
    except CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="City not found") from exc
    except ProviderTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Weather provider timed out") from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Weather provider is unavailable") from exc
    except InvalidProviderResponseError as exc:
        raise HTTPException(status_code=502, detail="Invalid weather provider response") from exc
