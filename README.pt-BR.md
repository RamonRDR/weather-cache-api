# Weather Cache API

[English](README.md) · [Español](README.es.md)

API REST de meteorologia com **Python 3.14, FastAPI, Pydantic, httpx, Open-Meteo e Redis**. O nome da cidade é convertido em coordenadas, a previsão atual é consultada na Open-Meteo e a resposta validada é armazenada no Redis com TTL configurável.

## Como executar

```bash
docker compose up --build
curl 'http://localhost:8000/weather?city=Itajai'
```

Documentação interativa: http://localhost:8000/docs

Para executar fora do Docker: instale Python 3.14, rode `python -m pip install -e '.[dev]'`, copie `.env.example` para `.env`, inicie Redis e execute `uvicorn weather_cache_api.main:app --reload`.

## Funcionamento

- Endpoint: `GET /weather?city=Itajai`.
- Geocoding: primeiro resultado retornado pela Open-Meteo.
- Cache: chave normalizada, TTL padrão de 600 segundos e indicador `cached`.
- Métricas: `GET /metrics` mostra hits, misses, erros e taxa de acerto **por processo** (reinicia com o servidor).
- Rate limiting: limite padrão de 60 requisições por 60 segundos por IP; devolve HTTP 429 com `Retry-After`. Se o Redis falhar, o limite é ignorado para manter a API disponível.
- Erros: 404 cidade não encontrada; 422 parâmetro inválido; 502 resposta externa inválida; 503 provedor indisponível; 504 timeout.
- Testes offline: `python -m pytest -q`.
- Qualidade: `ruff check .` e `ruff format --check .`.

## Testes de integração e benchmark

```bash
docker compose up -d redis
RUN_REDIS_TESTS=1 REDIS_TEST_URL=redis://localhost:6379/15 python -m pytest -q
python scripts/benchmark.py --samples 30 --delay-ms 30
```

No PowerShell, configure `$env:RUN_REDIS_TESTS='1'` e `$env:REDIS_TEST_URL='redis://localhost:6379/15'` antes do pytest. O CI executa esses testes com Redis real. O benchmark usa Redis real e um provedor HTTP **simulado** para coletar latências observadas, sem afirmar desempenho em produção. O limite por IP depende do endereço ASGI, ignora cabeçalhos de proxy não confiáveis e falha aberto quando o Redis está indisponível.

## Escopo

Os Ciclos 1 e 2 estão implementados na branch de revisão. O projeto ainda não foi implantado em produção. Veja o [README em inglês](README.md) para arquitetura, exemplo JSON **ilustrativo**, limitações e decisões técnicas.

Dados de [Open-Meteo](https://open-meteo.com/en/docs), sujeitos aos [termos do provedor](https://open-meteo.com/en/terms). Código MIT.
