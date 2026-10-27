"""Lo que VE la persona de las pruebas de la máquina (panel «Pruebas», plan visor-para-evaluar
D1–D4): cada escenario guardado con su estado en semáforo, la fecha, el balance de producto y,
al abrir uno, lo que falló con su cifra y el producto trabado o perdido con su lugar y su hora.

Es la misma lectura que `escenarios.listar` (el estado y su vigencia salen de ahí: ninguna regla
propia) puesta en palabras para la persona. Lee `doc` explícito, sin locks (el llamador sostiene
`STATE_LOCK`) y sin transporte, como el resto de `services`.
"""

from __future__ import annotations

from apolo.cosim.veredicto import FALLA, PASA, SIN_ASERCIONES

from .escenarios import SIN_CORRER, VENCIDO, estado, firma_documento, no_existe
from .errors import ServiceError

# estado → (rótulo, severidad del semáforo de `ui/src/diseno/atencion.ts`)
ESTADOS = {
    PASA: ("Pasa", "bien"),
    FALLA: ("Falla", "falla"),
    VENCIDO: ("Vencido", "aviso"),
    SIN_ASERCIONES: ("Sin aserciones", "aviso"),
    SIN_CORRER: ("Sin correr", "sin_evaluar"),
}
_PESO = {"falla": 0, "aviso": 1, "sin_evaluar": 2, "bien": 3}
# lo que rompe el balance (cosim/flujo.py), con su frase
_INCIDENCIAS = (("trabados", "trabado"), ("perdidos", "cayó al piso"), ("retenidos", "no salió a tiempo"),
                ("sin_entrar", "no pudo entrar"))


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


def resumen(estados: list[str]) -> str:
    """«15 de 16 pasan · 1 vencido» (lo que no pasa, por estado, en el orden de gravedad)."""
    n = len(estados)
    cuenta = {e: estados.count(e) for e in ESTADOS}
    partes = [f"{cuenta[PASA]} de {n} {'pasa' if n == 1 else 'pasan'}"]
    for e, uno, varios in ((FALLA, "falla", "fallan"), (VENCIDO, "vencido", "vencidos"),
                           (SIN_ASERCIONES, "sin aserciones", "sin aserciones"),
                           (SIN_CORRER, "sin correr", "sin correr")):
        if cuenta[e]:
            partes.append(_plural(cuenta[e], uno, varios))
    return " · ".join(partes)


def _estimado_s(res: dict) -> float | None:
    """Cuánto tardó la última corrida en el reloj de pared (duración simulada ÷ factor de tiempo
    real): con eso la persona sabe cuánto esperar al correrla de nuevo."""
    dur, factor = res.get("duracion_s"), res.get("factor_tiempo_real")
    if not dur or not factor:
        return None
    return round(float(dur) / float(factor), 1)


def _fila(doc, nombre: str, firma: str, cache: dict) -> dict:
    ent = doc.escenarios[nombre]
    esc, res = ent["escenario"], ent.get("resultado") or {}
    st = estado(doc, nombre, firma, cache)
    rotulo, severidad = ESTADOS.get(st["estado"], (st["estado"], "aviso"))
    fila = {"nombre": nombre, "estado": st["estado"], "rotulo": rotulo, "severidad": severidad}
    if esc.get("descripcion"):
        fila["descripcion"] = esc["descripcion"]
    if st["estado"] == VENCIDO:
        fila["motivo"] = st.get("motivo")
        if st.get("ultimo") in ESTADOS:
            fila["ultimo"] = ESTADOS[st["ultimo"]][0]
    if res.get("fecha"):
        fila["fecha"] = res["fecha"]
    if (res.get("flujo") or {}).get("balance"):
        fila["balance"] = res["flujo"]["balance"]
    est = _estimado_s(res)
    if est is not None:
        fila["estimado_s"] = est
    n_fallidas = sum(1 for a in res.get("aserciones", []) if not a.get("pasa"))
    if n_fallidas:
        fila["n_fallidas"] = n_fallidas
    return fila


