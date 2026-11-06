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
- Erros: 404 cidade não encontrada; 422 parâmetro inválido; 502 resposta externa inválida; 503 provedor indisponível; 504 timeout.
- Testes offline: `python -m pytest -q`.
- Qualidade: `ruff check .` e `ruff format --check .`.

## Escopo

O Ciclo 1 implementa os recursos básicos. Métricas do cache, rate limiting, expiração real com Redis e benchmarks reproduzíveis fazem parte do Ciclo 2. Nenhum ganho de desempenho foi medido ou afirmado. Veja [o README principal](README.md) para a arquitetura, amostra JSON **ilustrativa** e decisões técnicas.

Dados de [Open-Meteo](https://open-meteo.com/en/docs), sujeitos aos [termos do provedor](https://open-meteo.com/en/terms). Código MIT.
