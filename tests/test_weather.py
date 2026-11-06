"""Deterministic API and service tests: no network or Redis server needed."""

import httpx
import pytest
from fastapi.testclient import TestClient

from weather_cache_api.cache import WeatherCache
from weather_cache_api.limiter import RateLimitDecision, RateLimiter
from weather_cache_api.main import app, enforce_rate_limit, get_rate_limiter, get_weather_service
from weather_cache_api.open_meteo import OpenMeteoClient
from weather_cache_api.service import WeatherService

GEO = {
    "results": [{"name": "Itajaí", "country": "Brazil", "latitude": -26.91, "longitude": -48.66}]
}
FORECAST = {
    "current": {
        "time": "2026-11-06T12:00",
        "temperature_2m": 24.1,
        "relative_humidity_2m": 67,
        "apparent_temperature": 25.0,
        "precipitation": 0.0,
        "weather_code": 2,
        "wind_speed_10m": 12.4,
    }
}


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.expiries: dict[str, int] = {}
        self.get_calls = 0
        self.fail = False

    async def get(self, name: str) -> str | None:
        self.get_calls += 1
        if self.fail:
            raise ConnectionError("redis unavailable")
        return self.data.get(name)

    async def set(self, name: str, value: str, ex: int) -> None:
        if self.fail:
            raise ConnectionError("redis unavailable")
        self.data[name] = value
        self.expiries[name] = ex


@pytest.fixture
def setup_api():
    calls: list[str] = []
    cache_client = FakeRedis()
    state = {"geo": GEO, "forecast": FORECAST, "error": None}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if state["error"] == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if state["error"] == "status":
            return httpx.Response(503)
        if "search" in request.url.path:
            return httpx.Response(200, json=state["geo"])
        return httpx.Response(200, json=state["forecast"])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = WeatherService(OpenMeteoClient(http), WeatherCache(cache_client, 120))
    app.dependency_overrides[get_weather_service] = lambda: service
    app.dependency_overrides[enforce_rate_limit] = lambda: None
    try:
        client = TestClient(app)
        yield client, cache_client, calls, state
    finally:
        app.dependency_overrides.clear()


def test_weather_cache_miss_then_hit(setup_api):
    client, redis, calls, _ = setup_api
    first = client.get("/weather", params={"city": " Itajaí "})
    assert first.status_code == 200
    assert first.json()["cached"] is False
    assert first.json()["current"]["temperature_c"] == 24.1
    assert first.json()["current"]["observed_at"] == "2026-11-06T12:00:00Z"
    assert len(calls) == 2
    assert redis.expiries["weather:v1:itajaí"] == 120

    second = client.get("/weather", params={"city": "ITAJAÍ"})
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert len(calls) == 2


def test_city_not_found(setup_api):
    client, _, calls, state = setup_api
    state["geo"] = {}
    response = client.get("/weather", params={"city": "Nowhere"})
    assert response.status_code == 404
    assert response.json() == {"detail": "City not found"}
    assert len(calls) == 1


def test_timeout_maps_to_504(setup_api):
    client, _, _, state = setup_api
    state["error"] = "timeout"
    assert client.get("/weather", params={"city": "Itajai"}).status_code == 504


def test_upstream_http_error_maps_to_503(setup_api):
    client, _, _, state = setup_api
    state["error"] = "status"
    assert client.get("/weather", params={"city": "Itajai"}).status_code == 503


def test_invalid_forecast_maps_to_502(setup_api):
    client, _, _, state = setup_api
    state["forecast"] = {"current": {"temperature_2m": "invalid"}}
    assert client.get("/weather", params={"city": "Itajai"}).status_code == 502


def test_invalid_geocoding_maps_to_502(setup_api):
    client, _, _, state = setup_api
    state["geo"] = {"results": [{"name": "A"}]}
    assert client.get("/weather", params={"city": "Itajai"}).status_code == 502


def test_invalid_input_is_rejected(setup_api):
    client, _, calls, _ = setup_api
    assert client.get("/weather").status_code == 422
    assert client.get("/weather", params={"city": "   "}).status_code == 422
    assert calls == []


def test_redis_outage_falls_back_to_upstream(setup_api):
    client, redis, calls, _ = setup_api
    redis.fail = True
    response = client.get("/weather", params={"city": "Itajai"})
    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert len(calls) == 2


def test_corrupt_cache_entry_is_ignored(setup_api):
    client, redis, calls, _ = setup_api
    redis.data["weather:v1:itajai"] = "{not-json}"
    response = client.get("/weather", params={"city": "Itajai"})
    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert len(calls) == 2


def test_openapi_schema_exposes_weather(setup_api):
    client, _, _, _ = setup_api
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/weather" in schema.json()["paths"]
    assert client.get("/docs").status_code == 200


def test_cache_metrics_on_hit_and_miss(setup_api):
    client, _, _, _ = setup_api
    assert client.get("/metrics").json() == {
        "cache_hits": 0, "cache_misses": 0, "cache_errors": 0, "hit_rate": 0.0
    }
    client.get("/weather", params={"city": "Itajai"})
    client.get("/weather", params={"city": "Itajai"})
    assert client.get("/metrics").json() == {
        "cache_hits": 1, "cache_misses": 1, "cache_errors": 0, "hit_rate": 0.5
    }


def test_cache_metrics_count_redis_errors(setup_api):
    client, redis, _, _ = setup_api
    redis.fail = True
    client.get("/weather", params={"city": "Itajai"})
    assert client.get("/metrics").json() == {
        "cache_hits": 0, "cache_misses": 1, "cache_errors": 2, "hit_rate": 0.0
    }


def test_rate_limit_429_with_retry_after(setup_api):
    client, _, _, _ = setup_api

    class RejectOnThird:
        def __init__(self):
            self.count = 0

        async def check(self, ip):
            assert ip == "testclient"
            self.count += 1
            return RateLimitDecision(allowed=self.count <= 2, retry_after_seconds=9)

    limiter = RejectOnThird()
    app.dependency_overrides.pop(enforce_rate_limit)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    for _ in range(2):
        assert client.get("/weather", params={"city": "Itajai"}).status_code == 200
    blocked = client.get("/weather", params={"city": "Itajai"})
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "9"


def test_rate_limiter_uses_atomic_script_and_hashed_keys():
    import asyncio

    class FakeRedisEval:
        def __init__(self):
            self.count = 0

        async def eval(self, script, numkeys, key, seconds):
            assert "INCR" in script and "EXPIRE" in script
            assert numkeys == 1
            assert key.startswith("rate:v1:") and "127.0.0.1" not in key
            assert seconds == 60
            self.count += 1
            return [self.count, 42]

    async def verify():
        limiter = RateLimiter(FakeRedisEval(), requests=2, window_seconds=60)
        assert (await limiter.check("127.0.0.1")).allowed
        assert (await limiter.check("127.0.0.1")).allowed
        third = await limiter.check("127.0.0.1")
        assert not third.allowed
        assert third.retry_after_seconds == 42

    asyncio.run(verify())


def test_rate_limiter_fail_open_when_redis_is_down():
    import asyncio

    class BrokenRedis:
        async def eval(self, *args):
            raise ConnectionError("redis unavailable")

    decision = asyncio.run(RateLimiter(BrokenRedis(), 1, 60).check("127.0.0.1"))
    assert decision.allowed
