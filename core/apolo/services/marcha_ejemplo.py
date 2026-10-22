"""La marcha de EJEMPLO de un transportador para el video (plan fabrica-de-publicaciones, ajuste
D10: «una faja moviéndose sin cajas no parece que se mueva»).

`armar(doc)` arma, con lo que el documento ya declara, la petición de la dinámica (la misma que
recibe la tool `simulate` y que el guion lleva en `marcha.escenario`) para que el video muestre
la máquina ANDANDO CON PRODUCTO: cajas que entran por la cola, viajan sobre la banda y caen en
la descarga. Reutiliza lo que la dinámica ya sabe detectar, sin inventar otra detección:

- **la banda**: la de cada `create_belt_conveyor` (`physics.banda.detectar_bandas`, con su junta
  virtual si el tambor no tiene una) y la hecha a mano con rol «Banda» (`cosim_bandas._es_banda`)
  cuando hay UNA junta de giro motriz para declararla en `bandas` (la de nombre «motriz», o la
  única de giro). El tramo superior y su marcha salen de `physics.banda.superficie_banda`;
- **el sentido**: de la cola al tambor motriz (la descarga va en la cabeza motriz);
- **el producto**: los requisitos (`largo/ancho/alto_paquete_mm`, `peso_paquete_kg`,
  `paquetes_por_minuto`) y, lo que falte, una caja de cartón de 300 × 300 × 200 mm y 5 kg;
- **la velocidad**: `velocidad_m_s` de los requisitos, o 0,3 m/s.

Las cajas ya van repartidas sobre la primera mitad de la banda desde el primer cuadro (el
movimiento se lee de entrada) y una alimentación en serie sigue entrando por la cola. La parte
del video (`duracion_s`) crece con el largo de la banda y baja con la velocidad: lo que tarda en
llegar a la descarga la caja más adelantada, entre 8 y 20 s; la simulación dura además lo que
la máquina sigue andando después (la órbita final, `extra_s`).

`probar(doc, escenario)` corre esa simulación en proceso (prepare + simulate de la dinámica) y
exige que algo avance: si no, `SinMarcha` con el porqué. Una máquina que no es un transportador
(o un transportador de rodillos sin juntas: sin juntas no hay nada que gire) da `SinMarcha`; el
llamador avisa y el video sale sin marcha. El llamador sostiene el documento (sin locks aquí).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Caja de cartón de ejemplo (mm) y su peso (kg) cuando los requisitos no dicen el producto.
PRODUCTO_DEFECTO = (300.0, 300.0, 200.0)
MASA_DEFECTO_KG = 5.0
VELOCIDAD_DEFECTO_M_S = 0.3
#: Duración de la parte «la máquina andando» (s): la caja más adelantada llega a la descarga.
MARCHA_MIN_S, MARCHA_MAX_S = 8.0, 20.0
#: Las cajas iniciales ocupan hasta esta fracción de la banda (desde la cola).
TRAMO_INICIAL = 0.55
#: Cajas a la vista a la vez, como mucho (el paso sale del largo de la banda).
A_LA_VISTA = 4.5
PASO_MAX_MM = 1500.0
HUECO_MIN_MM = 150.0
MARGEN_COLA_MM = 60.0
#: Tope de cajas por banda (la dinámica admite 200 en total).
MAX_POR_BANDA = 40
DURACION_MAX_S = 60.0


class SinMarcha(Exception):
    """No hay marcha de ejemplo: el mensaje dice por qué y qué hacer."""


class MarchaInfiel(Exception):
    """La máquina andando NO es fiel al modelo (ajuste D13c): la cinta que dibuja el visor
    atraviesa una pieza o se aparta del sólido de la banda. El mensaje dice cuál y cuánto. No es
    una `SinMarcha`: quien publica no puede seguir en silencio sin ella."""


@dataclass
class Marcha:
    """La marcha armada: `escenario` (la petición de la dinámica), `duracion_s` (la parte del
    video) y lo que se asumió, para avisarlo."""

    escenario: dict
    duracion_s: float
    resumen: str
    asumido: list = field(default_factory=list)


@dataclass
class _Banda:
    pieza: str
    junta: dict
    declarar: bool  # hecha a mano: va en `bandas` de la petición
    datos: object = None  # BandaDatos


def _texto(doc, j: dict) -> str:
    hijo = doc.scene.get(j["child"])
    return f"{j['name']} {getattr(hijo, 'name', '') or ''}".lower()


def _junta_motriz(doc) -> dict | None:
    """La junta de giro que mueve una banda hecha a mano: la que dice «motriz» (en su nombre o en
    el de su pieza), o la única de giro. Varias sin «motriz» = no se adivina."""
    giros = [j for j in doc.joints.values() if j["type"] in ("giratoria", "continua")]
    motrices = [j for j in giros if "motriz" in _texto(doc, j)]
    if len(motrices) == 1:
        return motrices[0]
    return giros[0] if len(giros) == 1 else None


def bandas(doc) -> tuple[list[_Banda], list[str]]:
    """Las bandas que la dinámica puede mover, con su junta motriz, y por qué quedó fuera cada
    banda que no (avisos)."""
    from apolo.physics.banda import detectar_bandas
    from apolo.services.cosim_bandas import _es_banda

    escena = {f: x for f, x in doc.scene.items() if not getattr(x, "is_guide", False)}
    auto, virtuales, avisos = detectar_bandas(escena, doc.joints, [], True)
    todas = {**doc.joints, **virtuales}
    out = [_Banda(b[0], todas[b[1]], declarar=False) for b in auto]
    tomadas = {b.pieza for b in out}
    a_mano = [f for f, x in escena.items() if f not in tomadas and _es_banda(f, x)]
    if a_mano:
        junta = _junta_motriz(doc)
        if junta is None:
            avisos.append(f"La banda {', '.join(sorted(a_mano))} no tiene una junta de giro "
                          "motriz que la mueva (una junta continua del tambor o eje motriz, con "
                          "«motriz» en el nombre)")
        else:  # una junta mueve una banda: la más larga
            larga = max(a_mano, key=lambda f: _largo(escena[f]))
            out.append(_Banda(larga, junta, declarar=True))
    return out, avisos


def _largo(feat) -> float:
    try:
        bb = feat.shape.bounding_box()
    except Exception:  # noqa: BLE001 — sin bbox no compite
        return 0.0
    return max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y)


def _superficie(doc, b: _Banda):
    """BandaDatos del tramo superior (OCCT: casco de la banda), con la cola del super-comando
    como en `prepare_dynamics`."""
    from apolo.physics.banda import superficie_banda

    cola = None
    if b.pieza.endswith("_banda"):
        tc = doc.scene.get(f"{b.pieza[: -len('_banda')]}_tambor_cola")
        ancla = (getattr(tc, "anchors", None) or {}).get("eje_cola") if tc is not None else None
        if ancla:
            cola = ancla["origin"]
    return superficie_banda(doc.scene[b.pieza], b.junta, None, None, 0.6, 0.33, "ejemplo",
                            cola=cola)


def _producto(req: dict) -> tuple[tuple, float, list[str]]:
    """(dims (largo, ancho, alto) mm, masa kg, asumido) de los requisitos o de la caja de ejemplo."""
    asumido = []
    dims = []
    for clave, defecto in zip(("largo_paquete_mm", "ancho_paquete_mm", "alto_paquete_mm"),
                              PRODUCTO_DEFECTO):
        v = req.get(clave)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            dims.append(float(v))
        else:
            dims.append(defecto)
            asumido.append(clave)
    masa = req.get("peso_paquete_kg")
    if not (isinstance(masa, (int, float)) and not isinstance(masa, bool) and masa > 0):
        masa = MASA_DEFECTO_KG
        asumido.append("peso_paquete_kg")
    return tuple(dims), float(masa), asumido


def _num(req: dict, clave: str) -> float | None:
    v = req.get(clave)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def duracion_marcha(largo_mm: float, v_m_s: float) -> float:
    """Lo que tarda la caja más adelantada en llegar a la descarga (+ 2 s para verla caer),
    entre `MARCHA_MIN_S` y `MARCHA_MAX_S`: crece con el largo y baja con la velocidad."""
    t = TRAMO_INICIAL * largo_mm / 1000.0 / max(v_m_s, 1e-3) + 2.0
    return float(min(MARCHA_MAX_S, max(MARCHA_MIN_S, math.ceil(t))))


def _cajas(b: _Banda, k_banda: int, dims, masa, v, ppm, duracion_s, asumido) -> list[dict]:
    """Las cajas de una banda: repartidas sobre su primer tramo + la alimentación por la cola."""
    import numpy as np

    s = b.datos
    centro = np.asarray(s.centro, float) * 1000.0
    d, n = _sentido(b), np.asarray(s.n, float)
    largo, ancho_banda = 2000.0 * s.medio[0], 2000.0 * s.medio[1]
    lc, ac, hc = dims
    if ac > 0.9 * ancho_banda:
        asumido.append(f"ancho del producto recortado a {0.9 * ancho_banda:.0f} mm (la banda "
                       f"mide {ancho_banda:.0f})")
        ac = 0.9 * ancho_banda
    lc = min(lc, 0.3 * largo)
    paso = max(lc + HUECO_MIN_MM, min(largo / A_LA_VISTA, PASO_MAX_MM))
    if ppm:
        paso = max(paso, v * 1000.0 * 60.0 / ppm)  # el ritmo pedido, sin solapar cajas
    alto = 1000.0 * s.medio[2] + hc / 2 + 2.0 + lc / 2 * abs(float(d[2]))
    giro = math.degrees(math.atan2(float(d[1]), float(d[0])))

    def en(x_mm: float) -> list[float]:
        p = centro + (-largo / 2 + MARGEN_COLA_MM + lc / 2 + x_mm) * d + alto * n
        return [round(float(c), 1) for c in p]

    base = {"dims_mm": [round(lc, 1), round(ac, 1), round(hc, 1)], "masa_kg": masa,
            "rotacion_deg": [0.0, 0.0, round(giro, 2)]}
    cajas = []
    x = 0.0
    while x <= TRAMO_INICIAL * largo - lc and len(cajas) < MAX_POR_BANDA // 2:
        cajas.append({"nombre": f"caja_{k_banda}_{len(cajas)}", "posicion_mm": en(x), **base})
        x += paso
    cada = paso / 1000.0 / v
    cantidad = int(min(MAX_POR_BANDA - len(cajas), max(1, math.floor((duracion_s - cada) / cada) + 1)))
    if cada <= duracion_s:
        cajas.append({"nombre": f"cola_{k_banda}", "posicion_mm": en(0.0), "cada_s": round(cada, 3),
                      "desde_s": round(cada, 3), "cantidad": cantidad, **base})
    return cajas


def armar(doc, *, extra_s: float = 14.0) -> Marcha:
    """La marcha de ejemplo del transportador del documento (regenerado). `extra_s`: lo que la
    máquina sigue andando en el video después de su parte (la simulación dura `duracion_s +
    extra_s`, ≤ 60 s). `SinMarcha` si no hay banda que mover."""
    from apolo.physics.sim import PhysicsError

    encontradas, avisos = bandas(doc)
    if not encontradas:
        motivo = "; ".join(avisos) if avisos else (
            "no hay una banda transportadora que la dinámica sepa mover (la de create_belt_conveyor, "
            "o una pieza «Banda» con la junta de giro de su tambor motriz). Un transportador de "
            "rodillos sin juntas no tiene nada que gire")
        raise SinMarcha(motivo)
    req = doc.requirements or {}
    dims, masa, asumido = _producto(req)
    v = _num(req, "velocidad_m_s")
    if v is None:
        v = VELOCIDAD_DEFECTO_M_S
        asumido.append("velocidad_m_s")
    ppm = _num(req, "paquetes_por_minuto")
    for b in encontradas:
        try:
            b.datos = _superficie(doc, b)
        except PhysicsError as exc:
            raise SinMarcha(str(exc)) from None
    largo_max = max(2000.0 * b.datos.medio[0] for b in encontradas)
    duracion = duracion_marcha(largo_max, v)
    total_s = min(DURACION_MAX_S, duracion + max(0.0, float(extra_s)))
    motores, declaradas, productos = [], [], []
    for k, b in enumerate(encontradas):
        hacia = [round(float(c), 4) for c in _sentido(b)]
        motores.append({"junta": b.junta["name"], "modo": "velocidad", "v_superficie_m_s": v,
                        "direccion_transporte": hacia})
        if b.declarar:
            declaradas.append({"pieza": b.pieza, "junta_motriz": b.junta["name"],
                               "direccion_transporte": hacia})
        productos += _cajas(b, k, dims, masa, v, ppm, total_s, asumido)
    escenario = {"duracion_s": round(total_s, 2), "motores": motores, "productos": productos}
    if declaradas:
        escenario["bandas"] = declaradas
    lc, ac, hc = dims
    resumen = (f"{len(encontradas)} banda(s) a {v:g} m/s con cajas de {lc:g} × {ac:g} × {hc:g} mm "
               f"y {masa:g} kg; {duracion:g} s de marcha en el video")
    return Marcha(escenario=escenario, duracion_s=duracion, resumen=resumen,
                  asumido=list(dict.fromkeys(asumido)))


def _sentido(b: _Banda):
    """La marcha del tramo superior, de la cola hacia la cabeza motriz (la descarga)."""
    import numpy as np

    d = np.asarray(b.datos.d, float)
    hacia = np.asarray(b.junta["origin"], float) - np.asarray(b.datos.centro, float) * 1000.0
    return d if float(hacia @ d) >= 0 else -d


def fidelidad(doc, bandas: list[dict], res: dict) -> list[dict]:
    """La prueba D13b de cada faja animada (`library/fidelidad_faja.py`), con lo mismo que usa
    la marcha del visor: `bandas` = `marcha_visual.bandas_de_snap(snap)` y `res` el resultado de
    `simulate_dynamics`. Devuelve [{pieza, origen, desvio_mm}]; `MarchaInfiel` si alguna falla."""
    from apolo.library.marcha_visual import armar
    from apolo.services.marcha_visual import extraer_marcha_visual

    return _veredicto_fidelidad(armar(extraer_marcha_visual(doc, bandas), res)["fajas"])


def _veredicto_fidelidad(fajas: list[dict]) -> list[dict]:
    malas = [f for f in fajas if not f["fidelidad"]["ok"]]
    if malas:
        raise MarchaInfiel("; ".join(f"la banda «{f['pieza']}» {f['fidelidad']['motivo']}"
                                     for f in malas))
    return [{"pieza": f["pieza"], "origen": f["modelo"],
             "desvio_mm": (f["fidelidad"]["desvio"] or {}).get("desvio_mm")} for f in fajas]


def preparar_prueba(doc, escenario: dict):
    """Fase OCCT de `probar` (bajo el `STATE_LOCK` de quien lo tenga): el snapshot de la dinámica
    y lo que dibujará el visor (`marcha_visual.extraer_marcha_visual`, la misma adquisición que
    usa la serie del visor). Devuelve (snap, visual); `SinMarcha` si no hay nada que simular."""
    from apolo.physics.dinamica import prepare_dynamics
    from apolo.physics.sim import PhysicsError
    from apolo.services.marcha_visual import bandas_de_snap, extraer_marcha_visual

    try:
        snap = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, escenario,
                                mates=doc.mates)
    except PhysicsError as exc:
        raise SinMarcha(f"la simulación falló: {exc}") from None
    if snap.early is not None:
        raise SinMarcha(snap.early.get("mensaje") or "nada que simular")
    return snap, extraer_marcha_visual(doc, bandas_de_snap(snap))


def simular_prueba(snap) -> dict:
    """La dinámica del snapshot, sin el documento (fuera del `STATE_LOCK`; quien la corra en la API
    toma `PHYSICS_LOCK`). `SinMarcha` si la simulación falla."""
    from apolo.physics.dinamica import simulate_dynamics
    from apolo.physics.sim import PhysicsError

    try:
        return simulate_dynamics(snap)
    except PhysicsError as exc:
        raise SinMarcha(f"la simulación falló: {exc}") from None


def probar(doc, escenario: dict, *, minimo_mm: float | None = 200.0) -> dict:
    """Corre la dinámica de `escenario` sobre `doc` (en proceso, sin locks: el documento es del
    llamador) y exige que algún producto AVANCE al menos `minimo_mm` (None: sólo que simule, para
    un escenario escrito a mano). Devuelve {segundos, avance_mm, productos, avisos, fidelidad};
    `SinMarcha` con el porqué si falla o nada avanza, y `MarchaInfiel` si la faja que dibujará
    el visor no es fiel al modelo (`fidelidad`, ajuste D13). Las tres fases (`preparar_prueba`,
    `simular_prueba`, `concluir_prueba`) las corre por separado la puerta de publicación, con los
    locks de la API."""
    import time

    t = time.perf_counter()
    snap, visual = preparar_prueba(doc, escenario)
    return concluir_prueba(visual, simular_prueba(snap), minimo_mm=minimo_mm, desde=t)


def concluir_prueba(visual: dict, res: dict, *, minimo_mm: float | None = 200.0,
                    desde: float | None = None) -> dict:
    """Puro (lo extraído y el resultado de la simulación): el avance de los productos y la fidelidad de
    la faja animada (D13b). Ver `probar`."""
    import time

    import numpy as np

    from apolo.library.marcha_visual import armar as armar_visual

    t = time.perf_counter() if desde is None else desde
    inicio = {p["name"]: np.array([p["x"], p["y"], p["z"]], float) for p in res["productos"]}
    finales = res["resumen"]["productos"]
    avance = 0.0
    for nombre, r in finales.items():
        if nombre in inicio:
            delta = np.asarray(r["posicion_final_mm"], float) - inicio[nombre]
            avance = max(avance, float(np.hypot(delta[0], delta[1])))
    if minimo_mm is not None and not finales:
        raise SinMarcha("ningún producto entró a la simulación")
    if minimo_mm is not None and avance < minimo_mm:
        raise SinMarcha(f"los productos no avanzan sobre la banda (el que más, {avance:.0f} mm); "
                        "revisa la junta motriz y la banda")
    fiel = _veredicto_fidelidad(armar_visual(visual, res)["fajas"])
    return {"segundos": round(time.perf_counter() - t, 1), "avance_mm": round(avance),
            "productos": len(finales), "avisos": list(res.get("avisos") or []), "fidelidad": fiel}
