"""Las reglas del ERC que salen del ruteo de un tablero armado (plan V8.5 D3, D10, A10; F2).

Sólo con un `layout_tablero` vivo (sin él, el ERC de siempre):
- «llenado de canaleta»: la suma de las secciones exteriores pasa el tope de su sección útil
  (`Criterio.llenado_tope`, 50 %: criterio de diseño): aviso; más del 100 % no entra: error;
- «sale del tablero sin cable» (A10): un conductor SUELTO con un extremo fuera de la ubicación
  (el ruteo lo lleva hasta el prensaestopas; afuera tiene que ir dentro de un cable);
- «largo declarado vs ruteado»: el `largo_m` escrito a mano manda en la BOM (D3), y si difiere
  del ruteado más que `Criterio.difiere_largo` se avisa con las dos cifras (la F0 mostró que los
  declarados no se sostienen). La fila es `fila_largo_declarado`: la usan también los cables de
  campo (F4, `cables_campo.py`) y, con la misma regla, un cable SIN `por` cuyo `largo_m` no
  alcanza lo de dentro del tablero + sus tramos 3D + la reserva (`cables_cortos`, F5b: la -W4 de
  la faja 77 declaraba 1,5 m y necesitaba 1,88).
Cada regla tiene su SELECTOR (`llenas`, `salen_sin_cable`, `declarados_que_no_cuadran`): el
ERC de aquí y el panel del visor (`tablero_panel.py`, F3b) leen lo mismo (D15). El llamador
sostiene STATE_LOCK.

F3 (D6, D7, D10) suma, con un tablero armado: «calentamiento del tablero» (`tablero_calor.reglas`:
error si el aire pasa la máxima de un aparato, aviso si el método no lo cubre), «prensaestopas»
(`tablero_prensas.reglas`: aviso si un cable que sale no entra en ninguno o no entran en la placa)
y «aparato fuera del tablero armado» (`sin_tablero`: un aparato de montaje din, placa o puerta cuya
ubicación no tiene layout).
"""

from __future__ import annotations

