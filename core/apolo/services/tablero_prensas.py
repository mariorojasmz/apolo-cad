"""Los prensaestopas de cada tablero armado (plan V8.5 D7, F3), leídos del documento. El llamador
sostiene `STATE_LOCK`.

Arma las `Salida` de `library/electrico/prensaestopas.py` (las reglas están ahí):
- un cable SALE de la ubicación si uno de sus extremos (`desde`/`hasta`) es la ubicación o un
  aparato de ella y el otro no, o si, sin extremos declarados, alguno de sus hilos ruteados sale;
  un cable con los dos extremos dentro es interno: no pide prensaestopas;
- su Ø = el `diameter` de su ref del catálogo;
- su lugar = el punto donde el ruteo saca sus hilos (el más votado, como `cables_campo._salida`);
  sin hilos ligados, el extremo de la primera canaleta vertical;
- la placa pasacables (`tablero.gabinete.pasacables`, ancho × fondo) se supone CENTRADA en su cara
  (el catálogo no da su posición: supuesto).
`del_tablero(doc, m, t)` → dict para el panel, el ERC (`reglas`) y la BOM (`cuenta`).
"""

from __future__ import annotations

from collections import Counter

NORMA = "EN 62444 (rango de sujeción de la ficha del fabricante)"


def _dentro(m, u: str, texto: str | None) -> bool | None:
    """True si el extremo es la ubicación `u` o un aparato de ella; None si no hay extremo."""
    t = (texto or "").strip()
    if not t:
        return None
    if t.startswith("+") and "-" not in t:
        return t == u
    if t.startswith(u + "-"):
        return True
    d = next((x for x in m.dispositivos if x.designacion == t), None)
    if d is None:
        cand = [x for x in m.dispositivos if x.designacion.endswith(t) and "=" not in x.designacion]
        d = cand[0] if len(cand) == 1 else None
    return d is not None and d.ubicacion == u


def que_salen(m, t) -> list:
    """Los `Cable` del modelo que salen de la ubicación de `t`."""
    out = []
    for c in m.cables:
        if not c.designacion:
            continue
        a, b = _dentro(m, t.ubicacion, c.desde), _dentro(m, t.ubicacion, c.hasta)
        if a is None and b is None:
            if any(r.cable == c.designacion and r.sale for r in t.ruteo.rutas):
                out.append(c)
        elif bool(a) != bool(b):
            out.append(c)
    return out


def _punto(t, designacion: str) -> tuple[float, float]:
    """(u, w) del ruteo donde salen los hilos del cable (o el extremo de la primera vertical)."""
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.colocacion import Reglas

    i = t.armado.interior
    abajo = CATALOG[t.layout.gabinete].tablero.gabinete.pasacables.cara == "inferior"
    puntos = [p for r in t.ruteo.rutas if r.cable == designacion and r.sale
              for s in r.segmentos for p in (s.recorrido[0], s.recorrido[-1])
              if (p[1] < -1e-6 if abajo else p[1] > i.placa_alto + 1e-6)]
    if puntos:
        (u, _v, w), _ = Counter(tuple(round(x, 3) for x in p) for p in puntos).most_common(1)[0]
        return u, w
    vert = [k for k in t.layout.canaletas if k.orientacion == "v"]
    u = (vert[0].u0 + vert[0].u1) / 2 if vert else i.placa_ancho / 2
    return u, Reglas().canaleta_alto_mm / 2


def opciones() -> list:
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.prensaestopas import Opcion

    out = []
    for ref, c in CATALOG.items():
        f = c.tablero.prensaestopas if c.tablero is not None else None
        if f is not None:
            out.append(Opcion(ref, f.rosca, f.min_mm, f.max_mm, f.llave_mm))
    return out


def del_tablero(doc, m, t) -> dict:
    """{prensas: [...], avisos, criterio, cara}: los prensaestopas de `t`, en el mundo."""
    from apolo.kernel.matrix import compose_place
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.armado import y_de_la_placa
    from apolo.library.electrico.prensaestopas import Placa, Salida, colocar

    i = t.armado.interior
    pc = CATALOG[t.layout.gabinete].tablero.gabinete.pasacables
    salidas = []
    for c in que_salen(m, t):
        comp = CATALOG.get(c.ref)
        d = float((comp.params or {}).get("diameter") or 0.0) if comp is not None else 0.0
        u, w = _punto(t, c.designacion)
        salidas.append(Salida(c.id or c.designacion, c.designacion, d or None,
                              u - i.placa_ancho / 2, y_de_la_placa(i) - w))
    res = colocar(salidas, opciones(), Placa(-pc.ancho_mm / 2, pc.ancho_mm / 2, -pc.fondo_mm / 2, pc.fondo_mm / 2))
    mm = compose_place(t.params.position.tuple(), t.params.rotation.tuple())
    z = -i.alto / 2 if pc.cara == "inferior" else i.alto / 2

    def mundo(x, y):
        g = (x, y, z, 1.0)
        return [round(sum(mm[r][k] * g[k] for k in range(4)), 1) for r in range(3)]

    prensas = []
    for p in res.prensas:
        fila = {"cable": p.cable, "designacion": p.designacion,
                **({"diametro_mm": p.diametro_mm} if p.diametro_mm else {})}
        if p.ref is not None:
            fila.update({"ref": p.ref, "rosca": p.rosca, "rango_mm": list(p.rango_mm),
                         "nombre": CATALOG[p.ref].name, "punto": mundo(p.x, p.y), "corrido_mm": p.corrido_mm})
        else:
            fila["motivo"] = p.motivo
        prensas.append(fila)
    return {"cara": pc.cara, "prensas": prensas, "avisos": list(res.avisos), "criterio": res.criterio,
            "supuestos": ["La placa pasacables va centrada en su cara (el catálogo no da su posición).",
                          "El recorrido del cable de campo sale por el punto de su canaleta: el corrimiento "
                          "del prensaestopas no se suma al largo."]}


def cuenta(resultados: list[dict]) -> dict[str, int]:
    """{ref: cantidad} de los prensaestopas elegidos (lo que compra la BOM, D9)."""
    out: dict[str, int] = {}
    for r in resultados:
        for p in r["prensas"]:
            if p.get("ref"):
                out[p["ref"]] = out.get(p["ref"], 0) + 1
    return out


def reglas(tableros, resultados: dict[str, dict]) -> list[dict]:
    """Avisos del ERC: un cable que sale sin prensaestopas posible y los que no entran en la placa."""
    filas = []
    for t in tableros:
        r = resultados.get(t.cid) or {}
        for p in r.get("prensas", ()):
            if p.get("ref"):
                continue
            filas.append({
                "regla": "prensaestopas", "estado": "aviso",
                "detalle": f"{p['designacion']} sale de {t.ubicacion} sin prensaestopas: {p['motivo']}",
                "recomendacion": "Elige un cable cuyo Ø entre en un prensaestopas del catálogo (M16–M40) o "
                                 "suma la ref del prensaestopas que lo sujete.",
                "norma": NORMA, "elementos": [p["cable"]]})
        for a in r.get("avisos", ()):
            filas.append({"regla": "prensaestopas", "estado": "aviso", "detalle": f"{t.ubicacion}: {a}",
                          "recomendacion": "Usa un gabinete con placa pasacables mayor o reparte los cables "
                                           "por otra cara.", "norma": "criterio de diseño",
                          "elementos": [f"{t.cid}_gabinete"]})
    return filas
