"""HTTP adapter for Open-Meteo geocoding and current weather."""

from datetime import UTC

import httpx
from pydantic import ValidationError

from weather_cache_api.schemas import (
    CurrentWeather,
    ForecastPayload,
    GeocodedLocation,
    GeocodingPayload,
    WeatherResponse,
)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,"
    "precipitation,weather_code,wind_speed_10m"
)


class CityNotFoundError(Exception):
    """The geocoding provider found no matching city."""


class ProviderTimeoutError(Exception):
    """The upstream service timed out."""


class ProviderUnavailableError(Exception):
    """The upstream service failed or refused the request."""


class InvalidProviderResponseError(Exception):
    """The upstream payload did not match our expected schema."""


class OpenMeteoClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def _get_json(self, url: str, params: dict[str, str | int | float]) -> object:
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError from exc
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise ProviderUnavailableError from exc
        try:
            return response.json()
        except ValueError as exc:
            raise InvalidProviderResponseError from exc

    async def fetch_weather(self, city: str) -> WeatherResponse:
        data = await self._get_json(
            GEOCODING_URL, {"name": city, "count": 1, "language": "en", "format": "json"}
        )
        try:
            places = GeocodingPayload.model_validate(data).results
        except ValidationError as exc:
            raise InvalidProviderResponseError from exc
        if not places:
            raise CityNotFoundError

        location: GeocodedLocation = places[0]
        forecast_data = await self._get_json(
            FORECAST_URL,
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current": CURRENT_FIELDS,
                "timezone": "GMT",
            },
        )
        try:
            current = ForecastPayload.model_validate(forecast_data).current
        except ValidationError as exc:
            raise InvalidProviderResponseError from exc
        # timezone=GMT makes Open-Meteo's offset-free timestamp represent UTC.
        observed_at = (
            current.time.replace(tzinfo=UTC)
            if current.time.tzinfo is None
            else current.time
        )
        return WeatherResponse(
            location=location,
            current=CurrentWeather(
                observed_at=observed_at,
                temperature_c=current.temperature_2m,
                apparent_temperature_c=current.apparent_temperature,
                relative_humidity_percent=current.relative_humidity_2m,
                precipitation_mm=current.precipitation,
                weather_code=current.weather_code,
                wind_speed_kmh=current.wind_speed_10m,
            ),
        )
