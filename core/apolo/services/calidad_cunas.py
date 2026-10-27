"""El sentido de marcha de cada banda y dónde la banda LLEGA a cada tambor, para que la puerta de
publicación resguarde sólo la cuña de ENTRADA (plan puerta-sin-sobrediseno, D3–D4).

- `sentido_de_bandas(doc, bandas)`: el sentido de transporte de cada banda, en este orden (D3):
  (a) un escenario de prueba que lo declara (`mecanica.bandas[].direccion_transporte` de la
  pieza; dos escenarios que se contradicen = desconocido), (b) el requisito `sentido_transporte`
  y (c) la plantilla `create_belt_conveyor`, que transporta de la cola al motriz por construcción
  (el vector sale de los centros de SUS dos tambores en la escena: sigue a un giro o un traslado
  posterior). `reversible` (requisito) o ninguna fuente → sin sentido: las dos cuñas. Nunca se
  infiere del nombre ni del signo de la junta.
- `llegadas(doc, an)`: por cada peligro de cuña con sentido conocido, el punto 3D donde la banda
  llega a su tambor en la línea media del lazo (`library/seguridad/cuna_entrada.py`): la sección
  del sólido de la banda en el plano ⟂ al eje de los tambores por el centro de su ancho, como
  `services/marcha_visual` (OCCT en `seccion_plano.py`).

Lee shapes: el llamador sostiene `STATE_LOCK`. Sin el sentido o sin lazo, el peligro conserva las
dos cuñas y su evidencia dice por qué.
"""

from __future__ import annotations

import math

DESCONOCIDO = "desconocido: las dos cuñas"


def _unit3(v) -> list[float] | None:
    try:
        c = [float(x) for x in v]
    except (TypeError, ValueError):
        return None
    n = math.sqrt(sum(x * x for x in c)) if len(c) == 3 else 0.0
    return [x / n for x in c] if n > 1e-9 and math.isfinite(n) else None


def _de_escenarios(doc, banda: str) -> dict | None:
    vistos = []
    for nombre in sorted(getattr(doc, "escenarios", None) or {}):
        esc = (doc.escenarios[nombre] or {}).get("escenario") or {}
        mec = esc.get("mecanica") if isinstance(esc, dict) else None
        for b in (mec or {}).get("bandas") or []:
            if isinstance(b, dict) and b.get("pieza") == banda and \
                    (v := _unit3(b.get("direccion_transporte") or ())) is not None:
                vistos.append((nombre, v))
    if not vistos:
        return None
    n0, v0 = vistos[0]
    otros = [n for n, v in vistos if sum(a * b for a, b in zip(v, v0)) < 0.999]
    if otros:
        return {"vector": None, "fuente": f"los escenarios «{n0}» y «{otros[0]}» declaran sentidos "
                                          f"distintos: las dos cuñas"}
    return {"vector": v0, "fuente": f"escenario «{n0}»"}


def _de_requisito(req: dict) -> dict | None:
    from apolo.library.requisitos import SENTIDO, vector_sentido

    if req.get(SENTIDO) in (None, ""):
        return None
    try:  # la carga no valida: un manifest puede traer cualquier cosa
        return {"vector": vector_sentido(req[SENTIDO]), "fuente": f"requisito {SENTIDO}"}
    except ValueError:
        return {"vector": None, "fuente": f"requisito {SENTIDO} mal formado: las dos cuñas"}


