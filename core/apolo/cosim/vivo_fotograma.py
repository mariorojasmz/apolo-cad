"""La tabla y el fotograma binario de la sesión en vivo (plan V8.4 D2).

TABLA (va UNA vez, en el primer mensaje del WebSocket; los índices ordenan el fotograma):
  - `cuerpos`: [{name, junta, piezas}] — los cuerpos móviles de la dinámica, con sus piezas;
  - `productos`: [{name, producto, dims_mm}] — la cola del escenario de base (MuJoCo no crea
    cuerpos en marcha: el pool es fijo; los que aún no nacieron o ya retiró un sumidero van NaN);
  - `juntas`: [{name, tipo, unidad}] · `bandas`: [{pieza, junta, radio_mm, direccion}];
  - `senales`: [nombre] — las señales NUMÉRICAS (bool → 0/1, enteros, floats) con nombre D10;
    una que aparece después llega en `{"tipo": "senales", "desde": i, "nombres": [...]}` ANTES
    del fotograma que la trae. Las de texto (estado del PLC, falla) no viajan en el binario: van
    en `{"tipo": "textos", "t", "valores"}` sólo cuando cambian;
  - `mandos`: [{designacion, tipo, ref, acciones, color, pieza?, retorno?, actuadores?,
    potenciometro?, posiciones?, senales}] · `pilotos`: [{designacion, ref, color, pieza?, senal}]
    · `dispositivos`: [{designacion, tipo, ref, pieza?}] (las etiquetas de D5: motor, variador…)
    · `valvulas` (V8.9 F6, sólo si hay): [{designacion, ref, lados, manual, pieza?}] — las
    electroválvulas y su accionamiento manual (`accionar_manual`, que el WebSocket ya acepta);
  - `fallas`: [{designacion, tipo, fallas: [{falla, pide, opciones?}]}] y `ramas`: [{id, tipo:
    contacto | conductor, red, dispositivo?}] — lo que se puede hacer fallar (cosim-fallas D6,
    `fallas.catalogo`); la UI ofrece sólo eso. Una falla activa viaja en `<des>.averia` (texto).

FOTOGRAMA (float32 little-endian; `FORMATO` = 1):
  [0] formato · [1] t (s virtuales) · [2] factor de tiempo real medido · [3] nc · [4] np · [5] nj
  · [6] nb · [7] ns, y después
  - nc × 7: cada cuerpo RELATIVO a su pose inicial, T(t) = P(t)·P(0)⁻¹, como x, y, z (mm), qx,
    qy, qz, qw (el orden de three.js; lo mismo que `cuerpos[].poses` de la serie de la marcha);
  - np × 7: el centro de cada producto en ABSOLUTO (x, y, z mm, qx, qy, qz, qw), NaN si no está;
  - nj: q de cada junta (grados o mm) · nb: velocidad de la cara de la banda (m/s, la de la serie)
  - ns: el valor de cada señal de la tabla (NaN si ese intercambio no la trae).
Con 12 cuerpos y 133 señales pesa ~1,2 KB (F0). Puro: numpy y la física sin OCCT.
"""

from __future__ import annotations

import math

import numpy as np

from apolo.physics.dinamica_serie import _quat_xyzw
from apolo.physics.sim import MM, _pose_matrix

from .fallas import catalogo

FORMATO = 1
CABECERA = 8
NAN = float("nan")
#: tipos de modelo que se aprietan (D4) y su forma de mando; el resguardo (mandos-de-seguridad D2)
#: se abre y se cierra como el seccionador (`abrir`/`cerrar`, señal `<des>.cerrado`)
MANDOS = ("pulsador", "seta", "selector", "seccionador", "resguardo")
#: ISO 13850: la seta es roja sobre fondo amarillo (su ficha no trae `color`)
COLOR_SETA = ("rojo", "amarillo")


