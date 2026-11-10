# Architecture decisions (Cycles 1 and 2)

## ADR-001: FastAPI with one service and two adapters

**Decision:** HTTP validation and status mapping stay in main.py; WeatherService coordinates retrieval; OpenMeteoClient owns upstream HTTP; WeatherCache owns Redis. No queues, database, frontend, or unnecessary abstractions.

**Rationale:** Clear test seams and a straightforward story for an international engineering interview.

## ADR-002: Cache successful, validated weather responses by normalized city

**Decision:** Cache key weather:v1:{trimmed-casefolded-city}. TTL: 600 seconds by default, configured between 1 and 86,400 seconds. The cached field is changed to true only upon cache read.

**Tradeoffs:** City names can be ambiguous. Each distinct spelling may have a different cache key. Two simultaneous misses can call the provider twice; this is acceptable in Cycle 1.

## ADR-003: Fail open on cache failure, fail explicitly on provider failure

**Decision:** Redis GET/SET errors are logged and treated as cache misses / failed writes. Missing cities return 404; timeouts 504; other upstream HTTP/network failures 503; malformed upstream JSON/schema 502. No invented weather values.

## ADR-004: In-process cache metrics

**Decision:** Expose `GET /metrics` for hits, misses, cache errors and hit rate. Counters belong to a single process, reset on restart, and are not shared across workers.

**Tradeoff:** Minimal overhead and no extra dependency, but not a durable or distributed monitoring system. The metrics endpoint is unauthenticated; do not publish detailed operations metrics without review.

## ADR-005: Atomic, fixed-window per-IP limiter

**Decision:** Use a Redis Lua script (INCR + conditional EXPIRE + TTL) to ensure atomic updates. The default is 60 requests per 60-second window per ASGI peer IP. Redis keys contain SHA-256 digests of IP strings; this is pseudonymization, not anonymization.

**Tradeoffs:** Predictable and easy to test, but fixed-window boundaries allow bursts. ASGI peer IP is inappropriate behind proxies unless proxy trust is configured. The limiter intentionally fails open on Redis outages to preserve weather API availability; it is **not a security boundary**.

## ADR-006: Reproducible synthetic latency experiment

**Decision:** Measure cold and warm `WeatherService` calls against real Redis and an artificial delayed `httpx.MockTransport` provider. Use unique cache keys, delete before cold samples, seed before warm samples and print observed timing statistics.

**Tradeoffs:** Reproducible methodology and measured runtime values, but the artificial upstream latency is **not** a live provider benchmark or end-to-end HTTP result.

## Verification and next steps

Unit tests mock upstream HTTP and cache responses. Two opt-in tests verify real Redis TTL expiry and the rate-limiter window. GitHub Actions runs these tests with Redis 7 and Python 3.14, then executes the synthetic benchmark. All numeric results must come from actual CI logs or a local run, never estimates.

Status: Cycles 1 and 2 are integrated into the protected `main` branch after CI validation and Codex review. Future work includes production-like reverse-proxy deployment checks and observability aggregation. A separate advisory Actions workflow performs live Open-Meteo smoke validation; check its outcome in GitHub run logs.

Measured synthetic CI run: [benchmark methodology and observed results](performance.md).
