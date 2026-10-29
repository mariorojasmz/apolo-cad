"""¿Sobra alguna pieza? — la prueba de `diseno.sin_sobrantes` (plan puerta-sin-sobrediseno, D5,
D7 y D9). Lee el documento y reutiliza lo que la corrida de la puerta ya midió.

**Candidatas**: (a) las piezas que la puerta trata como guarda (los cuerpos de
`library/seguridad/guardas.revisar_guardas`) y (b) TODA pieza agregada después de la PRIMERA
corrida de la puerta (`doc.puerta_primera.ultimo_comando`: el comando de mayor número del log en
esa corrida; sin el dato, ninguna «agregada»; lo eléctrico —el `layout_tablero`, los
dispositivos— no cuenta como agregado: `del_carril`). Nunca son candidatas la tornillería (va con
lo que une), lo que gira o se mueve (es el peligro, no su resguardo), la banda ni los tensores (los
tensores que sobran son una nota del ítem de tensión: F1).

**Prueba** (sobre una COPIA del modelo sin la candidata, sin los `fasten`/`ground` que la nombran
y sin la tornillería que sólo la unía a ella: la de su `join_bolted` y la que no une otra cosa): la
candidata SOBRA si ningún control que puede empeorar sin ella empeora. Se corren de lo barato a
lo caro y la primera que empeora la declara necesaria (`la_pide`):

1. sujeción: ninguna otra pieza queda sin camino de carga (el grafo declarado de la entrega) ni
   pierde un APOYO: la candidata no sostiene a una vecina más lejos que ella del piso (en saltos
   de unión declarada). Un apoyo redundante —la segunda oreja de una guarda, la otra ménsula del
   drive— no «sobra»: el grafo no ve la palanca, y quitarlo dejaría la pieza colgando de un lado.
   De un apoyo se corren igual las sondas sin él y sin lo que sostiene: la evidencia dice
   `tambien_tapa` o `solo_apoyo` (D6 de lo-que-se-mueve, `calidad_sobrantes_apoyo.py`);
2. guardas: ningún cuerpo de guarda que estaba atornillado queda suelto o sin perno;
3. peligros, sondas RECTAS: los objetivos de cada peligro a ≤ `DIST_INFLUENCIA_MM` de ella (el
   brazo más la mano) siguen fuera del alcance; el de un peligro que ya fallaba en la corrida no
   suma sondas que llegan;
4. ingeniería (sólo si no es guarda: una placa, una ménsula, un refuerzo): ningún ítem de vida
   útil y estructura empeora (sin los lints: sin la pieza, sus barrenos quedan sin perno);
5. peligros con el brazo DOBLADO (sólo los resguardados): el campo de la muñeca sin ella, con los
   voxeles libres rehechos sólo en su zona (`CampoAlcance.libre_sin`); lo caro (~4–8 s en una
   faja de 2 m), sólo si 1–4 pasaron.

Las interferencias no se re-corren: quitar un sólido nunca crea un choque. La gravedad tampoco
(la sujeción declarada es lo que la puerta simula). **Voraz y en orden**: de la más pesada a la
más liviana y lo quitado queda quitado, así dos guardas que cubren el mismo hueco no salen las
dos «sobrantes»; una vuelta más re-prueba lo que pedían la sujeción o una guarda (lo que sólo
sostenía a una pieza que sobró después). Las formas OCCT se comparten (nunca se mutan): ni se regenera el log ni se toca
el documento. El llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

import copy
import time

from apolo.library.seguridad.iso13857 import ALCANCE_BRAZO_MM, ALCANCE_DESDE_MUNECA_MM

from .calidad_sobrantes_candidatas import (  # noqa: F401 — re-exportados por identidad
    MASA_MIN_KG,
    _tornilleria,
    candidatas,
    del_carril,
    marcar_primera_corrida,
    numero,
    ultimo_comando,
)

#: Un objetivo de un peligro se re-traza sin la candidata si ésta está a menos que esto de él: el
#: brazo (850 mm) más la mano desde la muñeca (230 mm, ISO 13857 tabla 6). Más lejos, ni el
#: antebrazo pasa por ella (D7: el costo se acota por zona).
DIST_INFLUENCIA_MM = ALCANCE_BRAZO_MM + ALCANCE_DESDE_MUNECA_MM
N_DIRECCIONES = 64  # las de la corrida (`controles_seguridad`)
#: Vueltas de la voraz: la segunda re-prueba lo que una quitada posterior pudo liberar.
MAX_VUELTAS = 3
_RANGO = {"FALLA": 0, "SIN_EVALUAR": 1, "OK": 2, "NO_APLICA": 3}
#: Lo que agrega la evidencia de un «apoyo de» (`calidad_sobrantes_apoyo`, D6 de lo-que-se-mueve).
_DE_APOYO = ("tambien_tapa", "solo_apoyo")


# ------------------------------------------------------------------ la copia sin la candidata
def _arrastra(c: str, quitadas: set, uniones: list[dict], hardware: set, jb: dict) -> set:
    """La candidata y la tornillería que sólo la unía a ella."""
    r = {c} | {h for h, par in jb.items() if c in par}
    socios: dict[str, set] = {}
    for u in uniones:
        socios.setdefault(u["a"], set()).add(u["b"])
        socios.setdefault(u["b"], set()).add(u["a"])
    for h in hardware - r - quitadas:
        s = socios.get(h, set()) - hardware
        if c in s and s <= quitadas | r:
            r.add(h)
    return r


def _dc_sin(dc: dict, q: set) -> dict:
    from .calidad_seguridad import piso_solido, z_piso

    piezas = {i: p for i, p in dc["piezas"].items() if i not in q}
    if piezas:
        lo = tuple(min(p.caja[0][k] for p in piezas.values()) for k in range(3))
        hi = tuple(max(p.caja[1][k] for p in piezas.values()) for k in range(3))
    else:
        lo = hi = (0.0, 0.0, 0.0)
    zp = z_piso(piezas, lo[2])
    return {**dc, "piezas": piezas, "caja": (lo, hi), "z_piso": zp,
            "piso_solido": piso_solido(piezas, zp),
            "solidos": {i: s for i, s in dc["solidos"].items() if i not in q},
            "uniones": [u for u in dc["uniones"] if u["a"] not in q and u["b"] not in q],
            "juntas": [j for j in dc["juntas"] if j.get("parent") not in q
                       and j.get("child") not in q]}


def doc_sin(doc, q: set):
    """Copia SUPERFICIAL del documento sin las piezas `q` ni lo que las nombra (las formas se
    comparten: nadie las muta)."""
    d = copy.copy(doc)
    d.scene = {k: v for k, v in doc.scene.items() if k not in q}
    d.fasteners = {k: f for k, f in doc.fasteners.items()
                   if f.get("a") not in q and f.get("b") not in q}
    d.grounds = {k: g for k, g in doc.grounds.items() if g.get("feature") not in q}
    d.mates = {k: m for k, m in doc.mates.items()
               if m.get("feature_a") not in q and m.get("feature_b") not in q}
    d.joints = {k: j for k, j in doc.joints.items()
                if j.get("parent") not in q and j.get("child") not in q}
    return d


# ------------------------------------------------------------------ cada control
def _sujecion(doc, q: set, hardware: set) -> tuple[set, dict, dict]:
    """(flotantes, vecinas, saltos al piso) del grafo declarado sin `q`. La tornillería se
    contrae: dos piezas unidas por un perno son vecinas y el perno no cuenta un salto."""
    from collections import deque

    from apolo.assembly.connectivity import build_graph, soundness_report

    escena = {k: v for k, v in doc.scene.items() if k not in q}
    g = build_graph(escena, doc.joints, doc.mates, doc.fasteners, doc.grounds)
    s = soundness_report(g)
    adj = g["adj"]
    vec = {x: ({y for y in ys if y not in hardware}
               | {z for h in ys if h in hardware for z in adj.get(h, ()) if z not in hardware})
           - {x} for x, ys in adj.items() if x not in hardware}
    d = {x: 0 for x in g["grounded_seed"] if x in vec}
    cola = deque(d)
    while cola:
        x = cola.popleft()
        for y in vec[x]:
            if y not in d:
                d[y] = d[x] + 1
                cola.append(y)
    return set(s.get("floating", [])) - hardware, vec, d


def _guardas(dc: dict, moviles: set) -> dict[str, str]:
    from apolo.library.seguridad.guardas import revisar_guardas

    rg = revisar_guardas(dc["piezas"], dc["uniones"], moviles & set(dc["piezas"]))
    return {i: g["estado"] for g in rg["guardas"] for i in g["ids"]}


def _vida(doc) -> dict[str, str]:
    from apolo.library.calidad.vida_util import controlar_vida_util

    from .calidad_mecanica import reglas_de_ingenieria

    return {i.id: i.estado for i in controlar_vida_util(reglas_de_ingenieria(doc, lints=False),
                                                         hay_motor=True, hay_uniones=True)}


def _dist_caja(caja, punto) -> float:
    lo, hi = caja
    return sum(max(lo[k] - punto[k], 0.0, punto[k] - hi[k]) ** 2 for k in range(3)) ** 0.5


def _cercanos(p: dict, r: set, piezas: dict) -> list[int]:
    """Los índices de los objetivos del peligro a ≤ `DIST_INFLUENCIA_MM` de lo que se quita, del
    más cercano al más lejano. Una sonda recta que llega lo hace a ≤ 850 mm de profundidad: todo
    lo que la para está a esa distancia de su objetivo (la locación vale para rectas y codo)."""
    cajas = [piezas[i].caja for i in r if i in piezas]
    d = [(min((_dist_caja(c, o) for c in cajas), default=float("inf")), k)
         for k, o in enumerate(p["objetivos"])]
    return [k for dk, k in sorted(d) if dk <= DIST_INFLUENCIA_MM]


def _n_direcciones(p: dict) -> int:
    """Las direcciones de la corrida para el peligro ENTERO (`evaluar_peligro` las baja con
    muchos objetivos): un subconjunto de objetivos se sondea igual que en la corrida."""
    from .calidad_sondas import MAX_SONDAS_PELIGRO

    n = len(p["objetivos"])
    return (N_DIRECCIONES if n * N_DIRECCIONES <= MAX_SONDAS_PELIGRO else
            max(16, MAX_SONDAS_PELIGRO // n))


def _llegan(sondas) -> int:
    return sum(1 for x in sondas if x.get("alcanza"))


class Prueba:
    """El estado de la prueba voraz: lo ya quitado y lo que la máquina cumple sin ello."""

    def __init__(self, doc, an: dict, sondas: dict, hardware: set, jb: dict):
        self.doc, self.an, self.hardware, self.jb = doc, an, hardware, jb
        self.quitadas: set = set()
        # el teselado y el campo del codo de F3 (F3c): las nubes por pieza no cambian sin otra
        self.compartido: dict = sondas.get("compartido") or {}
        self.nubes: dict = self.compartido.get("nubes", {})
        self.ms = {"sujecion": 0.0, "guardas": 0.0, "rectas": 0.0, "ingenieria": 0.0,
                   "codo": 0.0, "apoyo": 0.0}  # apoyo: D6 de lo-que-se-mueve
        self.etapa = {k: 0 for k in self.ms}
        self.flot, self.vec, self.saltos = _sujecion(doc, set(), hardware)
        self.guardas = _guardas(an["dc"], set(an["moviles"]))
        self._vida_base = None
        res = sondas["resultados"]
        # el que ya FALLA sólo se mide con las rectas (la corrida no lo dobló): ningún objetivo
        # suyo debe sumar sondas que llegan (`llegan_por`: por objetivo, medido sin lo quitado)
        self.peligros = [{**p, "estado": res[p["id"]]["estado"], "llegan_por": {}}
                         for p in sondas["peligros"]
                         if p.get("objetivos") and res[p["id"]]["estado"] in ("OK", "FALLA")]
        self.en_holgura = [p for p in sondas["peligros"] if p.get("en_holgura")]
        self._tr_base = None
        self._campo_base = None
        self._empuje_f3 = None

    def empuje(self, q: set, dc: dict):
        """La `BandaEmpujable` de la máquina sin `q` (`dc` = `_dc_sin(an["dc"], q)`): la de la
        corrida (la de F3 en `compartido`, o una armada una vez) con `q` enmascarado, sin rehacer
        sus árboles (plan puerta-rapida, D1); rehecha sólo si `q` quita una banda."""
        from .calidad_codo import BandaEmpujable

        if self._empuje_f3 is None:
            e = self.compartido.get("empuje")
            self._empuje_f3 = (e if e is not None and e.dc is self.an["dc"]
                               else BandaEmpujable(self.an["dc"], self.nubes))
        v = self._empuje_f3.sin(q)
        return v if v is not None else BandaEmpujable(dc, self.nubes)

    def _campo(self, dc: dict, empuje, r: set):
        """El campo de la muñeca sin lo quitado: la primera vez entero (y el de la base); después,
        el de la base con sólo la zona de `r` recalculada (`CampoAlcance.libre_sin` y
        `sin_zona`): el teselado y la distancia de las demás piezas no cambian. La base es el
        campo que F3 ya armó en la corrida (`compartido`), con lo ya quitado recalculado en su
        zona."""
        from .calidad_codo import campo_alcance

        if self._campo_base is None:
            base = _dc_sin(self.an["dc"], self.quitadas)
            f3 = self.compartido.get("campo")  # el de la corrida de F3: sin quitar nada (F3c)
            if f3 is not None and f3.misma_grilla(base["caja"], base["z_piso"],
                                                  base.get("piso_solido", False)):
                self._campo_base = (f3 if not self.quitadas else self._sin_zona(
                    f3, base, self.empuje(self.quitadas, base), self.quitadas))
            if self._campo_base is None:
                self._campo_base = campo_alcance(base["solidos"], base["caja"], base["z_piso"],
                                                 self.empuje(self.quitadas, base), self.nubes,
                                                 base.get("piso_solido", False))
        cb = self._campo_base
        return (self._sin_zona(cb, dc, empuje, r)
                or campo_alcance(dc["solidos"], dc["caja"], dc["z_piso"], empuje, self.nubes,
                                 dc.get("piso_solido", False)))

    def _sin_zona(self, cb, dc: dict, empuje, r: set):
        """El campo `cb` con sólo la zona de `r` recalculada sobre los sólidos de `dc`
        (`CampoAlcance.libre_sin` y `sin_zona`); None si la grilla cambió (otra caja o piso)."""
        import numpy as np

        from .calidad_codo import EMPUJE_MM, nubes_de

        cajas = [self.an["dc"]["piezas"][i].caja for i in r if i in self.an["dc"]["piezas"]]
        if not cajas or not cb.misma_grilla(dc["caja"], dc["z_piso"],
                                            dc.get("piso_solido", False)):
            return None
        lo = np.min([c[0] for c in cajas], axis=0) - EMPUJE_MM
        hi = np.max([c[1] for c in cajas], axis=0) + EMPUJE_MM
        a, b = lo - 100.0, hi + 100.0  # la holgura del brazo y del voxel, de sobra
        pts = []
        for fid, p in dc["piezas"].items():
            if fid not in dc["solidos"] or any(p.caja[1][k] < a[k] or p.caja[0][k] > b[k]
                                               for k in range(3)):
                continue
            x = nubes_de(dc["solidos"], [fid], self.nubes)
            x = x[np.all((x >= a) & (x <= b), axis=1)] if len(x) else x
            if empuje is not None and fid in empuje.bandas and len(x):
                x = x[~empuje.empujable(x)]
            pts.append(x)
        pts = np.concatenate(pts) if pts else np.zeros((0, 3))
        return cb.sin_zona(cb.libre_sin(pts, lo, hi))

    def _cron(self, etapa: str, t0: float) -> None:
        self.ms[etapa] += (time.perf_counter() - t0) * 1000.0
        self.etapa[etapa] += 1

    def probar(self, c: str) -> dict | None:
        """None si `c` sobra (y queda quitada); si no, {control, detalle}."""
        from .calidad_codo import sondas_con_codo
        from .calidad_sondas import Trazador

        doc, dc0 = self.doc, self.an["dc"]
        r = _arrastra(c, self.quitadas, dc0["uniones"], self.hardware, self.jb)
        q = self.quitadas | r
        nombre = lambda i: getattr(doc.scene.get(i), "name", None) or i  # noqa: E731
        t0 = time.perf_counter()
        dc_c = self.saltos.get(c)
        apoya = sorted(x for x in self.vec.get(c, ()) if x not in q and dc_c is not None
                       and self.saltos.get(x) is not None and self.saltos[x] > dc_c)
        if apoya:  # necesaria; las sondas sin ella (lo apoyado queda) sólo dicen la verdad (D6)
            self._cron("sujecion", t0)
            from .calidad_sobrantes_apoyo import tambien_tapa

            return {"control": "sujeción", "detalle": "es un apoyo de: "
                    + ", ".join(nombre(i) for i in apoya[:4]), **tambien_tapa(self, r, apoya)}
        flot, vec, saltos = _sujecion(doc, q, self.hardware)
        self._cron("sujecion", t0)
        nuevas = sorted(flot - self.flot - q)
        if nuevas:
            return {"control": "sujeción", "detalle": "sin ella quedan sin camino de carga: "
                    + ", ".join(nombre(i) for i in nuevas[:4])}
        t0 = time.perf_counter()
        dc = _dc_sin(dc0, q)
        moviles = set(self.an["moviles"]) - q
        guardas = _guardas(dc, moviles)
        self._cron("guardas", t0)
        sueltas = sorted(i for i, e in guardas.items() if e != "OK" and self.guardas.get(i) == "OK")
        if sueltas:
            return {"control": "guardas", "detalle": "sin ella queda sin atornillar: "
                    + ", ".join(nombre(i) for i in sueltas[:4])}
        tocados = [(p, ks) for p in self.peligros if (ks := _cercanos(p, r, dc0["piezas"]))]
        tocados.sort(key=lambda x: x[0]["estado"] == "FALLA")  # los que resguarda, primero
        tr = empuje = None
        if tocados:
            t0 = time.perf_counter()
            tr = Trazador(dc["solidos"])
            empuje = self.empuje(q, dc)
            for p, ks in tocados:
                malo = self._rectas(p, ks, tr, dc, empuje)
                if malo:
                    self._cron("rectas", t0)
                    return {"control": "peligros", "detalle": f"{p['peligro']}: {malo}"}
            self._cron("rectas", t0)
        t0 = time.perf_counter()
        malo, tr, empuje = self._holguras(r, dc, tr, empuje, q)
        self._cron("rectas", t0)
        if malo:
            return {"control": "peligros", "detalle": malo}
        if dc0["piezas"][c].rol != "guarda":
            t0 = time.perf_counter()
            if self._vida_base is None:
                self._vida_base = _vida(doc_sin(doc, self.quitadas))
            vida = _vida(doc_sin(doc, q))
            self._cron("ingenieria", t0)
            peores = sorted(i for i, e in vida.items()
                            if _RANGO[e] < _RANGO.get(self._vida_base.get(i, "NO_APLICA"), 3))
            if peores:
                return {"control": "ingeniería", "detalle": "sin ella empeora: "
                        + ", ".join(peores[:4])}
        else:
            vida = None
        doblar = [(p, ks) for p, ks in tocados if p["estado"] == "OK"]
        if doblar:
            t0 = time.perf_counter()
            campo = self._campo(dc, empuje, r)
            for p, ks in doblar:  # con > 8 objetivos el tope por objetivo depende de cuántos son
                sub = (p if len(p["objetivos"]) > 8 else
                       {**p, "objetivos": [p["objetivos"][k] for k in ks]})
                extra, _ms = sondas_con_codo(tr, campo, sub, N_DIRECCIONES, empuje)
                if _llegan(extra):
                    self._cron("codo", t0)
                    return {"control": "peligros", "detalle": f"{p['peligro']}: una sonda con el "
                            "brazo doblado llega sin ella"}
            self._cron("codo", t0)
        # sobra: queda quitada y lo medido sin ella es la nueva base
        self.quitadas, self.flot, self.guardas = q, flot, guardas
        self.vec, self.saltos = vec, saltos
        if vida is not None:
            self._vida_base = vida
        if doblar:
            self._campo_base = campo
        for p, _ks in tocados:
            p["llegan_por"].update(p.pop("_nuevas", {}))
        self._tr_base = None
        return None

    def _holguras(self, r: set, dc: dict, tr, empuje, q: set):
        """(motivo | None, tr, empuje): un objetivo que la corrida sacó por caer en una holgura
        funcional (`calidad_sondas.fuera_de_holguras`) vuelve a contar si lo quitado forma esa
        rendija; con ella abierta, se sondea con las rectas. `q`: todo lo quitado (`dc` sin él)."""
        from .calidad_sondas import Trazador, evaluar_peligro, holgura

        for p in self.en_holgura:
            puntos = [tuple(h["punto"]) for h in p["en_holgura"] if set(h["entre"]) & r]
            if not puntos:
                continue
            if tr is None:
                tr, empuje = Trazador(dc["solidos"]), self.empuje(q, dc)
            libres = [q for q in puntos if holgura(tr, q) is None]
            if not libres:
                continue
            s, _ms = evaluar_peligro(tr, {**p, "objetivos": libres}, dc["caja"], dc["z_piso"],
                                     N_DIRECCIONES, empuje.salta,
                                     piso_solido=dc.get("piso_solido", False))
            if _llegan(s):
                return (f"{p['peligro']}: sin ella se abre una holgura funcional y una sonda "
                        "recta llega"), tr, empuje
        return None, tr, empuje

    def _rectas(self, p: dict, ks: list[int], tr, dc: dict, empuje) -> str | None:
        """Las sondas rectas de los objetivos `ks` del peligro sin lo quitado: None si ninguno
        empeora (un peligro resguardado: ninguna llega; uno que ya falla: no llegan más que
        antes por objetivo). Deja lo medido en `p["_nuevas"]` (la base si la candidata sobra)."""
        from .calidad_sondas import Trazador, evaluar_peligro

        n = _n_direcciones(p)
        p["_nuevas"] = {}
        for k in ks:
            s, _ms = evaluar_peligro(tr, {**p, "objetivos": [p["objetivos"][k]]}, dc["caja"],
                                     dc["z_piso"], n, empuje.salta,
                                     piso_solido=dc.get("piso_solido", False))
            ahora = _llegan(s)
            p["_nuevas"][k] = ahora
            if p["estado"] == "OK":
                if ahora:
                    return "una sonda recta llega sin ella"
                continue
            if k not in p["llegan_por"]:  # la base de ese objetivo, con lo ya quitado
                if self._tr_base is None:
                    base = _dc_sin(self.an["dc"], self.quitadas)
                    self._tr_base = (Trazador(base["solidos"]), base,
                                     self.empuje(self.quitadas, base))
                tb, base, emp = self._tr_base
                sb, _ms = evaluar_peligro(tb, {**p, "objetivos": [p["objetivos"][k]]},
                                          base["caja"], base["z_piso"], n, emp.salta,
                                          piso_solido=base.get("piso_solido", False))
                p["llegan_por"][k] = _llegan(sb)
            if ahora > p["llegan_por"][k]:
                return (f"llegan {ahora} sondas rectas a un objetivo sin ella "
                        f"({p['llegan_por'][k]} con ella)")
        return None


def sobrantes(doc, contexto) -> dict:
    """El insumo de `diseno.sin_sobrantes` → {candidatas, sobrantes, necesarias, quitadas, ms,
    por_etapa}. Usa el análisis y las sondas de la corrida (`contexto`: `f3.analisis`,
    `f3.sondas`); sin ellas (la fuente «seguridad» no corrió) → {"error"}."""
    from .calidad_seguridad import analisis

    t0 = time.perf_counter()
    an = analisis(doc, contexto)
    sondas = contexto.una_vez("f3.sondas", lambda: None) if contexto is not None else None
    if sondas is None:
        return {"error": "las sondas de seguridad no corrieron en esta puerta"}
    hardware, jb = _tornilleria(doc, an["dc"]["piezas"])
    cands = candidatas(doc, an, hardware)
    prueba = Prueba(doc, an, sondas, hardware, jb)
    sobran, necesarias = [], []
    pendientes, vueltas = cands, 0
    while pendientes and vueltas < MAX_VUELTAS:
        vueltas += 1
        quedan, sobro = [], False
        for c in pendientes:
            c = {k: c[k] for k in ("id", "nombre", "masa_kg", "origen")}
            motivo = prueba.probar(c["id"])
            if motivo is None:
                sobran.append({**c, "la_pide": "ninguna prueba de la puerta"})
                sobro = True
            else:
                quedan.append({**c, "la_pide": motivo["control"], "detalle": motivo["detalle"],
                               **{k: motivo[k] for k in _DE_APOYO if k in motivo}})
        probadas = {c["id"] for c in pendientes}
        necesarias = [n for n in necesarias if n["id"] not in probadas] + quedan
        # otra vuelta sólo a lo que pedían la sujeción o una guarda: lo que sostenía o unía puede
        # haber sobrado después (la guarda lateral de un deflector que sobró); lo que pedía un
        # peligro, no (quitar más sólo abre más)
        pendientes = [n for n in quedan if n["la_pide"] in ("sujeción", "guardas")] if sobro else []
    necesarias.sort(key=lambda c: (-c["masa_kg"], c["id"]))
    return {"candidatas": len(cands), "sobrantes": sobran, "necesarias": necesarias,
            "vueltas": vueltas,
            "quitadas": sorted(prueba.quitadas),
            "agregadas_desde": (getattr(doc, "puerta_primera", None) or {}).get("ultimo_comando"),
            "ms": round((time.perf_counter() - t0) * 1000.0),
            "por_etapa": {k: {"pruebas": prueba.etapa[k], "ms": round(v)}
                          for k, v in prueba.ms.items()}}