def _centro(doc, fid: str):
    f = doc.scene.get(fid)
    if f is None or f.shape is None:
        return None
    bb = f.shape.bounding_box()
    return [(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2]


def _de_plantilla(doc, banda: str) -> dict | None:
    f = doc.scene.get(banda)
    cmd = getattr(f, "command_id", None)
    if cmd is None or f"{cmd}_banda" != banda:
        return None
    tipo = next((c.get("type") for c in doc.commands if c.get("id") == cmd), None)
    if tipo != "create_belt_conveyor":
        return None
    a, b = _centro(doc, f"{cmd}_tambor_cola"), _centro(doc, f"{cmd}_tambor_motriz")
    v = _unit3([b[i] - a[i] for i in range(3)]) if a is not None and b is not None else None
    if v is None:
        return None
    return {"vector": [round(c, 6) + 0.0 for c in v],
            "fuente": f"plantilla create_belt_conveyor ({cmd}): de la cola al motriz"}


def sentido_de_bandas(doc, bandas) -> dict[str, dict]:
    """{banda: {vector: [x, y, z] unitario | None, fuente: texto}} (orden de fuentes: docstring)."""
    from apolo.library.requisitos import REVERSIBLE

    req = doc.requirements or {}
    if req.get(REVERSIBLE) is True or str(req.get(REVERSIBLE)).strip().lower() in ("si", "sí", "true"):
        return {b: {"vector": None, "fuente": "reversible (requisito): las dos cuñas"} for b in bandas}
    return {b: (_de_escenarios(doc, b) or _de_requisito(req) or _de_plantilla(doc, b)
                or {"vector": None, "fuente": DESCONOCIDO}) for b in bandas}


def _seccion(doc, banda: str, eje: int, caja) -> dict | None:
    """{media, espesor, origen, u, w} de la línea media del lazo de la banda en el plano ⟂ al
    `eje` por el centro de su ancho (u = eje mundial siguiente, w = v × u), o None."""
    from apolo.kernel.shapes import place_matrix
    from apolo.library.ruta_faja_modelo import linea_media

    from .seccion_plano import cortar, lazo_de_banda

    f = doc.scene.get(banda)
    if f is None or f.shape is None:
        return None
    i = next(k for k in range(3) if k != eje)
    u = [1.0 if k == i else 0.0 for k in range(3)]
    v = [1.0 if k == eje else 0.0 for k in range(3)]
    w = [v[1] * u[2] - v[2] * u[1], v[2] * u[0] - v[0] * u[2], v[0] * u[1] - v[1] * u[0]]
    origen = [(caja[0][k] + caja[1][k]) / 2.0 for k in range(3)]

    def fila(e):
        return [*e, -sum(e[k] * origen[k] for k in range(3))]

    inv = [fila(u), fila(w), fila(v), [0, 0, 0, 1]]
    try:
        lazo = lazo_de_banda(cortar(place_matrix(f.shape, inv), 0.0))
    except Exception:  # noqa: BLE001 — una banda que OCCT no corta queda con las dos cuñas
        return None
    if lazo is None:
        return None
    media, t = linea_media(lazo["ext"], lazo["huecos"])
    if len(media) < 3:
        return None
    return {"media": media, "espesor": t, "origen": origen, "u": u, "w": w}


def _plano(s: dict, p) -> list[float]:
    return [sum((p[k] - s["origen"][k]) * s[e][k] for k in range(3)) for e in ("u", "w")]


def llegadas(doc, an: dict) -> dict[str, dict]:
    """{id de peligro de cuña: {hacia: (x, y, z) | None, sentido: texto}} para la puerta: con
    `hacia`, `calidad_sondas.cunas` toma sólo la cuña de entrada. Una sección por banda y eje."""
    from apolo.library.seguridad.cuna_entrada import lazo_en_marcha, llegada

    piezas = an["dc"]["piezas"]
    peligros = [p for p in an["peligros"] if p.get("cuna")]
    if not peligros:
        return {}
    sentidos = sentido_de_bandas(doc, sorted({p["cuna"]["banda"] for p in peligros}))
    secciones: dict = {}
    out = {}
    for p in peligros:
        b, t = p["cuna"]["banda"], p["cuna"]["tambor"]
        s = sentidos[b]
        if s["vector"] is None:
            out[p["id"]] = {"hacia": None, "sentido": s["fuente"]}
            continue
        red = piezas[t].redondo
        clave = (b, red.eje)
        if clave not in secciones:
            secciones[clave] = _seccion(doc, b, red.eje, piezas[b].caja)
        sec = secciones[clave]
        motivo, hacia = "", None
        if sec is None:
            motivo = "la sección de la banda no da un lazo cerrado"
        else:
            lazo, motivo = lazo_en_marcha(sec["media"], _plano({**sec, "origen": [0, 0, 0]},
                                                               s["vector"]),
                                          _plano({**sec, "origen": [0, 0, 0]}, (0.0, 0.0, 1.0)))
            if lazo is not None:
                q = llegada(lazo, _plano(sec, red.centro), red.radio, sec["espesor"])
                if q is None:
                    motivo = "la línea media del lazo no muestra dónde llega al tambor"
                else:
                    hacia = tuple(float(sec["origen"][k] + q[0] * sec["u"][k] + q[1] * sec["w"][k])
                                  for k in range(3))
        out[p["id"]] = ({"hacia": hacia, "sentido": f"cuña de entrada; sentido: {s['fuente']}"}
                        if hacia is not None else
                        {"hacia": None, "sentido": f"las dos cuñas: {motivo} (sentido: {s['fuente']})"})
    return out
