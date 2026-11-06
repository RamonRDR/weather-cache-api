"""Live end-to-end smoke test for Open-Meteo via the running Docker Compose API.

Unlike unit tests and synthetic benchmarks, this makes real network requests
through /weather to Open-Meteo geocoding and forecast APIs. Run only on demand
or in the separate advisory GitHub Actions workflow.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_json(base_url: str, path: str, params: dict[str, str] | None = None) -> dict:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{base_url.rstrip('/')}{path}{query}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} returned HTTP {exc.code}: {body}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"{path} request failed: {exc}") from exc


def wait_until_ready(base_url: str, timeout_seconds: float = 45) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            schema = get_json(base_url, "/openapi.json")
            if "/weather" in schema["paths"] and "/metrics" in schema["paths"]:
                return
        except RuntimeError, KeyError, ValueError:
            pass
        time.sleep(1)
    raise RuntimeError("API did not become ready before the smoke-test deadline")


def assert_valid_weather(payload: dict, city: str, cached: bool) -> None:
    assert payload["source"] == "open-meteo", "Unexpected data provider"
    assert payload["cached"] is cached, f"Expected cached={cached}"
    location = payload["location"]
    assert city.casefold() in location["name"].casefold(), "Geocoding returned a different city"
    assert location["country"], "Geocoding response has no country"
    assert -90 <= location["latitude"] <= 90
    assert -180 <= location["longitude"] <= 180
    current = payload["current"]
    datetime.fromisoformat(current["observed_at"].replace("Z", "+00:00"))
    for field in (
        "temperature_c",
        "apparent_temperature_c",
        "precipitation_mm",
        "wind_speed_kmh",
    ):
        assert isinstance(current[field], (int, float)), f"Invalid {field}"
    assert 0 <= current["relative_humidity_percent"] <= 100


def run_smoke(base_url: str, city: str) -> str:
    wait_until_ready(base_url)
    first = get_json(base_url, "/weather", {"city": city})
    assert_valid_weather(first, city=city, cached=False)
    second = get_json(base_url, "/weather", {"city": city})
    assert_valid_weather(second, city=city, cached=True)
    assert first["location"] == second["location"]
    assert first["current"] == second["current"]
    metrics = get_json(base_url, "/metrics")
    assert metrics["cache_misses"] >= 1, "Expected at least one cache miss"
    assert metrics["cache_hits"] >= 1, "Expected at least one cache hit"
    return (
        f"Real Open-Meteo geocoding and forecast succeeded for {city}; "
        "the second request came from Redis cache."
    )


def write_summary(success: bool, message: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    status = "PASS" if success else "FAIL"
    text = (
        "## Live Open-Meteo smoke test\n\n"
        f"**{status}**: {message}\n\n"
        "Uses the full Docker Compose stack and real external Open-Meteo calls. "
        "This is an advisory live test, not the required mocked CI check. "
        "External provider availability can change.\n"
    )
    with Path(summary_path).open("a", encoding="utf-8") as file:
        file.write(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", default="Berlin")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        message = run_smoke(args.base_url, args.city)
    except (AssertionError, KeyError, ValueError, RuntimeError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        print(f"LIVE SMOKE FAILED: {message}", file=sys.stderr)
        write_summary(False, message)
        return 1
    print(f"LIVE SMOKE PASSED: {message}")
    write_summary(True, message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