def panel(doc) -> dict:
    """`{veredicto: {severidad, frase}, escenarios: [fila…]}`; sin escenarios, `escenarios: []`.
    La frase del veredicto es el resumen («15 de 16 pasan · 1 vencido») y su severidad, la de la
    peor fila; las filas, lo más grave primero y, a igual estado, en el orden en que se declararon."""
    firma, cache = firma_documento(doc), {}
    filas = [_fila(doc, n, firma, cache) for n in doc.escenarios]
    if not filas:
        return {"veredicto": None, "escenarios": []}
    orden = sorted(range(len(filas)), key=lambda i: (_PESO[filas[i]["severidad"]], i))
    peor = filas[orden[0]]["severidad"]
    return {"veredicto": {"severidad": peor, "frase": resumen([f["estado"] for f in filas])},
            "escenarios": [filas[i] for i in orden]}


def _lugar(doc, punto) -> dict:
    """El lugar de un punto (mm) dicho por la pieza más cercana (`pieza`, `cerca_de`) y su
    coordenada (`punto_mm`): «sobre Banda» se lee mejor que (512, 0, 904) mm."""
    if not punto or len(punto) != 3:
        return {}
    x, y, z = (float(c) for c in punto)
    out: dict = {"punto_mm": [round(x), round(y), round(z)]}
    mejor = None
    for fid, f in doc.scene.items():
        if not getattr(f, "visible", True):
            continue
        try:
            bb = f.shape.bounding_box()
        except Exception:  # noqa: BLE001 — una pieza sin caja no decide el lugar
            continue
        dx = max(bb.min.X - x, 0.0, x - bb.max.X)
        dy = max(bb.min.Y - y, 0.0, y - bb.max.Y)
        dz = max(bb.min.Z - z, 0.0, z - bb.max.Z)
        d = (dx * dx + dy * dy + dz * dz) ** 0.5
        if mejor is None or d < mejor[0]:
            mejor = (d, fid, f.name)
    if mejor is not None and mejor[0] <= 300.0:  # a más de 30 cm, el nombre confunde
        out.update(pieza=mejor[1], cerca_de=mejor[2])
    return out


def _incidencias(doc, flujo: dict) -> list[dict]:
    """El producto que rompió el balance: qué le pasó, dónde y a qué hora (las listas de
    `cosim/flujo.py`, ya recortadas en el resultado guardado; su total en `n_<lista>`)."""
    out = []
    for clave, que in _INCIDENCIAS:
        for it in flujo.get(clave) or []:
            hora = it.get("desde_s", it.get("t", it.get("entro_s", it.get("le_tocaba_s"))))
            out.append({"tipo": clave, "producto": it.get("producto", "?"), "que": que,
                        **({"hora_s": hora} if hora is not None else {}),
                        **_lugar(doc, it.get("pos_mm"))})
        total = flujo.get(f"n_{clave}")
        mostradas = len(flujo.get(clave) or [])
        if isinstance(total, int) and total > mostradas:
            out.append({"tipo": clave, "mas": total - mostradas})
    return out


def detalle(doc, nombre: str) -> dict:
    """Un escenario abierto: su fila, las aserciones que fallaron con su cifra (el `detalle` del
    veredicto: «al final vale 3») y las incidencias del producto. Sin escenario → 404."""
    if nombre not in doc.escenarios:
        raise ServiceError(404, no_existe(doc, nombre))
    fila = _fila(doc, nombre, firma_documento(doc), {})
    res = doc.escenarios[nombre].get("resultado") or {}
    fila["fallidas"] = [{"asercion": a.get("asercion", ""), "cifra": a.get("detalle", "")}
                        for a in res.get("aserciones", []) if not a.get("pasa")]
    fila["incidencias"] = _incidencias(doc, res.get("flujo") or {})
    fila["n_aserciones"] = len(doc.escenarios[nombre]["escenario"].get("aserciones") or [])
    return fila
