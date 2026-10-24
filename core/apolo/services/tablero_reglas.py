"""Las reglas del ERC que salen del ruteo de un tablero armado (plan V8.5 D3, D10, A10; F2).

Sólo con un `layout_tablero` vivo (sin él, el ERC de siempre):
- «llenado de canaleta»: la suma de las secciones exteriores pasa el tope de su sección útil
  (`Criterio.llenado_tope`, 50 %: criterio de diseño): aviso; más del 100 % no entra: error;
- «sale del tablero sin cable» (A10): un conductor SUELTO con un extremo fuera de la ubicación
  (el ruteo lo lleva hasta el prensaestopas; afuera tiene que ir dentro de un cable);
- «largo declarado vs ruteado»: el `largo_m` escrito a mano manda en la BOM (D3), y si difiere
  del ruteado más que `Criterio.difiere_largo` se avisa con las dos cifras (la F0 mostró que los
  declarados no se sostienen). La fila es `fila_largo_declarado`: la usan también los cables de
  campo (F4, `cables_campo.py`).
Cada regla tiene su SELECTOR (`llenas`, `salen_sin_cable`, `declarados_que_no_cuadran`): el
ERC de aquí y el panel del visor (`tablero_panel.py`, F3b) leen lo mismo (D15). El llamador
sostiene STATE_LOCK.
"""

from __future__ import annotations

import json

NORMA = "criterio de diseño"


def _pct(x: float) -> str:
    return f"{x * 100:.0f} %"


# ── lo que encuentra cada regla (lo leen el ERC de abajo y el panel, `tablero_panel.py`) ──


def llenas(t) -> list:
    """Los `Llenado` de las canaletas que pasan el tope (una fracción > 1 no entra)."""
    tope = t.ruteo.criterio["llenado_tope"]
    return [ll for ll in t.ruteo.llenados if ll.fraccion > tope]


def salen_sin_cable(t) -> list:
    """Las `Ruta` de los conductores sueltos con un extremo fuera de la ubicación (A10)."""
    return [r for r in t.ruteo.rutas if r.sale and r.cable is None]


def declarados_que_no_cuadran(t) -> list[tuple]:
    """[(Ruta, diferencia relativa)] de los `largo_m` a mano que difieren del ruteado más que
    `Criterio.difiere_largo`."""
    limite = t.ruteo.criterio["difiere_largo"]
    out = []
    for r in t.ruteo.rutas:
        if r.declarado_mm is None or r.sale or r.cable is not None or r.largo_mm <= 0:
            continue
        dif = (r.declarado_mm - r.largo_mm) / r.largo_mm
        if abs(dif) > limite:
            out.append((r, dif))
    return out


# ── las filas del ERC ─────────────────────────────────────────────────────────────────────


def _llenado(t) -> list[dict]:
    tope = t.ruteo.criterio["llenado_tope"]
    filas = []
    for ll in llenas(t):
        f = ll.fraccion
        pieza = t.canaletas.get(ll.canaleta) or f"canaleta {ll.canaleta + 1}"
        eje = "u" if ll.orientacion == "h" else "v"
        a, b = ll.pasa or (ll.desde, ll.hasta)
        error = f > 1.0
        filas.append({
            "regla": "llenado de canaleta", "estado": "error" if error else "aviso",
            "detalle": (f"{pieza} ({t.canaleta_ref}, {t.ubicacion}) va al {_pct(f)} de su sección útil "
                        f"({ll.ocupado_mm2:.0f} de {ll.util_mm2:.0f} mm², {len(ll.conductores)} "
                        f"conductores) entre {eje} = {a:.0f} y {b:.0f} mm de la placa; tope "
                        f"{_pct(tope)}" + (": no entran" if error else "")),
            "recomendacion": "Reparte los conductores por otra canaleta (overrides de la colocación) o "
                             "usa un gabinete mayor; la canaleta llena no deja agregar ni cambiar "
                             "cables y calienta.",
            "norma": NORMA, "elementos": [pieza, *ll.conductores[:6]]})
    return filas


def _sale(t) -> list[dict]:
    filas = []
    for r in salen_sin_cable(t):
        filas.append({
            "regla": "sale del tablero sin cable", "estado": "aviso",
            "detalle": (f"{r.id} ({' → '.join(r.puntos)}) sale de {t.ubicacion} como conductor suelto: "
                        "dentro del tablero llega al prensaestopas, pero afuera un conductor suelto "
                        "no está protegido. Decláralo como hilo de un cable: add_cable (ref, desde, "
                        f"hasta) y edit_command('{r.id}', {{\"cable\": \"-W…\", \"hilo\": \"1\"}})"),
            "recomendacion": "Lo que sale del gabinete va dentro de un cable con su prensaestopas "
                             "(add_cable), no como conductores sueltos.",
            "norma": NORMA, "elementos": [r.id]})
    return filas


def fila_largo_declarado(cid: str, que: str, declarado_mm: float, calculado_mm: float, donde: str,
                         limite: float) -> dict | None:
    """La fila «largo declarado vs ruteado» (aviso si difieren más que `limite`), o None. La usan
    los conductores del tablero (`donde` = «por las canaletas de +TAB1») y los cables de campo
    (V8.5 F4, `cables_campo.py`)."""
    if calculado_mm <= 0:
        return None
    dif = (declarado_mm - calculado_mm) / calculado_mm
    if abs(dif) <= limite:
        return None
    return {
        "regla": "largo declarado vs ruteado", "estado": "aviso",
        "detalle": (f"{cid} ({que}): declarado {declarado_mm / 1000:.2f} m, "
                    f"ruteado {donde} {calculado_mm / 1000:.2f} m "
                    f"({dif * 100:+.0f} %); la BOM compra el declarado. Si no lo mediste, "
                    f"quítalo y compra el ruteado: edit_command('{cid}', "
                    f"{json.dumps({'largo_m': None})})"),
        "recomendacion": "Deja que el largo salga del ruteo (dentro de un tablero armado o por el "
                         "recorrido `por` de un cable); declara `largo_m` sólo si lo mediste.",
        "norma": NORMA, "elementos": [cid]}


def _declarados(t) -> list[dict]:
    filas = []
    limite = t.ruteo.criterio["difiere_largo"]
    for r, _dif in declarados_que_no_cuadran(t):
        fila = fila_largo_declarado(r.id, " → ".join(r.puntos), r.declarado_mm, r.largo_mm,
                                    f"por las canaletas de {t.ubicacion}", limite)
        if fila is not None:
            filas.append(fila)
    return filas


def reglas(doc, m=None) -> list[dict]:
    """Las filas del ERC del ruteo (vacía sin tablero armado)."""
    from apolo.commands.errors import CommandError

    from .tablero import ruteos

    try:
        tableros = ruteos(doc, m)
    except (CommandError, ValueError) as exc:  # el layout regeneró: esto no debería pasar
        return [{"regla": "ruteo del tablero", "estado": "aviso",
                 "detalle": f"no se pudo rutear el tablero: {exc}", "norma": NORMA, "elementos": []}]
    filas: list[dict] = []
    for t in tableros:
        filas += _llenado(t) + _sale(t) + _declarados(t)
    return filas
