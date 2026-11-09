# Performance measurements

> **Important:** These are **measured synthetic service-layer timings**, not real Open-Meteo responses, production throughput, or end-to-end HTTP latencies. The benchmark intentionally injects artificial upstream delay. Do not present the median ratio below as a production speedup.

## Reproducible procedure

1. Start a dedicated Redis instance using `docker compose up -d redis`.
2. Install Python 3.14 and dependencies with `python -m pip install -e '.[dev]'`.
3. Execute `python scripts/benchmark.py --samples 10 --delay-ms 20`.
4. Each uncached sample deletes a unique cache key, then calls `WeatherService` (one geocoding and one weather request, each delayed by 20 ms in `httpx.MockTransport`).
5. Warm samples reuse one valid cached response; checks assert no upstream request was made.
6. The script reports measured mean, median (p50), p95, and median ratio. All timings include service processing plus real Redis requests but **exclude** ASGI HTTP transport and real provider variability.

## Observed CI result (2026-11-06)

**Source:** [GitHub Actions CI run #11](https://github.com/RamonRDR/weather-cache-api/actions/runs/42288744402), Python 3.14.10 on GitHub-hosted Ubuntu, Redis 7 Alpine service, commit `c6059afb20228548cf3bafecd095431fd8a75979`.

| Metric | Cache miss (cold) | Cache hit (warm) |
| --- | ---: | ---: |
| Samples | 10 | 10 |
| Mean | 41.011 ms | 0.114 ms |
| p50 | 40.944 ms | 0.095 ms |
| p95 | 41.472 ms | 0.234 ms |

Observed ratio of medians: **430.99×** in this synthetic experiment. This is not a guaranteed improvement in real deployments. Two artificial 20 ms delays account for most uncached duration, while the warm path skips both simulated calls. Upstream request count was 22 (20 for ten cold samples, 2 to seed the warm cache, 0 during ten warm samples).

The same run reported **17 pytest tests passed**, Ruff lint and formatting passed, and the benchmark step succeeded. One Starlette/httpx deprecation warning appeared in the test suite.

## Interpretation and limitations

- The experiment demonstrates that cached requests avoid the two costly upstream calls in a controlled environment.
- Results change with machine load, network, provider latency, Redis topology, concurrency and cache hit ratio.
- A production-oriented future study should add real provider latency distribution, concurrency, p99, error rates, TTL churn, and end-to-end HTTP measurements.
- Never compare this synthetic 430.99× ratio directly with a production performance claim.
