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
- Errores: 404 ciudad no encontrada; 422 entrada inválida; 502 respuesta externa inválida; 503 proveedor no disponible; 504 tiempo de espera agotado.
- Pruebas sin conexión: `python -m pytest -q`.
- Calidad: `ruff check .` y `ruff format --check .`.

## Alcance

El Ciclo 1 implementa la base funcional. Las métricas de caché, los límites de frecuencia, las pruebas reales de caducidad en Redis y los benchmarks reproducibles corresponden al Ciclo 2. No se afirman mejoras de rendimiento no medidas. Consulte el [README principal](README.md) para arquitectura, un ejemplo JSON **ilustrativo** y decisiones técnicas.

Datos de [Open-Meteo](https://open-meteo.com/en/docs) sujetos a sus [condiciones](https://open-meteo.com/en/terms). Código MIT.