import json
import math

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
                         limite: float, consejo: str | None = None) -> dict | None:
    """La fila «largo declarado vs ruteado» (aviso si difieren más que `limite`), o None. La usan
    los conductores del tablero (`donde` = «por las canaletas de +TAB1»), los cables de campo
    (V8.5 F4, `cables_campo.py`) y los cables sin `por` que se quedan cortos (F5b, con su
    `consejo`: sin recorrido no hay largo calculado que comprar)."""
    if calculado_mm <= 0:
        return None
    dif = (declarado_mm - calculado_mm) / calculado_mm
    if abs(dif) <= limite:
        return None
    consejo = consejo or (f"Si no lo mediste, quítalo y compra el ruteado: edit_command('{cid}', "
                          f"{json.dumps({'largo_m': None})})")
    return {
        "regla": "largo declarado vs ruteado", "estado": "aviso",
        "detalle": (f"{cid} ({que}): declarado {declarado_mm / 1000:.2f} m, "
                    f"ruteado {donde} {calculado_mm / 1000:.2f} m "
                    f"({dif * 100:+.0f} %); la BOM compra el declarado. {consejo}"),
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


def cables_cortos(doc, m, tableros) -> list[tuple]:
    """[(Cable, mínimo en mm, partes)] de los cables SIN `por` con `largo_m` declarado y hilos
    ruteados dentro de un tablero armado cuyo declarado no alcanza lo que se puede medir (F5b):
    lo de dentro (su hilo más largo, por tablero), el recorrido de cada tramo 3D ligado con
    `piezas` (`piezas_electricas.recorrido_mm`, volumen / sección: el de la BOM) y la reserva de cada
    aparato de campo ligado a su pieza (`CriterioCampo.reserva_campo_mm`, la de F4). `partes` =
    [(texto, mm)] para la fila."""
    from apolo.library.electrico.cable_campo import CriterioCampo
    from apolo.library.piezas_electricas import recorrido_mm

    from .cables_campo import _extremo

    crit = CriterioCampo()
    tabs = {t.ubicacion: t for t in tableros}
    out = []
    for c in m.cables:
        if c.por or c.largo_m is None or not c.designacion:
            continue
        partes = []
        for t in tableros:
            hilos = [r.largo_mm for r in t.ruteo.rutas if r.cable == c.designacion and r.sale]
            if hilos:
                partes.append((f"dentro de {t.ubicacion}", max(hilos)))
        if not partes:
            continue
        for fid in c.piezas:
            f = doc.scene.get(fid)
            largo = recorrido_mm(f.shape) if f is not None and f.shape is not None else None
            if largo:
                partes.append((f"el tramo 3D {fid}", largo))
        for texto in (c.desde, c.hasta):
            e = _extremo(doc, m, tabs, texto)
            if e[0] == "aparato":
                partes.append((f"la reserva en {e[2]}", crit.reserva_campo_mm))
        minimo = sum(mm for _, mm in partes)
        if c.largo_m * 1000.0 < minimo - 1e-6:
            out.append((c, minimo, partes))
    return out


def _cortos(doc, m, tableros) -> list[dict]:
    filas = []
    for c, minimo, partes in cables_cortos(doc, m, tableros):
        donde = "como mínimo, con " + " + ".join(f"{t} {mm / 1000:.2f} m" for t, mm in partes) + ","
        consejo = (f"Sin recorrido (por) no hay largo calculado: mídelo y corrígelo, edit_command('{c.id}', "
                   f"{json.dumps({'largo_m': math.ceil(minimo / 100.0) / 10})}) es lo mínimo redondeado, "
                   "o dale su recorrido por la estructura (add_cable.por) para que el largo salga solo")
        fila = fila_largo_declarado(c.id or c.designacion, c.designacion, c.largo_m * 1000.0, minimo, donde,
                                    0.0, consejo)
        if fila is not None:
            filas.append(fila)
    return filas


def reglas(doc, m=None) -> list[dict]:
    """Las filas del ERC del ruteo (vacía sin tablero armado)."""
    from apolo.commands.errors import CommandError

    from .electrico import modelo
    from .tablero import ruteos

    m = m if m is not None else modelo(doc)
    try:
        tableros = ruteos(doc, m)
    except (CommandError, ValueError) as exc:  # el layout regeneró: esto no debería pasar
        return [{"regla": "ruteo del tablero", "estado": "aviso",
                 "detalle": f"no se pudo rutear el tablero: {exc}", "norma": NORMA, "elementos": []}]
    filas: list[dict] = []
    for t in tableros:
        filas += _llenado(t) + _sale(t) + _declarados(t)
    if not tableros:
        return filas
    from . import tablero_calor, tablero_prensas

    prensas = {t.cid: tablero_prensas.del_tablero(doc, m, t) for t in tableros}
    return (filas + _cortos(doc, m, tableros) + tablero_calor.reglas(doc, m, tableros)
            + tablero_prensas.reglas(tableros, prensas) + _sin_tablero(m, tableros))


#: los montajes de lo que va DENTRO de un tablero (`ficha_datos.TABLERO`)
_DE_TABLERO = ("din", "placa", "puerta")


def sin_tablero(m, tableros) -> list:
    """Los dispositivos que van dentro de un tablero (montaje din, placa o puerta) cuya ubicación no
    tiene un layout vivo, en un documento que sí arma alguno (D10): no se dibujan, no calientan
    ningún tablero ni entran a su ruteo."""
    from apolo.library.catalog import CATALOG

    armadas = {t.ubicacion for t in tableros}
    out = []
    for d in m.dispositivos:
        comp = CATALOG.get(d.ref)
        e = comp.electrico if comp is not None else None
        if e is None or e.montaje not in _DE_TABLERO or e.simbolo == "gabinete" or d.ubicacion in armadas:
            continue
        out.append(d)
    return out


def _sin_tablero(m, tableros) -> list[dict]:
    import json

    validas = ", ".join(sorted({t.ubicacion for t in tableros}))
    return [{"regla": "aparato fuera del tablero armado", "estado": "aviso",
             "detalle": (f"{d.designacion} ({d.ref}) va dentro de un tablero y "
                         + (f"su ubicación {d.ubicacion} no tiene layout_tablero" if d.ubicacion else
                            "no tiene ubicación")
                         + f": no se dibuja ni cuenta en el ruteo ni en el calentamiento de {validas}. "
                         f"Si va en uno de ellos: edit_command('{d.id}', "
                         f"{json.dumps({'ubicacion': sorted({t.ubicacion for t in tableros})[0]})})"),
             "recomendacion": "Cada aparato de tablero lleva la ubicación del tablero donde va (IEC 81346 «+»).",
             "norma": NORMA, "elementos": [d.designacion]} for d in sin_tablero(m, tableros)]
