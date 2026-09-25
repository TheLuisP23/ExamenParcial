"""Clientes de servicios externos (specs/04-api.md §4: `app/clients/weatherapi.py`).

`app/domain/` nunca importa de este paquete (arquitectura limpia); es este
paquete el que, cuando aplique, puede apoyarse en tipos de `app/domain/` --
en la práctica `app/clients/weatherapi.py` no lo hace: expone sus propias
estructuras de datos (`DayForecast`, `HourlyForecastPoint`, ...) para no
acoplar el cliente HTTP al modelo de predicción; BE-06 hace el mapeo hacia
`app.domain.factors.ClimaInput`/`HourlyPoint`.
"""