def _numero(v) -> float | None:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _mando(des: str, m, d) -> dict:
    out = {"designacion": des, "tipo": m.tipo, "ref": m.ref, "acciones": list(m.ACCIONES),
           "color": d.color if d is not None else None}
    if m.tipo == "seta":
        out["color"], out["fondo"] = out["color"] or COLOR_SETA[0], COLOR_SETA[1]
    if d is not None and d.pieza:
        out["pieza"] = d.pieza
    if m.tipo == "pulsador":
        out["retorno"] = m.retorno
        out["actuadores"] = list(m.nombres)
        out["potenciometro"] = m.potenciometro is not None
    elif m.tipo == "selector":
        out["posiciones"] = [str(p) for p in m.posiciones]
    out["senales"] = [f"{des}.{c}" for c in m.salidas()]
    return out


class Fotograma:
    """Arma la tabla y empaca cada fotograma de una `Corrida`. Se crea ANTES del primer
    intercambio: la pose inicial P(0) es la del fotograma 0 de la dinámica."""

    def __init__(self, corrida):
        self.c = c = corrida
        integ = c.integ
        dyn = integ.snap
        d = integ.d
        self.cuerpos = [(cu["name"], integ.bid_cuerpo[cu["name"]]) for cu in dyn.cuerpos]
        self.p0_inv = [np.linalg.inv(np.asarray(_pose_matrix(d.xpos[b], d.xquat[b]), float))
                       for _, b in self.cuerpos]
        self.juntas = list(dyn.juntas)
        self.senales: list[str] = []
        self._idx: dict[str, int] = {}
        self._textos: dict = {}
        self._ultimos_textos: dict = {}

    # ── la tabla ─────────────────────────────────────────────────────────────────────────────

    def tabla(self) -> dict:
        c = self.c
        dyn = c.integ.snap
        por_des = {x.designacion: x for x in c.snap.dispositivos}
        modelos = c.tab.modelos
        mandos = [_mando(des, m, por_des.get(des)) for des, m in modelos.items() if m.tipo in MANDOS]
        pilotos = []
        for des, m in modelos.items():
            if m.tipo == "piloto":
                x = por_des.get(des)
                pilotos.append({"designacion": des, "ref": m.ref, "color": x.color if x else None,
                                **({"pieza": x.pieza} if x and x.pieza else {}), "senal": f"{des}.encendido"})
        dispositivos = [{"designacion": des, "tipo": m.tipo, "ref": m.ref,
                         **({"pieza": por_des[des].pieza} if des in por_des and por_des[des].pieza else {}),
                         # V8.9 F6: la carrera nominal (la lectura no la pasa por el tope blando)
                         **({"carrera_mm": round(m.carrera * 1000.0, 3)} if m.tipo == "cilindro" else {})}
                        for des, m in modelos.items()]
        # V8.9 F6: las electroválvulas con su accionamiento manual (el grupo plegado de «Mandos»);
        # sin válvulas no va la clave (la tabla de siempre)
        valvulas = [{"designacion": des, "ref": m.ref, "lados": list(m.lados), "manual": bool(m.manual),
                     **({"pieza": por_des[des].pieza} if des in por_des and por_des[des].pieza else {})}
                    for des, m in modelos.items() if m.tipo == "electrovalvula"]
        giro = c.integ.giro
        return {
            "formato": FORMATO, "dt_s": c.dt,
            "cuerpos": [{"name": cu["name"], "junta": cu["junta"], "piezas": list(cu["piezas"])}
                        for cu in dyn.cuerpos],
            "productos": [{"name": p["name"], "producto": p.get("producto", p["name"]),
                           "dims_mm": [p["w"], p["d"], p["h"]]} for p in dyn.productos],
            "juntas": [{"name": n, "tipo": dyn.juntas[n]["tipo"], "unidad": "grados" if giro[n] else "mm"}
                       for n in self.juntas],
            "bandas": [{"pieza": b.pieza, "junta": b.junta, "radio_mm": round(b.radio / MM, 2),
                        "direccion": [round(float(x), 6) for x in b.e]} for b in dyn.bandas],
            "senales": list(self.senales),
            "mandos": mandos, "pilotos": pilotos, "dispositivos": dispositivos,
            **({"valvulas": valvulas} if valvulas else {}),
            **catalogo(c.tab),
        }

    # ── cada fotograma ───────────────────────────────────────────────────────────────────────

    def reunir(self) -> tuple[list[str], dict]:
        """Las señales de ESTE intercambio: (nombres nuevos para la tabla, valores numéricos);
        los textos quedan para `textos_cambiados`."""
        nuevas, valores = [], {}
        filas = [(pref + n, v) for pref, s in self.c.fuentes() for n, v in s.items()]
        filas += list(self.c.analogicas_extra().items())
        for nombre, v in filas:
            x = _numero(v)
            if x is None:
                if v is not None and nombre not in self._idx:
                    self._textos[nombre] = v
                continue
            if nombre not in self._idx:
                self._idx[nombre] = len(self.senales)
                self.senales.append(nombre)
                nuevas.append(nombre)
            valores[nombre] = x
        return nuevas, valores

    def textos_cambiados(self) -> dict:
        out = {n: v for n, v in self._textos.items() if self._ultimos_textos.get(n, object()) != v}
        self._ultimos_textos.update(out)
        return out

    def empacar(self, t: float, factor: float, valores: dict) -> bytes:
        integ = self.c.integ
        d = integ.d
        nc, np_, nj = len(self.cuerpos), len(integ.bid_prod), len(self.juntas)
        bandas = integ.snap.bandas
        ns = len(self.senales)
        buf = np.full(CABECERA + 7 * (nc + np_) + nj + len(bandas) + ns, NAN, np.float32)
        buf[:CABECERA] = (FORMATO, t, factor, nc, np_, nj, len(bandas), ns)
        i = CABECERA
        for (_, b), p0i in zip(self.cuerpos, self.p0_inv):
            m = np.asarray(_pose_matrix(d.xpos[b], d.xquat[b]), float) @ p0i
            buf[i: i + 3] = m[:3, 3]
            buf[i + 3: i + 7] = _quat_xyzw(m[:3, :3])
            i += 7
        for k, b in enumerate(integ.bid_prod):
            if integ.activo[k]:
                w, x, y, z = (float(q) for q in d.xquat[b])
                if w < 0:
                    w, x, y, z = -w, -x, -y, -z
                buf[i: i + 3] = [float(c) / MM for c in d.xpos[b]]
                buf[i + 3: i + 7] = (x, y, z, w)
            i += 7
        for n in self.juntas:
            buf[i] = integ.q_apolo(n)[0]
            i += 1
        for b in bandas:
            da = integ.juntas[b.junta][1] if b.junta in integ.juntas else None
            buf[i] = float(d.qvel[da]) * b.radio if da is not None else NAN
            i += 1
        for nombre, x in valores.items():
            j = self._idx[nombre]
            buf[i + j] = x if math.isfinite(x) else NAN
        return buf.tobytes()


def leer_fotograma(datos: bytes) -> dict:
    """El fotograma binario como dict (lo usan los tests y los scripts; el visor lo lee igual)."""
    a = np.frombuffer(datos, dtype="<f4")
    nc, np_, nj, nb, ns = (int(x) for x in a[3:CABECERA])
    i = CABECERA
    cuerpos = a[i: i + 7 * nc].reshape(nc, 7)
    i += 7 * nc
    productos = a[i: i + 7 * np_].reshape(np_, 7)
    i += 7 * np_
    juntas = a[i: i + nj]
    i += nj
    bandas = a[i: i + nb]
    i += nb
    return {"formato": int(a[0]), "t": float(a[1]), "factor": float(a[2]), "cuerpos": cuerpos,
            "productos": productos, "juntas": juntas, "bandas": bandas, "senales": a[i: i + ns]}
