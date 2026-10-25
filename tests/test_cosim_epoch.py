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
    "physics/dinamica_nacimiento.py",
    "physics/dinamica_peticion.py",
    "physics/hull.py",
    "physics/sensores.py",
    "physics/sim.py",
    "services/cosim_aire.py",
    "services/cosim_bandas.py",
    "services/cosim_red.py",
    "services/cosim_snapshot.py",
)

#: V8.4 F1 (sin subir): el paso compartido lote/vivo da la MISMA huella de trazas (la 77 en sus
#: tres casos de F0 y `tests/test_cosim_vivo.py` contra el bucle de V8.3); `sumideros` sólo deja
#: correr escenarios que antes eran 400 y el color/pieza del snapshot no entran al resultado.
#: V8.4 F4 (sin subir): `services/escenarios.py` sólo saca `validar_nombre` y `no_existe` a
#: públicos (los usa `sesion_viva.py`); la vigencia y la lectura no cambian.
#: 4 — V8.4, cola en vivo: la caja de la cola nace sólo con su lugar de entrada libre
#: (`physics/dinamica_nacimiento.py`). Los 5 escenarios de la 77 dan la misma huella (su banda
#: anda antes de que toque la segunda caja), pero un escenario cuya cola encimaba cajas cambia.
#: nucleo-abierto F1a (sin subir): el snapshot lleva los modelos de EXTENSIÓN del tablero
#: (`modelos_extension`, `extensiones`) y el worker los registra; sin extensiones van vacíos y
#: ningún resultado cambia. Su vigencia (la versión de la extensión) va en `services/escenarios`.
#: cosim-fallas F1a (sin subir, D8): las fallas a propósito (`Modelo.FALLAS`, el evento `falla`,
#: la máscara de contactos pegados) sólo actúan con un evento `falla`; sin él las salidas son las
#: de antes: 9 escenarios del banco (marcha, seta, atasco, fase, cable, cajas, sensor pegado,
#: caída de red, atasco parcial) dan la MISMA huella antes y después (bitácora del plan).
#: mandos-de-seguridad F1 (sin subir, D5): modelos NUEVOS (`resguardo`, `rele_seguridad`), el
#: tablero lee los que declaran `BORNES_ENTRADA` y el vocabulario `pide` suma «salida»; sin esos
#: aparatos nada cambia: 11 escenarios del banco (los 9 de arriba, la seta por variador y el NC de
#: la seta pegado) dan la MISMA huella que en bf69175 (bitácora del plan).
#: mandos-de-seguridad F1b (sin subir): `vivo_fotograma.MANDOS` suma `resguardo`; sólo cambia lo
#: que la tabla del `inicio` ofrece en vivo, no el paso ni ninguna traza.
#: V8.5 F5b (sin subir, D8): la red toma el largo CALCULADO (ruteo del tablero armado, recorrido
#: `por`) de lo que no declara `largo_m`; con todo declarado, o sin tablero armado ni `por` (el
#: banco y la 77 original), la entrada de la red es idéntica. Lo que sí cambia (un documento con
#: largos calculados y un resultado de antes) lo vence la firma v1 (`services/escenarios`).
#: V8.9 F3 (sin subir, D14): la co-simulación del aire (`cosim/neumatica`, la electroválvula, el
#: acople del cilindro, los eventos del aire, `services/cosim_aire.py`) sólo actúa con un circuito
#: de aire; el tablero cambió cómo saca de la red una carga con falla (por bobina) y suma el índice
#: de las válvulas, sin efecto sin ellas: 9 escenarios del banco (marcha, seta, atasco parcial,
#: contactor soldado y no_cierra, piloto fundido, corte de fase, cajas con seta y sensor pegado)
#: dan la MISMA huella que en 06d44ac. Un documento con válvulas cambia de firma por su ficha
#: eléctrica (el `modelo` nuevo de la bobina): sus resultados de antes quedan vencidos solos.
#: datos-de-corte-y-acometida F1b (sin subir, D11): modelo NUEVO (`diferencial`, la residual por
#: fasores), indexado aparte en el tablero; las demás protecciones siguen recibiendo los mismos
#: módulos (`_corriente` = |`_fasor`|, bit a bit). Ningún documento existente usa el tipo: 10
#: escenarios del banco (marcha, seta, atasco parcial, contactor soldado y no_cierra, piloto
#: fundido, corte de fase, corto entre fases, cajas con seta y sensor pegado) dan la MISMA huella
#: que en 194e119 (bitácora del plan).
#: 5 — datos-de-corte-y-acometida F1c (D7, D11): el esquema de tierra se lee del AJUSTE de la red
#: (antes se ignoraba) y la red entiende TN-S, TN-C-S, TT (con `RA_ohm`: el PE unido a tierra por
#: 1/RA, `FuenteRed.R_tierra_ohm`) e IT; con `Icc_kA` ajustado la hipótesis ya no dice «SUPUESTA».
#: Un documento con esos ajustes cambia de resultado con el MISMO log. Sin esquema la entrada de la
#: red es idéntica: 5 escenarios del banco (marcha, seta, caída de red, corto entre fases y el
#: variador) dan la MISMA huella que en 1f01d0a (bitácora del plan).
#: V8.9 F6 (sin subir): `vivo_fotograma.tabla` suma `valvulas` (las electroválvulas y su
#: accionamiento manual, sólo si hay); sólo cambia lo que el `inicio` ofrece en vivo, no el paso
#: ni ninguna traza (como la F1b de mandos-de-seguridad).
#: ni ninguna traza (como la F1b de mandos-de-seguridad). La electroválvula con manual publica
#: `manual` (el lado enclavado, texto): sólo existe con válvulas; un escenario sin aire no cambia.
HUELLA: tuple[int, str] = (5, "RECALCULAR")


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
