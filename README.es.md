# Weather Cache API

[English](README.md) · [Português](README.pt-BR.md)

API REST meteorológica creada con **Python 3.14, FastAPI, Pydantic, httpx, Open-Meteo y Redis**. Convierte nombres de ciudades en coordenadas, consulta las condiciones actuales y almacena respuestas validadas en Redis con caducidad configurable.

## Inicio rápido

```bash
docker compose up --build
curl 'http://localhost:8000/weather?city=Itajai'
```

Documentación interactiva: http://localhost:8000/docs

Para ejecutar sin Docker: instale Python 3.14, ejecute `python -m pip install -e '.[dev]'`, copie `.env.example` a `.env`, inicie Redis y use `uvicorn weather_cache_api.main:app --reload`.

## Comportamiento

- Endpoint: `GET /weather?city=Itajai`.
- Geocodificación: se selecciona el primer resultado de Open-Meteo.
- Caché: clave normalizada, TTL de 600 segundos por defecto y campo `cached`.
- Métricas: `GET /metrics` muestra aciertos, fallos, errores y tasa de aciertos **por proceso** (se reinicia con el servidor).
- Límite de solicitudes: 60 peticiones por 60 segundos por IP; devuelve HTTP 429 con `Retry-After`. Si Redis falla, el límite permite las solicitudes para mantener la disponibilidad.
- Errores: 404 ciudad no encontrada; 422 entrada inválida; 502 respuesta externa inválida; 503 proveedor no disponible; 504 tiempo de espera agotado.
- Pruebas sin conexión: `python -m pytest -q`.
- Calidad: `ruff check .` y `ruff format --check .`.

## Pruebas de integración y benchmark

```bash
docker compose up -d redis
RUN_REDIS_TESTS=1 REDIS_TEST_URL=redis://localhost:6379/15 python -m pytest -q
python scripts/benchmark.py --samples 30 --delay-ms 30
```

En PowerShell, configure `$env:RUN_REDIS_TESTS='1'` y `$env:REDIS_TEST_URL='redis://localhost:6379/15'` antes de ejecutar pytest. CI ejecuta las pruebas con Redis real. El benchmark mide latencia real de ejecución con Redis y un proveedor HTTP **simulado**, sin afirmar rendimiento de producción. Consulte los [resultados medidos en CI](docs/performance.md), con metodología y limitaciones. El límite por IP usa el par ASGI, ignora cabeceras de proxy no confiables y permite solicitudes si Redis deja de funcionar.

## Prueba real de Open-Meteo en GitHub Actions

El workflow separado [Live Open-Meteo smoke test](.github/workflows/live-smoke.yml) inicia API y Redis con Docker Compose, consulta **Berlín** en las APIs reales de geocodificación y pronóstico, y verifica que la segunda solicitud se sirva desde Redis. Es una prueba **informativa**, no el control obligatorio `quality`, porque el proveedor externo puede fallar. Se ejecuta con cambios pertinentes del PR y puede lanzarse manualmente cuando el workflow esté en la rama principal. No requiere credenciales.

## Alcance

Los Ciclos 1 y 2 están implementados en la rama de revisión. No hay despliegue a producción. Consulte el [README en inglés](README.md) para arquitectura, ejemplo JSON **ilustrativo**, limitaciones y decisiones técnicas.

Datos de [Open-Meteo](https://open-meteo.com/en/docs) sujetos a sus [condiciones](https://open-meteo.com/en/terms). Código MIT.
