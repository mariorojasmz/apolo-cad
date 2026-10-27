"""La cadena de IZAJE en pose (plan `docs/plans/cadena-de-izaje.md`, D6): una cadena abierta no
es un cuerpo rígido, así que la FK no la mueve con una junta; la REHACE desde donde quedaron sus
dos amarres.

Cada pieza de `create_hoist_chain` se reconoce por su `mesh_key` («izaje|…»,
`library/izaje_geom.clave`: los números con que se construyó) y sus anclas por las uniones
`{cadena}_pasador_a|b`. Si alguna ancla se movió (cuelga, con juntas `fija`, de la pieza que
sube), la cadena se rearma con el MISMO número de pasos desde el pasador A posado hacia el B
posado: el ramal que se mueve se mueve, el largo se conserva. Avisa si el último rodillo no cae
en el ancla B (la pieza se movió fuera de los ramales: tiraría o aflojaría la cadena) o si un
amarre se sale del plano de la cadena.
"""

from __future__ import annotations

from collections.abc import Callable

#: Lo que el último rodillo puede quedar lejos del ancla B (mm) sin aviso.
TOL_AMARRE_MM = 1.0


def _aplicar(m, p) -> list[float]:
    return [m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3)]


def _posado(loc, p) -> list[float]:
    if loc is None:
        return list(p)
    from build123d import Location

    v = (loc * Location(tuple(p))).position
    return [v.X, v.Y, v.Z]


def _girar_pinones(doc, feat, d, c0, c, out: dict, location_de: Callable) -> None:
    """Los piñones fijos ruedan con la cadena: cada uno gira lo que corrieron sus rodillos
    asentados (módulo un diente: el piñón es simétrico), así sus dientes siguen en los asientos
    como en el diseño. Uno que la FK ya mueve (cuelga de una junta con valor) no se toca."""
    import math

    from build123d import Axis

    m = feat.matrix
    eje = (m[0][2], m[1][2], m[2][2])
    for k, pin in enumerate(d.pinones):
        fid = (doc.fasteners or {}).get(f"{feat.id}_p{k + 1}", {}).get("b")
        if fid not in out or location_de(fid) is not None or not c0.asentados[k] or not c.asentados[k]:
            continue
        q0, q1 = c0.puntos[c0.asentados[k][0]], c.puntos[c.asentados[k][0]]
        diente = 2.0 * math.pi / pin.z
        giro = math.remainder(math.atan2(q1[1] - pin.cy, q1[0] - pin.cx)
                              - math.atan2(q0[1] - pin.cy, q0[0] - pin.cx), diente)
        if abs(giro) > 1e-9:
            centro = _aplicar(m, (pin.cx, pin.cy, 0.0))
            out[fid] = out[fid].rotate(Axis(tuple(centro), eje), math.degrees(giro))


def posar_cadenas_izaje(doc, out: dict, location_de: Callable) -> list[str]:
    """Reemplaza en `out` ({fid: shape posado}) cada cadena de izaje cuyas anclas se movieron.
    `location_de(fid)` = la Location de la FK de esa pieza (None = no se movió). Devuelve avisos."""
    avisos: list[str] = []
    cadenas = [f for f in doc.scene.values()
               if (f.mesh_key or "").startswith("izaje|") and f.matrix and f.id in out]
    if not cadenas:
        return avisos
    from apolo.kernel.matrix import invert_rigid
    from apolo.kernel.shapes import place_matrix
    from apolo.library.catalog import CATALOG
    from apolo.library.izaje_geom import cadena_posada, datos_de_clave, diseno

    for feat in cadenas:
        d = datos_de_clave(feat.mesh_key)
        comp = CATALOG.get(d.cadena) if d else None
        anclas = [(doc.fasteners or {}).get(f"{feat.id}_pasador_{lado}", {}).get("b") for lado in "ab"]
        if comp is None or None in anclas:
            continue
        locs = [location_de(fid) for fid in anclas]
        if all(loc is None for loc in locs):
            continue
        try:
            c0 = diseno(d, float(comp.specs["paso"]))
        except ValueError:
            continue
        m = feat.matrix
        inv = invert_rigid(m)
        extremos = []
        for loc, q, lado in zip(locs, (c0.puntos[0], c0.puntos[-1]), "AB"):
            local = _aplicar(inv, _posado(loc, _aplicar(m, (q[0], q[1], 0.0))))
            if abs(local[2]) > TOL_AMARRE_MM:
                avisos.append(f"La cadena de izaje '{feat.name}': el amarre {lado} sale {local[2]:+.1f} mm del "
                              "plano de la cadena en esta pose")
            extremos.append((local[0], local[1]))
        try:
            piezas, c = cadena_posada(d, comp.specs, extremos[0], extremos[1])
        except ValueError as exc:
            avisos.append(f"La cadena de izaje '{feat.name}' no se arma en esta pose: {exc}")
            continue
        out[feat.id] = place_matrix(piezas, m)
        _girar_pinones(doc, feat, d, c0, c, out, location_de)
        if abs(c.falta_mm) > TOL_AMARRE_MM:
            que = "no llega a" if c.falta_mm > 0 else "se pasa de"
            avisos.append(
                f"La cadena de izaje '{feat.name}' {que} su amarre B por {abs(c.falta_mm):.1f} mm en esta pose: "
                "la pieza se mueve fuera de los ramales (la cadena tiraría o quedaría floja)")
    return avisos
