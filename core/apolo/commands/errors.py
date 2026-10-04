"""El error de un comando: params inválidos, referencia a un sólido que no existe, geometría que
OCCT no puede construir. La API lo devuelve como 400 con su texto (sync y job iguales).

Vive aparte de `registry.py` para que `strict.py` (que `registry.py` importa) pueda lanzarlo sin
un import circular; `registry.CommandError` es el MISMO objeto (re-export).
"""


class CommandError(Exception):
    pass
