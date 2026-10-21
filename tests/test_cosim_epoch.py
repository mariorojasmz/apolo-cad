"""La versión del motor de la co-simulación no se olvida (plan V8.3 F6b, defecto 1).

La vigencia de un resultado de escenario es firma del documento + hash del escenario +
`COSIM_EPOCH` (`apolo/cosim/__init__.py`). Si el código que produce o evalúa el resultado cambia
y la versión no sube, la puerta de entrega sigue en VERDE con resultados que el código nuevo
ya no daría (lo midió la re-verificación F6b: 3 de 4 escenarios «vigentes» fallaban).

Trinquete al estilo de `tests/test_contrato_comandos.py`: `HUELLA` guarda `(versión, huella del
código)`. Si la huella cambió y la versión no, falla y obliga a decidir:
  - el cambio puede cambiar el resultado o el veredicto de un escenario con el MISMO documento →
    sube `COSIM_EPOCH` (todos los resultados guardados quedan «vencidos»);
  - fue un refactor sin efecto → actualiza sólo la huella.
`python tests/test_cosim_epoch.py` imprime el literal para pegar.

La huella cubre el código del motor (`ARCHIVOS`); el catálogo eléctrico NO va aquí: sus fichas
entran a la firma del documento (`services/escenarios._fichas_electricas`), así un YAML vence
sólo los documentos que usan esa ref.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from apolo.cosim import COSIM_EPOCH

RAIZ = Path(__file__).resolve().parents[1] / "core" / "apolo"

#: Lo que decide el resultado de una co-simulación dado el documento y el escenario.
ARCHIVOS = (
    "cosim/**/*.py",
    "plc/**/*.py",
    "physics/banda.py",
    "physics/dinamica.py",
    "physics/dinamica_arrastre.py",
    "physics/dinamica_control.py",
    "physics/dinamica_cuerpos.py",
    "physics/dinamica_datos.py",
    "physics/dinamica_integrador.py",
    "physics/dinamica_modelo.py",
    "physics/dinamica_motores.py",
    "physics/dinamica_peticion.py",
    "physics/hull.py",
    "physics/sensores.py",
    "physics/sim.py",
    "services/cosim_bandas.py",
    "services/cosim_red.py",
    "services/cosim_snapshot.py",
)

HUELLA: tuple[int, str] = (2, "f4bbe35aee467fed")


def archivos() -> list[Path]:
    out = set()
    for patron in ARCHIVOS:
        hallados = list(RAIZ.glob(patron))
        assert hallados, f"el patrón {patron} no encuentra archivos: actualiza ARCHIVOS"
        out.update(hallados)
    return sorted(out)


def huella() -> str:
    """sha1 del código, sin depender de los finales de línea del checkout ni de la línea que
    declara la versión (subirla no es cambiar el motor)."""
    h = hashlib.sha1()
    for p in archivos():
        texto = p.read_text(encoding="utf-8").replace("\r\n", "\n")
        texto = "\n".join(ln for ln in texto.split("\n") if not ln.startswith("COSIM_EPOCH ="))
        h.update(p.relative_to(RAIZ).as_posix().encode())
        h.update(texto.encode("utf-8"))
    return h.hexdigest()[:16]


def problemas(declarada: tuple[int, str], version: int, actual: str) -> list[str]:
    v0, h0 = declarada
    if version < v0:
        return [f"COSIM_EPOCH BAJÓ de {v0} a {version}: nunca baja (un resultado viejo volvería a "
                "parecer vigente)"]
    if version > v0:
        return [f'subiste COSIM_EPOCH a {version}: declara HUELLA = ({version}, "{actual}")']
    if actual != h0:
        return [f"el código del motor de la co-simulación cambió y COSIM_EPOCH no (sigue en {v0})"]
    return []


def test_el_motor_no_cambia_sin_decidir_su_version():
    p = problemas(HUELLA, COSIM_EPOCH, huella())
    assert not p, (
        "Versión del motor de la co-simulación (V8.3 F6b):\n  " + "\n  ".join(p) + "\n"
        "Si el cambio puede cambiar el resultado o el veredicto de un escenario con el MISMO "
        "documento, sube COSIM_EPOCH (apolo/cosim/__init__.py): los resultados guardados quedan "
        "«vencidos». Si fue un refactor sin efecto, actualiza sólo la huella. Después pega el "
        "literal que imprime `python tests/test_cosim_epoch.py` (regla: core/apolo/cosim/CLAUDE.md)."
    )


def test_el_trinquete_distingue_los_tres_casos():
    assert problemas((2, "a"), 2, "a") == []
    assert "cambió" in problemas((2, "a"), 2, "b")[0]
    assert "subiste" in problemas((2, "a"), 3, "b")[0]
    assert "BAJÓ" in problemas((2, "a"), 1, "a")[0]


if __name__ == "__main__":
    print(f'HUELLA: tuple[int, str] = ({COSIM_EPOCH}, "{huella()}")')
