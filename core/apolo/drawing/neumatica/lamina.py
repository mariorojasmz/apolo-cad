"""La lámina del esquema neumático ISO 1219 (plan V8.9 F5, D11): marco, título, el esquema
compuesto por reglas, notas y cajetín, en un `SheetModel` (SVG, PDF, DXF y DWG con los
exportadores del núcleo).

El formato crece solo (A3 → A2 → A1 → A0) si las columnas no caben en el pedido; más de lo que
entra en un A0 es error con el porqué.
"""

from __future__ import annotations

from ..dimensions import notes_block
from ..sheet import MARGIN, SHEETS, Label, SheetModel
from ..titleblock import draw_title_block
from .circuito import CircuitoAire, planear
from .composicion import ancho_necesario, dibujar

FORMATOS = ("A4", "A3", "A2", "A1", "A0")
NOTAS = (
    "Posición de reposo: sin energía ni aire (ISO 1219-2).",
    "Designación IEC 81346-2; vías de válvula ISO 5599-3.",
    "Bobinas y detectores: referidos a su borne del tablero.",
)
SUFIJO = " · ESQUEMA ISO 1219"  # el cajetín mide el título y lo parte: sale entero


def _formato(pedido: str, ancho: float) -> str:
    inicio = FORMATOS.index(pedido) if pedido in FORMATOS else FORMATOS.index("A3")
    inicio = max(inicio, FORMATOS.index("A3"))  # el esquema necesita el alto de un A3
    for f in FORMATOS[inicio:]:
        if SHEETS[f][0] - MARGIN >= ancho:
            return f
    raise ValueError(f"el esquema neumático necesita {ancho:.0f} mm de ancho y no cabe ni en un A0: "
                     "divide el circuito en sub-proyectos (insert_project) o pide la lámina por partes")


def lamina_neumatica(c: CircuitoAire, *, proyecto: str = "Sin título", hoja: str = "A3",
                     meta: dict | None = None, notas: tuple | list = ()) -> SheetModel:
    """La lámina ISO 1219 del circuito `c`. `notas`: las que agrega quien la pide (supuestos)."""
    plan = planear(c)
    formato = _formato(hoja, ancho_necesario(plan))
    W, H = SHEETS[formato]
    m = SheetModel(W, H)
    m.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN, "frame")
    m.labels.append(Label(MARGIN + 6, H - 22, "ESQUEMA NEUMÁTICO (ISO 1219)", 5.0, anchor="start"))
    r = dibujar(m, c, plan)
    todas = list(NOTAS) + [str(n) for n in notas] + [f"Revisar: {a}." for a in r.avisos]
    notes_block(m, W - MARGIN - 150.0, H - 22.0, todas, title="NOTAS", ancho=144.0)  # su franja
    base = dict(meta or {})
    base.setdefault("material", "—")
    draw_title_block(m, {**base, "project": f"{proyecto}{SUFIJO}", "scale": "s/e", "sheet": formato,
                         "units": "—", "tolerance": "—", "finish": "—"})
    m.meta["esquema_neumatico"] = {
        "formato": formato,
        "simbolos": {d: list(s.caja) for d, s in r.simbolos.items()},
        "avisos": list(r.avisos),
        "colgados": {s: des for s, (des, _via) in plan.silenciadores.items()},
        "columnas": [(col.cilindro or col.valvula or col.suelto).designacion for col in plan.columnas
                     if (col.cilindro or col.valvula or col.suelto) is not None],
        # lo que lee el panel «Neumática» del visor (V8.9 F6): los puertos y los tramos de cada línea
        # y la caja de cada posición de cada válvula (esquina inferior izquierda; S × H mm)
        "lineas": {f"P{i + 1}": {"puertos": list(miembros), "tramos": r.trazos.get(f"P{i + 1}", [])}
                   for i, miembros in enumerate(plan.lineas)},
        "fuente": list(r.fuente) if r.fuente else None,
        "toma": {"tramo": r.toma[0], "puerto": r.toma[1]} if r.toma else None,
        "posiciones": {d: {k.split(":", 1)[1]: list(v) for k, v in s.marcas.items() if k.startswith("caja:")}
                       for d, s in r.simbolos.items() if any(k.startswith("caja:") for k in s.marcas)},
    }
    return m
