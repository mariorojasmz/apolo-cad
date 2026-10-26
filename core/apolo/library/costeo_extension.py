"""Filas del costeo que suma una extensión (`Extension.costeo`; plan
puntos-de-extension-entregables, D2). Puro: guarda lo declarado y valida las filas; quien llama a
`FuenteCosteo.filas(doc)` es `services/cobros.py`, bajo el lock del llamador.

Una fila de extensión llega YA COSTEADA (la extensión sabe su precio y la `fuente` lo declara):
`costing.costed_bom` no la re-costea y `costing_totals` la suma a `extensiones_usd`, ni comprada
ni fabricada. Sin extensiones con costeo, `DE_EXTENSION` está vacío y nada cambia.

Una fuente puede traer una `nota` (plan pedidos-de-extensiones, D9): UNA línea de ≤ `NOTA_MAX`
caracteres que aclara lo que cobra; se valida al cargar (`motivo_nota`) y sale en la cotización
sólo si la fuente cobró al menos una fila, DESPUÉS de las notas del núcleo (que no se quitan).
Cambiar la nota es cambiar el costeo: la extensión sube su `version_costeo`.

Plan cotizacion-identificada-y-ajustes-por-escenario (F1):

- D3: una fuente con `acota` («nucleo.alcance» o «nucleo.validez», `ACOTABLES`) pone su `nota` EN
  LUGAR de esa nota del núcleo (si cobró). Las de honestidad (`HONESTIDAD`) no se acotan nunca:
  la carga rechaza la extensión. Una nota del núcleo tiene un solo dueño: dos fuentes que acotan
  la misma (de una extensión o de dos) → la segunda no carga.
- D4: `incluye` (de `ALCANCES`) declara qué cubren sus filas; si cobró, el alcance del núcleo deja
  de excluirlo (`costeo["incluye"]`), aunque nadie lo acote.
- D2: `IdentificacionCosteo` aporta la identificación comercial de la cotización cuando el
  proyecto no la trae (`services/identificacion.py`). Su `rotulo` (opcional, una línea de
  ≤ `ROTULO_MAX`, `motivo_rotulo`) es lo que dice el pie de la hoja («identificación: <rótulo>»);
  sin él, el id. El del proyecto es `ROTULO_PROYECTO`.
- Cotización sin internos: el `rotulo` de una `FuenteCosteo` (mismo tope y validación) es lo que
  dice la columna «Ref» de sus filas en la cotización (la fila lo lleva en `rotulo`, sólo si hay);
  sin él, el id, como antes. El `ref` de la fila sigue siendo el id (con él se cuenta quién cobró).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

#: `origen` de una fila de extensión: «extension:<nombre>».
ORIGEN = "extension:"
#: Las claves de una fila (más `categoria`, opcional); ninguna otra.
CAMPOS = ("descripcion", "cantidad", "unidad", "costo_unit", "fuente")
CATEGORIA = "servicios"  # la de una fila que no declara la suya
NOTA_MAX = 300  # caracteres de la nota de una fuente
ROTULO_MAX = 60  # caracteres del rótulo de una identificación (el pie de la cotización)
#: El rótulo del pie cuando la identificación es la del proyecto (`doc.comercial`).
ROTULO_PROYECTO = "datos comerciales del proyecto"
#: Las notas del núcleo de la cotización, por id, en su orden (`drawing/quote._notas_nucleo`).
NOTAS_NUCLEO = ("nucleo.avisos", "nucleo.referenciales", "nucleo.cambio", "nucleo.detalle",
                "nucleo.alcance", "nucleo.validez")
#: Las que una fuente puede reemplazar (D3); las demás son de HONESTIDAD.
ACOTABLES = ("nucleo.alcance", "nucleo.validez")
HONESTIDAD = tuple(n for n in NOTAS_NUCLEO if n not in ACOTABLES)
#: Lo que una fuente puede declarar que cubren sus filas (D4). «pruebas» (de marcha) basta para
#: que el alcance deje de excluir la puesta en marcha.
ALCANCES = ("transporte", "instalacion", "puesta_en_marcha", "pruebas")


@dataclass(frozen=True)
class FuenteCosteo:
    """Una fuente de filas del costeo: `id` «prefijo.x» (la ref de sus filas), `filas(doc)` →
    iterable de `{descripcion, cantidad, unidad, costo_unit, fuente[, categoria]}` y, opcional,
    `nota`: una línea para las notas de la cotización (sale sólo si la fuente cobró); `acota`: el
    id de la nota del núcleo que esa `nota` reemplaza (`ACOTABLES`); `incluye`: lo que cubren sus
    filas (`ALCANCES`); `rotulo`: lo que dice la columna «Ref» de sus filas en la cotización
    (sin él, el `id`)."""

    id: str
    filas: Callable
    nota: str | None = None
    acota: str | None = None
    incluye: tuple = ()
    rotulo: str | None = None


@dataclass(frozen=True)
class IdentificacionCosteo:
    """La identificación comercial que aporta una extensión (D2): `id` «prefijo.x»,
    `de_documento(doc)` → `{titulo, cliente, numero, revision}` (todos opcionales;
    `library/comercial.normalizar`) o `None` si no tiene para ese documento y, opcional, `rotulo`:
    el texto corto y legible que dice el pie de la cotización («ficha del encargo»; sin él, el
    `id`). Gana la del proyecto; luego la primera extensión que devuelva algo."""

    id: str
    de_documento: Callable
    rotulo: str | None = None


#: nombre de la extensión → (version_costeo, (FuenteCosteo, …)); lo llena `extensiones.cargar`.
DE_EXTENSION: dict[str, tuple[int, tuple[FuenteCosteo, ...]]] = {}


def vigentes() -> list[tuple[str, FuenteCosteo]]:
    """(nombre de la extensión, fuente) de cada fuente de filas cargada, en el orden de carga."""
    return [(nombre, f) for nombre, (_v, fuentes) in DE_EXTENSION.items() for f in fuentes
            if isinstance(f, FuenteCosteo)]


def identificaciones() -> list[tuple[str, IdentificacionCosteo]]:
    """(nombre de la extensión, identificación) de cada `IdentificacionCosteo` cargada, en orden."""
    return [(nombre, f) for nombre, (_v, fuentes) in DE_EXTENSION.items() for f in fuentes
            if isinstance(f, IdentificacionCosteo)]


def versiones() -> dict[str, int]:
    """{nombre: version_costeo} de las extensiones con costeo (lo publica el dict del costeo)."""
    return {nombre: v for nombre, (v, _f) in DE_EXTENSION.items()}


def _numero(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _texto(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def fila(nombre: str, fuente: FuenteCosteo, d) -> dict:
    """La fila costeada de `d`, o `ValueError` con el motivo (la fila no se cobra)."""
    if not isinstance(d, dict):
        raise ValueError(f"una fila no es un dict: {d!r}"[:200])
    faltan = [k for k in CAMPOS if k not in d]
    sobran = sorted(set(d) - set(CAMPOS) - {"categoria"})
    if faltan or sobran:
        raise ValueError("una fila es {descripcion, cantidad, unidad, costo_unit, fuente"
                         "[, categoria]}" + (f"; faltan {', '.join(faltan)}" if faltan else "")
                         + (f"; sobran {', '.join(sobran)}" if sobran else ""))
    for k in ("descripcion", "unidad", "fuente"):
        if not _texto(d[k]):
            raise ValueError(f"`{k}` es un texto no vacío, no {d[k]!r}")
    if "categoria" in d and not _texto(d["categoria"]):
        raise ValueError(f"`categoria` es un texto no vacío, no {d['categoria']!r}")
    if not _numero(d["cantidad"]) or d["cantidad"] <= 0:
        raise ValueError(f"`cantidad` es un número finito > 0, no {d['cantidad']!r}")
    if not _numero(d["costo_unit"]) or d["costo_unit"] < 0:
        raise ValueError(f"`costo_unit` es un número finito ≥ 0 (USD), no {d['costo_unit']!r}")
    cantidad, costo = float(d["cantidad"]), float(d["costo_unit"])
    return {
        "ref": fuente.id, "descripcion": d["descripcion"].strip(),
        "categoria": (d.get("categoria") or CATEGORIA).strip(), "material": "", "norma": "",
        "cantidad": int(cantidad) if cantidad.is_integer() else cantidad,
        "unidad": d["unidad"].strip(), "longitud_mm": None, "peso_unitario_kg": None,
        "peso_total_kg": None, "origen": ORIGEN + nombre,
        "costo_ud_usd": round(costo, 2), "costo_total_usd": round(costo * cantidad, 2),
        "costo_fuente": d["fuente"].strip(),
        **({"rotulo": fuente.rotulo.strip()} if fuente.rotulo else {}),
    }


def es_de_extension(row: dict) -> bool:
    return str(row.get("origen") or "").startswith(ORIGEN)


def motivo_nota(nota) -> str | None:
    """Por qué la `nota` de una fuente no vale (la extensión no carga), o `None` si vale (o no
    hay): un texto no vacío, de UNA línea y de ≤ `NOTA_MAX` caracteres."""
    if nota is None:
        return None
    if not _texto(nota):
        return f"`nota` es un texto no vacío, no {nota!r}"[:200]
    if nota.splitlines() != [nota]:
        return "`nota` es de una sola línea (sin saltos)"
    if len(nota) > NOTA_MAX:
        return f"`nota` tiene {len(nota)} caracteres (máximo {NOTA_MAX})"
    return None


def motivo_rotulo(rotulo) -> str | None:
    """Por qué el `rotulo` de una identificación o de una fuente no vale (la extensión no carga),
    o `None` si vale (o no hay): un texto no vacío, de UNA línea y de ≤ `ROTULO_MAX` caracteres."""
    if rotulo is None:
        return None
    if not _texto(rotulo):
        return f"`rotulo` es un texto no vacío, no {rotulo!r}"[:200]
    if rotulo.splitlines() != [rotulo]:
        return "`rotulo` es de una sola línea (sin saltos)"
    if len(rotulo) > ROTULO_MAX:
        return f"`rotulo` tiene {len(rotulo)} caracteres (máximo {ROTULO_MAX})"
    return None


def rotulo_de(ident: IdentificacionCosteo) -> str:
    """Lo que dice el pie de la cotización de esta identificación: su `rotulo` o, sin él, su id."""
    return ident.rotulo.strip() if ident.rotulo else ident.id


def motivo_acota(acota, nota) -> str | None:
    """Por qué el `acota` de una fuente no vale (D3), o `None`: una de `ACOTABLES` y con `nota`
    (el texto que la reemplaza). Acotar una de honestidad se rechaza con el motivo."""
    if acota is None:
        return None
    if acota in HONESTIDAD:
        return (f"`acota` «{acota}»: es una nota de honestidad del núcleo y no se acota nunca "
                f"(sólo {' y '.join(ACOTABLES)})")
    if acota not in ACOTABLES:
        return f"`acota` {acota!r} no es una nota acotable del núcleo ({' o '.join(ACOTABLES)})"[:200]
    if nota is None:
        return f"`acota` «{acota}» sin `nota`: la nota es el texto que la reemplaza"
    return None


def motivo_incluye(incluye) -> str | None:
    """Por qué el `incluye` de una fuente no vale (D4), o `None`: una tupla o lista de `ALCANCES`."""
    if not isinstance(incluye, (tuple, list)):
        return f"`incluye` es una tupla de {', '.join(ALCANCES)}, no {incluye!r}"[:200]
    malos = [x for x in incluye if x not in ALCANCES]
    if malos:
        return (f"`incluye` nombra {', '.join(map(repr, malos))}: cada uno es de "
                f"{', '.join(ALCANCES)}")[:200]
    return None


def _cobraron(filas: list[dict]) -> list[FuenteCosteo]:
    hay = {(r["ref"], r["origen"]) for r in filas}
    return [f for nombre, f in vigentes() if (f.id, ORIGEN + nombre) in hay]


def notas(filas: list[dict]) -> list[dict]:
    """`[{texto, fuente, origen[, acota]}]` de las fuentes con nota que cobraron al menos una de
    `filas` (las ya costeadas), en el orden de carga; `acota` = la nota del núcleo que reemplaza."""
    cobraron = {(r["ref"], r["origen"]) for r in filas}
    return [{"texto": f.nota.strip(), "fuente": f.id, "origen": ORIGEN + nombre,
             **({"acota": f.acota} if f.acota else {})}
            for nombre, f in vigentes() if f.nota and (f.id, ORIGEN + nombre) in cobraron]


def incluye(filas: list[dict]) -> list[str]:
    """Lo que cubren las fuentes que cobraron al menos una de `filas` (D4), ordenado."""
    return sorted({x for f in _cobraron(filas) for x in f.incluye})
