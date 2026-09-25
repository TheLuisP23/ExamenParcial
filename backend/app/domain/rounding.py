"""Redondeo comercial (ROUND_HALF_UP) usado por el modelo `reglas-v1`.

specs/03-modelo-prediccion.md §1 exige redondeo "mitad hacia arriba" para el
cálculo de `visitantes_estimados`. El `round()` nativo de Python usa
"banker's rounding" (redondeo al par más cercano en los empates .5), que da
resultados distintos en los empates (ver `test_UT_11_...`), así que no sirve
aquí.
"""

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(x: float) -> int:
    """Redondea `x` al entero más cercano, con los empates ``.5`` hacia arriba.

    Se pasa por `str(x)` antes de construir el `Decimal` para redondear sobre
    la representación decimal "vista" del float (la misma que produce
    `repr()`/`str()`), evitando que el binario de coma flotante subyacente
    (p. ej. 230.5 no es exactamente representable) introduzca un sesgo hacia
    abajo o arriba distinto del que espera un humano leyendo el número.
    """
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
