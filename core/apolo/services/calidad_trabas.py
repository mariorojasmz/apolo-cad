"""Las trabas de la posición de USO de un plegable, medidas (plan plegables-en-la-puerta, F3: D5 y
D6). El insumo de `plegado.traba`; el criterio está en `library/calidad/trabas.py`. Sólo con el
requisito `plegable`. El llamador sostiene STATE_LOCK.

- **Grados de libertad**: las juntas de movimiento que CAMBIAN entre uso y guardado del primer
  estudio válido (`calidad_plegado`) y ninguna restricción de lazo resuelve (los motores). Cada
  uno lleva el sentido en que pliega (el signo de guardado − uso) y los pivotes de lazo
  (`calidad_lazos.pivotes`) cuya cadena mueve.
- **La pose de uso** es la del fotograma con los lazos resueltos (como el estudio en la UI y en
  `scan_motion`); toda prueba parte de ella.
- **Tope**: la junta movida `PASO` sin resolver el lazo (la prueba de pose de
  `calidad_movimiento`); se miden los pares (pieza de la traba, pieza que esa junta mueve
  respecto de ella) que en uso están a ≤ `CERCA_MM` por caja o que son las dos de la traba.
- **Sobre-centro**: P = origen posado de la junta del brazo (la que mueve al padre de la
  rodilla), K = origen posado de la rodilla (la junta del `punto_coincidente`), Q = su punto; el
  ángulo es 180° − ∠PKQ en el plano normal al eje de la rodilla y el lado, el signo de K respecto
  de la recta PQ en uso y en guardado. El tope de la rodilla se prueba moviéndola `PASO` hacia
  donde el ángulo crece (se dobla más).
- **Tirante**: el grado movido `PASO` desde el uso. Una rodilla (los dos brazos rígidos de D4)
  cierra si |PQ| está entre la diferencia y la suma de sus brazos: se mide por geometría a lo
  largo del camino. Otro lazo, por continuación con sus restricciones (como `calidad_lazos`).
"""

from __future__ import annotations

import math

#: Lo que una pieza puede distar por caja de la de la traba para medirse como su tope (mm).
CERCA_MM = 2.5


def requiere(doc) -> bool:
    from .calidad_plegado import requiere as plegable

    return plegable(doc)


