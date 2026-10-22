"""Insumos de la PUERTA DE PUBLICACIÓN (plan puerta-de-publicacion, F1): lee el documento y reúne,
como datos puros, todo lo que evalúa el registro (`library/calidad/registro.py`). El llamador
sostiene STATE_LOCK; lo lento (la gravedad y la simulación de la marcha) lo corre la API FUERA del
lock con el suyo (patrón dos locks): aquí sólo `preparar_marcha` (OCCT) y `concluir_marcha` (puro).

`reunir(doc, expand=, gravedad=)` arma:
- `hechos`: los ELEMENTOS detectados por tipo general (`puerta_hechos.py`, D14) y las familias
  de función (D15): lo que decide `aplica_si`;
- `fabricacion`: cada pieza de catálogo o sólido con material y proceso; `funciones`: el metadato
  declarado (D15);
- `entrega`: la puerta de entrega (`library/delivery`) con la gravedad que corrió la API, y sus
  insumos crudos de acceso de herramienta, ERC y escenarios;
- `interna`: los choques DENTRO de cada super-comando, sin `same_command_pairs` (D13b);
- `memoria`: el veredicto de la memoria de cálculo sin el PDF;
- `fuentes`: los ítems de cada `Fuente` del registro (F2 hoy; F3 con una línea allá);
- `firma`: `firma_modelo` del documento (la misma que calcula la publicación del `.apolo`).
"""

from __future__ import annotations

import importlib
import time
from contextlib import contextmanager


@contextmanager
def _cronometro(tiempos: dict, clave: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        tiempos[clave] = round(tiempos.get(clave, 0.0) + time.perf_counter() - t0, 2)


#: Lo del manifest que decide la puerta (además del log): visibilidad (la interferencia mira lo
#: visible), materiales y vertical (masa, material), estudios (poses), requisitos (cargas),
#: FEA, cadenas de cotas, escenarios, tensores y funciones declarados (D15). Colores, nombres y
#: notas no cuentan.
CLAVES_FIRMA = {"hidden": [], "materials": {}, "vertical": "metalmecanica", "motion": {},
                "requirements": {}, "fea": {}, "stackups": {}, "escenarios": {}, "tensores": [],
                "funciones": []}


def firma_modelo(commands: list, manifest: dict) -> str:
    """La huella del modelo que la puerta evaluó: el log + lo de `CLAVES_FIRMA` del manifest. Pura:
    la calcula este servicio (de un `Document`, `firma`) y la publicación (del `.apolo`, sin
    regenerarlo): la misma función."""
    import hashlib
    import json

    datos = [commands, {k: manifest.get(k, defecto) for k, defecto in CLAVES_FIRMA.items()}]
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=str).encode()).hexdigest()[:20]


def firma(doc) -> str:
    """`firma_modelo` con lo que el `.apolo` de este documento guardaría."""
    manifest = {"hidden": sorted(doc.hidden), "materials": doc.materials,
                "vertical": doc.vertical, "motion": doc.motion,
                "requirements": doc.requirements, "fea": doc.fea, "stackups": doc.stackups,
                "escenarios": doc.escenarios, "tensores": getattr(doc, "tensores", None) or [],
                "funciones": getattr(doc, "funciones", None) or []}
    return firma_modelo(doc.commands, manifest)


def poner_funciones(doc, valor) -> list[dict]:
    """Reemplaza el metadato `doc.funciones` (D15: la solución declarada por función; manifest,
    fuera del log). Valida forma y piezas antes de tocar nada; `ServiceError(400)` con la
    corrección."""
    from apolo.library.calidad.funciones import validar_funciones

    from .errors import ServiceError

    try:
        limpio = validar_funciones(valor)
    except ValueError as exc:
        raise ServiceError(400, str(exc)) from exc
    faltan = sorted({p for f in limpio for p in f["piezas"] if p not in doc.scene})
    if faltan:
        raise ServiceError(400, f"funciones: pieza(s) inexistente(s) {', '.join(faltan)}")
    doc.funciones = limpio
    return doc.funciones


def interferencia_interna(doc) -> dict:
    """Los choques entre piezas de un MISMO comando (lo que la puerta de entrega excluye con
    `same_command_pairs`, D13b del plan), con sus exclusiones de lo DECLARADO: juntas, `fasten`,
    herraje y tornillería asentados. Un solape ≤ `EXCESS_TOL_MM3` es un asiento: se tolera y se
    declara. Revisa TODAS las parejas candidatas (pagina, sin recorte)."""
    from apolo.library import interference_report
    from apolo.library.checks import EXCESS_TOL_MM3, hardware_ids, joint_pairs

    from .delivery_inputs import exclusiones_declaradas

    fasten_pairs, bolt_ids = exclusiones_declaradas(doc)
    excl_pares, excl_ids = joint_pairs(doc) | fasten_pairs, hardware_ids(doc) | bolt_ids
    por_cmd: dict[str, list[str]] = {}
    for fid, f in doc.scene.items():
        por_cmd.setdefault(f.command_id, []).append(fid)
    grupos = {c: fids for c, fids in por_cmd.items() if len(fids) >= 2}
    choques, tolerados = [], []
    for cmd, fids in grupos.items():
        desde = 0
        while True:
            rep = interference_report(doc.scene, only=fids, exclude_pairs=excl_pares,
                                      exclude_ids=excl_ids, desde=desde)
            for c in rep["interferencias"]:
                (tolerados if c["volumen_mm3"] <= EXCESS_TOL_MM3 else choques).append(
                    {"comando": cmd, **c})
            if not rep["truncado"]:
                break
            desde = rep["desde_siguiente"]
    choques.sort(key=lambda c: -c["volumen_mm3"])
    return {"comandos": len(grupos), "choques": choques, "tolerados": tolerados,
            "tolerancia_mm3": EXCESS_TOL_MM3}


