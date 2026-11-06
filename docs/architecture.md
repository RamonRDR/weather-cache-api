# Architecture decisions (Cycle 1)

## ADR-001: FastAPI with one service and two adapters

**Decision:** HTTP validation and status mapping stay in main.py; WeatherService coordinates retrieval; OpenMeteoClient owns upstream HTTP; WeatherCache owns Redis. No queues, database, frontend, or unnecessary abstractions.

**Rationale:** Clear test seams and a straightforward story for an international engineering interview.

## ADR-002: Cache successful, validated weather responses by normalized city

**Decision:** Cache key weather:v1:{trimmed-casefolded-city}. TTL: 600 seconds by default, configured between 1 and 86,400 seconds. The cached field is changed to true only upon cache read.

**Tradeoffs:** City names can be ambiguous. Each distinct spelling may have a different cache key. Two simultaneous misses can call the provider twice; this is acceptable in Cycle 1.

## ADR-003: Fail open on cache failure, fail explicitly on provider failure

**Decision:** Redis GET/SET errors are logged and treated as cache misses / failed writes. Missing cities return 404; timeouts 504; other upstream HTTP/network failures 503; malformed upstream JSON/schema 502. No invented weather values.

## Verification and future work

HTTP is mocked with httpx.MockTransport. An in-memory Redis stand-in verifies TTL arguments and cache behavior. This **does not** demonstrate real Redis expiration or a measured performance gain. Cycle 2 will add Redis integration tests, hit/miss metrics, rate limiting, and reproducible cold/warm performance tests with real timings.