def trabas(doc) -> dict | None:
    """El insumo de `plegado.traba` (formato en `library/calidad/trabas.traba`), o None sin el
    requisito."""
    if not requiere(doc):
        return None
    from apolo.library.calidad.plegado import es_valido

    from .calidad_plegado import _etiquetado, _valores_resueltos, estudios

    e = next((x for x in estudios(doc) if es_valido(x)), None)
    if e is None:
        return {"estudio": None, "grados": [], "trabas": []}
    ctx = _Ctx(doc, _valores_resueltos(doc, e["uso"]["values"]),
               _valores_resueltos(doc, e["guardado"]["values"]))
    deps = {c.get("joint") for c in (doc.constraints or {}).values()}
    from .calidad_movimiento import MOVIMIENTO

    grados = []
    for g in e["cambian"]:
        if g in deps or doc.joints[g].get("type") not in MOVIMIENTO:
            continue
        d = ctx.guardado.get(g, 0.0) - ctx.uso.get(g, 0.0)
        grados.append({"grado": g, "pliega": "+" if d > 0 else "-",
                       "lazos": [p["nombre"] for p in ctx.pivotes if g in p["cadena"]]})
    por_grado = {g["grado"]: g for g in grados}
    filas = []
    kf = _etiquetado(doc.motion[e["estudio"]], "uso") or {}
    for k, t in enumerate(kf.get("trabas") or []):
        fila = {"indice": k, **{c: t[c] for c in ("junta", "sentido", "tipo", "piezas", "nota")
                                if c in t}}
        g = t.get("grado") or t.get("junta")
        fila["grado"] = g
        if g not in por_grado:
            fila["ignorada"] = _por_que_no(doc, e, g, deps)
            filas.append(fila)
            continue
        fila["pliega"] = por_grado[g]["pliega"]
        fila["faltan"] = [p for p in t.get("piezas") or [] if p not in doc.scene]
        if not fila["faltan"]:
            try:
                fila["medida"] = ctx.medir(t, g)
            except Exception as exc:  # noqa: BLE001 — no se pudo medir: SIN_EVALUAR, nunca OK
                fila["medida"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
        filas.append(fila)
    return {"estudio": e["estudio"], "grados": grados, "trabas": filas}


def _por_que_no(doc, e, g, deps) -> str:
    if g not in doc.joints:
        return f"la junta {g} ya no existe"
    if g in deps:
        return (f"{g} la resuelve un lazo: no es un grado de libertad; nombra en \"grado\" la "
                f"junta motora y {g} en \"junta\"")
    if g not in e["cambian"]:
        return f"{g} no cambia entre uso y guardado: no pliega"
    return f"{g} no es una junta de movimiento"


class _Ctx:
    """Lo que comparten las trabas de una corrida: la pose de uso, la de guardado, los pivotes."""

    def __init__(self, doc, uso: dict, guardado: dict):
        from .calidad_lazos import pivotes
        from .delivery_inputs import _juntas_que_mueven

        self.doc, self.uso, self.guardado = doc, uso, guardado
        self.by_child = {j["child"]: j for j in doc.joints.values()}
        self.pivotes = pivotes(doc)
        for p in self.pivotes:
            p["cadena"] = _juntas_que_mueven(doc, doc.joints[p["junta"]]["child"])
        self._formas: dict = {}

    # -------------------------------------------------------------- la FK
    def loc(self, vals: dict, fid: str, cache: dict):
        from apolo.robotics.pose import feature_location

        return feature_location(self.doc.joints, vals, fid, self.by_child, cache)

    def formas(self, vals: dict) -> dict:
        """{fid: (clave de ubicación, forma posada)} de todo sólido que no es guía."""
        clave = tuple(sorted(vals.items()))
        if clave not in self._formas:
            from .calidad_plegado import _clave_loc

            cache: dict = {}
            out = {}
            for fid, f in self.doc.scene.items():
                if getattr(f, "is_guide", False) or getattr(f, "shape", None) is None:
                    continue
                lc = self.loc(vals, fid, cache)
                out[fid] = (_clave_loc(lc), (lc * f.shape) if lc is not None else f.shape)
            self._formas = {clave: out} if len(self._formas) > 6 else {**self._formas, clave: out}
        return self._formas[clave]

    def punto(self, vals: dict, fid: str, p) -> tuple:
        from build123d import Pos

        from apolo.library import ejes_giro as E

        p = E.vec(p)
        lc = self.loc(vals, fid, {})
        if lc is None:
            return p
        v = (lc * Pos(*p)).position
        return (v.X, v.Y, v.Z)

    # -------------------------------------------------------------- por tipo
    def medir(self, t: dict, g: str) -> dict:
        tipo = t["tipo"]
        sgn = 1.0 if t["sentido"] == "+" else -1.0
        if tipo == "tope":
            jm = t.get("junta") or g
            if jm == g:
                return self.tope(t["piezas"], g, sgn * _paso(self.doc.joints[g]))
            d = self.continuar(g, sgn * 1.0, self.propias(g))[0].get(jm, 0.0) - self.uso.get(jm, 0.0)
            if abs(d) < 1e-6:
                return {"error": f"{jm} no se mueve cuando {g} se mueve en «{t['sentido']}»"}
            return self.tope(t["piezas"], jm, math.copysign(_paso(self.doc.joints[jm]), d))
        if tipo == "sobre_centro":
            return {"lazos": [self.rodilla(p, t["piezas"]) for p in self.lazos(g, t.get("junta"))]}
        if tipo == "tirante":
            return self.tirante(g, sgn * _paso(self.doc.joints[g]), t.get("junta"))
        if tipo == "retenida":
            return self.retenida(t["piezas"])
        return {}

    def lazos(self, g: str, junta: str | None) -> list[dict]:
        if junta and junta != g:
            return [p for p in self.pivotes if junta in (p["junta"], self._brazo(p))]
        return [p for p in self.pivotes if g in p["cadena"]]

    def propias(self, g: str, junta: str | None = None) -> dict:
        cadenas = set().union(*(set(p["cadena"]) for p in self.lazos(g, junta))) \
            if self.lazos(g, junta) else set()
        return {n: c for n, c in (self.doc.constraints or {}).items() if c.get("joint") in cadenas}

    def continuar(self, motor: str, delta: float, propias: dict, pasos: int = 6) -> tuple:
        """(valores, residuo) con `motor` movido `delta` desde el uso, el lazo resuelto por
        continuación (cada paso arranca de la solución del anterior, como `calidad_lazos`). Un
        paso que no cierra NO corta: cerca del punto muerto de la rodilla el solver se estanca en
        un paso y el siguiente vuelve a cerrar (medido en la rodilla de 2,25° de los tests)."""
        from apolo.assembly.constraints import solve_constraints

        from .calidad_lazos import _residuo

        vals = dict(self.uso)
        if not propias:
            return {**vals, motor: vals.get(motor, 0.0) + delta}, 0.0
        for k in range(1, pasos + 1):
            vals = solve_constraints(self.doc.joints, propias,
                                     {**vals, motor: self.uso.get(motor, 0.0) + delta * k / pasos})
        return vals, _residuo(self.doc.joints, vals, propias)

    def tope(self, piezas: list[str], junta: str, delta: float) -> dict:
        from apolo.kernel.measure import measure_distance

        from .calidad_movimiento import _comun

        prueba = {**self.uso, junta: self.uso.get(junta, 0.0) + delta}
        f0, f1 = self.formas(self.uso), self.formas(prueba)
        pares, vistos = [], set()
        for a in piezas:
            if a not in f0:
                continue
            bb = f0[a][1].bounding_box()
            for b, (k0, sb) in f0.items():
                par = frozenset((a, b))
                if b == a or par in vistos:
                    continue
                if (f0[a][0] != f1[a][0]) == (k0 != f1[b][0]):
                    continue  # la junta no mueve una respecto de la otra
                if b not in piezas and not _cajas_cerca(bb, sb.bounding_box(), CERCA_MM):
                    continue
                vistos.add(par)
                try:
                    d = float(measure_distance(f0[a][1], sb)["dist_mm"])
                except Exception:  # noqa: BLE001 — sin distancia no hay tope que medir
                    continue
                if d > CERCA_MM:
                    continue
                c0, c1 = _comun(f0[a][1], sb), _comun(f1[a][1], f1[b][1])
                pares.append({"a": a, "b": b, "dist_mm": round(d, 3),
                              "comun_uso_mm3": None if math.isnan(c0) else round(c0, 1),
                              "comun_prueba_mm3": None if math.isnan(c1) else round(c1, 1)})
        return {"junta": junta, "valor": round(delta, 3), "pares": pares}

    def _brazo(self, piv: dict) -> str | None:
        from .enclavamientos import junta_movil

        j = junta_movil(self.doc, self.doc.joints[piv["junta"]]["parent"])
        return j["name"] if j else None

    def _pkq(self, vals: dict, piv: dict, anclado: bool = False) -> tuple | None:
        """(ángulo 180° − ∠PKQ en grados, lado de K respecto de PQ) en la pose `vals`; con
        `anclado`, Q es el ancla posada del `punto_coincidente` (la rodilla movida sola)."""
        from apolo.library import ejes_giro as E

        joints = self.doc.joints
        jk = joints[piv["junta"]]
        jp = joints.get(self._brazo(piv) or "")
        if jp is None:
            return None
        con = self.doc.constraints[piv["nombre"]]
        p = self.punto(vals, jp["parent"], jp["origin"])
        k = self.punto(vals, jk["parent"], jk["origin"])
        q = self.punto(vals, jk["child"], con["anchor"]) if anclado else E.vec(con["point"])
        eje = E.unit(E.vec(jk["axis"]))
        kp, kq = _plano(_resta(p, k), eje), _plano(_resta(q, k), eje)
        nkp, nkq = _norma(kp), _norma(kq)
        if nkp < 1e-9 or nkq < 1e-9:
            return None
        cos = max(-1.0, min(1.0, sum(x * y for x, y in zip(kp, kq)) / (nkp * nkq)))
        ang = 180.0 - math.degrees(math.acos(cos))
        lado = sum(x * y for x, y in zip(_cruz(_resta(k, p), _resta(q, p)), eje))
        return ang, (1 if lado > 1e-9 else -1 if lado < -1e-9 else 0)

    def rodilla(self, piv: dict, piezas: list[str]) -> dict:
        from .calidad_lazos import _residuo

        out = {"pivote": piv["nombre"], "rodilla": piv["junta"]}
        propias = {n: c for n, c in (self.doc.constraints or {}).items()
                   if c.get("joint") in piv["cadena"]}
        uso = self._pkq(self.uso, piv)
        if uso is None:
            return {**out, "error": "la rodilla no tiene un brazo con junta (P) o sus pivotes "
                                    "coinciden"}
        out.update(angulo_deg=round(uso[0], 3), lado_uso=uso[1],
                   residuo_uso_mm=round(_residuo(self.doc.joints, self.uso, propias), 3))
        gu = self._pkq(self.guardado, piv)
        out["lado_guardado"] = gu[1] if gu else None
        paso = _paso(self.doc.joints[piv["junta"]])
        mas = []
        for s in (1.0, -1.0):
            v = {**self.uso, piv["junta"]: self.uso.get(piv["junta"], 0.0) + s * paso}
            r = self._pkq(v, piv, anclado=True)
            mas.append((r[0] if r else -1e9, s))
        s = max(mas)[1]  # hacia donde la rodilla se dobla más
        out["tope"] = self.tope(piezas, piv["junta"], s * paso)
        return out

    def _abre(self, piv: dict, vals: dict) -> float | None:
        """Lo que le falta (mm) a una rodilla P-K-Q para cerrar en la pose `vals`: sus dos brazos
        son rígidos (|PK| y |KQ| de diseño), así que cierra si y sólo si |PQ| está entre su
        diferencia y su suma. None si el lazo no es una rodilla (sin brazo con junta en P)."""
        from apolo.library import ejes_giro as E

        jk = self.doc.joints[piv["junta"]]
        jp = self.doc.joints.get(self._brazo(piv) or "")
        if jp is None:
            return None
        con = self.doc.constraints[piv["nombre"]]
        p0, k0, q0 = E.vec(jp["origin"]), E.vec(jk["origin"]), E.vec(con["anchor"])
        a, b = _norma(_resta(k0, p0)), _norma(_resta(q0, k0))
        d = _norma(_resta(E.vec(con["point"]), self.punto(vals, jp["parent"], jp["origin"])))
        return max(0.0, d - (a + b), abs(a - b) - d)

    def tirante(self, g: str, delta: float, junta: str | None, pasos: int = 6) -> dict:
        """El lazo con el grado movido `delta` desde el uso. Si todos sus lazos son rodillas
        (lo que declara D4), por geometría: el mayor faltante de cierre en `pasos` puntos del
        camino (bloqueado a mitad = no llega). Si no, el solver por continuación: sin solución,
        `least_squares` gasta todas sus evaluaciones (≈ 7 s de CPU por prueba en la fixture)."""
        from apolo.library.calidad.movimiento import RESIDUO_LAZO_MM

        from .calidad_lazos import _residuo

        lazos = self.lazos(g, junta)
        out = {"grado": g, "valor": round(delta, 3), "lazos": [p["nombre"] for p in lazos]}
        if not lazos:
            return out
        propias = self.propias(g, junta)
        out["residuo_uso_mm"] = round(_residuo(self.doc.joints, self.uso, propias), 3)
        if all(self._abre(p, self.uso) is not None for p in lazos):
            peor, hasta = 0.0, delta
            for k in range(1, pasos + 1):
                v = {**self.uso, g: self.uso.get(g, 0.0) + delta * k / pasos}
                peor = max(self._abre(p, v) for p in lazos)
                hasta = delta * k / pasos
                if peor > RESIDUO_LAZO_MM:
                    break
            out.update(metodo="rodilla", residuo_prueba_mm=round(peor, 3), hasta=round(hasta, 3))
            return out
        vals, r = self.continuar(g, delta, propias)
        out.update(metodo="solver", residuo_prueba_mm=round(r, 3), hasta=round(delta, 3))
        return out

    def retenida(self, piezas: list[str]) -> dict:
        from apolo.kernel.measure import measure_distance
        from apolo.library.ejes_giro import tipo_reten

        f0 = self.formas(self.uso)
        retenes, retenidas = [], []
        for p in piezas:
            tipo = tipo_reten(getattr(self.doc.scene[p], "name", ""))
            (retenes if tipo else retenidas).append((p, tipo))
        out_r = []
        for fid, tipo in retenes:
            ds = []
            for o, _t in retenidas:
                try:
                    ds.append(float(measure_distance(f0[fid][1], f0[o][1])["dist_mm"]))
                except Exception:  # noqa: BLE001 — sin distancia: no se sabe si toca
                    continue
            out_r.append({"fid": fid, "tipo": tipo,
                          "dist_mm": round(min(ds), 3) if ds else None})
        return {"retenes": out_r, "retenidas": [p for p, _t in retenidas]}


def _paso(j: dict) -> float:
    """Lo que se mueve la junta en cada prueba: `calidad_movimiento.PASO` (3° en una de giro,
    3 mm en una prismática), sin acotar a sus límites (un límite declarado no es un tope)."""
    from .calidad_movimiento import PASO

    return PASO


def _cajas_cerca(a, b, tol: float) -> bool:
    return (a.min.X - tol <= b.max.X and b.min.X - tol <= a.max.X and a.min.Y - tol <= b.max.Y
            and b.min.Y - tol <= a.max.Y and a.min.Z - tol <= b.max.Z and b.min.Z - tol <= a.max.Z)


def _resta(a, b) -> tuple:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cruz(a, b) -> tuple:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norma(a) -> float:
    return math.sqrt(sum(x * x for x in a))


def _plano(v, eje) -> tuple:
    """`v` sin su componente sobre `eje` (unitario)."""
    t = sum(x * y for x, y in zip(v, eje))
    return (v[0] - t * eje[0], v[1] - t * eje[1], v[2] - t * eje[2])
