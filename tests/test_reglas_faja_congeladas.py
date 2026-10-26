"""Red de `conveyor_engineering_check`: tres casos congelados, TEXTO A TEXTO.

Plan [partir-nucleo-congelado-ii](../docs/plans/partir-nucleo-congelado-ii.md), F3 (D5 a, D7):
la función se partió por EXTRACCIÓN en bloques (`library/rules_faja_*.py`) con el estado en
`ContextoFaja`, y el gate del corte fue un corpus de 56 llamadas con salida idéntica. Estos tres
(los que más líneas de la función cubren juntos: 310 de 351) quedan como red permanente para que
una edición futura de la extracción no cambie una cifra, un texto ni el orden de las reglas sin
que se note. Incluye el dict `conveyor` DESPUÉS de la llamada: la adherencia le escribe
`pull_n` y `bearing_radial_n`, que lee la vida L10.

Un cambio DELIBERADO de una regla actualiza `tests/data/reglas_faja_congeladas.json` en el mismo
commit, con el motivo.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apolo.library.rules import conveyor_engineering_check

CASOS = json.loads((Path(__file__).parent / "data" / "reglas_faja_congeladas.json")
                   .read_text(encoding="utf-8"))


def _texto(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


@pytest.mark.parametrize("caso", CASOS, ids=[c["origen"] for c in CASOS])
def test_reglas_de_la_faja_salen_identicas(caso):
    conveyor = copy.deepcopy(caso["conveyor"])
    reglas = conveyor_engineering_check(conveyor, **caso["argumentos"])
    assert _texto(reglas) == _texto(caso["reglas"])
    assert _texto(conveyor) == _texto(caso["conveyor_despues"])


def test_los_casos_cubren_las_tres_construcciones():
    """Banda sobre rodillos (ISO 5048), banda sobre cama (CEMA) y rodillos: si alguien cambia el
    JSON por casos más pobres, la red pierde ramas."""
    normas = {r.get("calc", {}).get("norma") for c in CASOS for r in c["reglas"]
              if r["regla"] == "arrastre de banda"}
    assert normas == {"ISO 5048 / DIN 22101", "CEMA (unit handling) — slider bed, μ = 0.30–0.35"}
    assert any(c["conveyor"].get("tipo") in (None, "rodillos") for c in CASOS)
    assert sum(len(c["reglas"]) for c in CASOS) == 29
