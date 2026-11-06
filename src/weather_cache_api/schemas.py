"""Validated upstream and public API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GeocodedLocation(BaseModel):
    name: str = Field(min_length=1)
    country: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class GeocodingPayload(BaseModel):
    results: list[GeocodedLocation] = Field(default_factory=list)


class CurrentPayload(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    time: datetime
    temperature_2m: float
    relative_humidity_2m: int = Field(ge=0, le=100)
    apparent_temperature: float
    precipitation: float
    weather_code: int
    wind_speed_10m: float


class ForecastPayload(BaseModel):
    current: CurrentPayload


class CurrentWeather(BaseModel):
    observed_at: datetime
    temperature_c: float
    apparent_temperature_c: float
    relative_humidity_percent: int
    precipitation_mm: float
    weather_code: int
    wind_speed_kmh: float


class WeatherResponse(BaseModel):
    location: GeocodedLocation
    current: CurrentWeather
    source: str = "open-meteo"
    cached: bool = False

class CacheMetricsResponse(BaseModel):
    cache_hits: int = Field(ge=0)
    cache_misses: int = Field(ge=0)
    cache_errors: int = Field(ge=0)
    hit_rate: float = Field(ge=0, le=1)