def items_de_fuentes(doc, registro=None) -> dict:
    """{clave: [ítems como dict]} de cada `Fuente` del registro, o {clave: {"error"}} si no corre."""
    from apolo.library.calidad.item import Item
    from apolo.library.calidad.registro import fuentes

    out: dict = {}
    for f in fuentes(registro):
        modulo, nombre = f.servicio.split(":")
        try:
            items = getattr(importlib.import_module(modulo), nombre)(doc)
            out[f.clave] = [i.to_dict() if isinstance(i, Item) else dict(i) for i in items]
        except Exception as exc:  # noqa: BLE001 — una fuente que no corre: SIN_EVALUAR
            out[f.clave] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def reunir(doc, *, expand, gravedad: dict, registro=None, tiempos: dict | None = None) -> dict:
    """Los insumos del registro, salvo la marcha. `gravedad` = {"resultado": dict | None,
    "motivo"}: la simulación que la API corrió con su lock (None = no corrió → SIN_EVALUAR)."""
    from apolo.library.delivery import delivery_report

    from .delivery_inputs import delivery_inputs
    from .memoria_reglas import veredicto_memoria
    from .puerta_hechos import fabricacion, hechos

    tiempos = {} if tiempos is None else tiempos
    por_regla: dict = {}
    with _cronometro(tiempos, "entrega"):
        kw = delivery_inputs(doc, expand=expand, tiempos=por_regla)
        entrega = delivery_report(**kw, gravedad=gravedad.get("resultado"))
    tiempos.update({f"entrega.{k}": v for k, v in por_regla.items()})
    with _cronometro(tiempos, "hechos"):
        h = hechos(doc, kw)
    with _cronometro(tiempos, "interferencia_interna"):
        interna = interferencia_interna(doc)
    with _cronometro(tiempos, "memoria"):
        try:
            memoria = veredicto_memoria(doc)
        except Exception as exc:  # noqa: BLE001 — sin memoria: SIN_EVALUAR
            memoria = {"error": f"{type(exc).__name__}: {exc}"}
    with _cronometro(tiempos, "fuentes"):
        fuentes = items_de_fuentes(doc, registro)
    with _cronometro(tiempos, "fabricabilidad"):
        fab = fabricacion(doc)
    return {"firma": firma(doc), "hechos": h, "entrega": entrega, "gravedad": gravedad,
            "acceso": kw.get("acceso_herramienta"), "electrico": kw.get("electrico"),
            "escenarios": kw.get("escenarios"), "interna": interna, "memoria": memoria,
            "fuentes": fuentes, "fabricacion": fab,
            "funciones": list(getattr(doc, "funciones", None) or []), "tiempos": tiempos}


# ------------------------------------------------------------------ la marcha (D13 de la fábrica)
def preparar_marcha(doc) -> dict:
    """Fase OCCT (bajo STATE_LOCK): la marcha automática de `marcha_ejemplo.armar` lista para
    simular → {"snap", "visual", "resumen"}; o {"resultado": "sin_marcha", "detalle"} si no se
    puede armar (sin banda con junta motriz, el registro dirá NO_APLICA por sus hechos)."""
    from . import marcha_ejemplo as me

    try:
        m = me.armar(doc)
        snap, visual = me.preparar_prueba(doc, m.escenario)
    except me.SinMarcha as exc:
        return {"resultado": "sin_marcha", "detalle": str(exc)}
    return {"snap": snap, "visual": visual, "resumen": m.resumen}


def concluir_marcha(prep: dict, res: dict | None, error: str | None = None,
                    desde: float | None = None) -> dict:
    """Puro: el insumo `marcha` del registro, del resultado de la simulación (que la API corrió
    fuera del STATE_LOCK). `MarchaInfiel` → «infiel» (FALLA); lo demás que impide verla →
    «sin_marcha» (SIN_EVALUAR)."""
    from . import marcha_ejemplo as me

    if "resultado" in prep:
        return {k: v for k, v in prep.items() if k in ("resultado", "detalle")}
    if res is None:
        return {"resultado": "sin_marcha", "detalle": error or "la simulación no corrió"}
    try:
        r = me.concluir_prueba(prep["visual"], res, minimo_mm=200.0, desde=desde)
    except me.MarchaInfiel as exc:
        return {"resultado": "infiel", "detalle": str(exc)}
    except me.SinMarcha as exc:
        return {"resultado": "sin_marcha", "detalle": str(exc)}
    return {"resultado": "ok", "resumen": prep.get("resumen"), **r}
