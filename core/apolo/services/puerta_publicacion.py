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
  insumos crudos de acceso de herramienta, ERC, escenarios y `nombres` (los aparatos del carril
  con su rótulo DECLARADO, `nombres_aparatos.insumo_puerta`: una sola lectura para la regla de la
  entrega, el detector `operables` y el ítem `interfaz.nombres_por_funcion`);
- `interna`: los choques DENTRO de cada super-comando, sin `same_command_pairs` (D13b);
- `memoria`: el veredicto de la memoria de cálculo sin el PDF;
- `flujo`: el balance de producto al ritmo nominal (`flujo_producto.evaluar`, plan
  balance-de-producto D9);
- `sobrantes`: qué guarda o pieza agregada sobra (`calidad_sobrantes.sobrantes`, sobre el análisis
  y las sondas de la fuente «seguridad»: va después de las fuentes) y `justificadas`, el metadato
  (puerta-sin-sobrediseno D6/D11);
- `fuentes`: lo que da cada `Fuente` del registro (F2: función mecánica; F3: seguridad y
  reparabilidad, con la tabla de riesgos), cada una UNA vez;
- `firma`: `firma_modelo` del documento (la misma que calcula la publicación del `.apolo`).

Un `Contexto` por corrida: lo caro que comparten los detectores de los hechos y las fuentes (la
detección de F3 sobre la extracción OCCT de `calidad_seguridad.datos_calidad`) se calcula una
vez; cada detector usa así el MISMO criterio que el control que lo evalúa, sin pagarlo dos veces.
"""

from __future__ import annotations

import importlib
import time
from contextlib import contextmanager


class Contexto:
    """Memo de UNA corrida de la puerta (vive lo que dura `reunir`; nunca es estado global)."""

    def __init__(self) -> None:
        self._memo: dict = {}

    def una_vez(self, clave: str, calcular):
        """`calcular()` la primera vez que se pide `clave`; después, lo mismo. Si revienta, no se
        guarda (quien lo vuelva a pedir lo verá fallar)."""
        if clave not in self._memo:
            self._memo[clave] = calcular()
        return self._memo[clave]


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
#: notas no cuentan. Los datos de las extensiones (`ext`) cuentan sólo si hay (`firma_modelo`).
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
    if manifest.get("ext"):  # los datos de las extensiones (F1d), sólo si hay: sin ellos, la de siempre
        datos.append({"ext": manifest["ext"]})
    if manifest.get("justificadas"):  # D11 de puerta-sin-sobrediseno, igual: sólo si hay
        datos.append({"justificadas": manifest["justificadas"]})
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=str).encode()).hexdigest()[:20]


def firma(doc) -> str:
    """`firma_modelo` con lo que el `.apolo` de este documento guardaría."""
    manifest = {"hidden": sorted(doc.hidden), "materials": doc.materials,
                "vertical": doc.vertical, "motion": doc.motion,
                "requirements": doc.requirements, "fea": doc.fea, "stackups": doc.stackups,
                "escenarios": doc.escenarios, "tensores": getattr(doc, "tensores", None) or [],
                "funciones": getattr(doc, "funciones", None) or [],
                "ext": getattr(doc, "ext", None) or {},
                "justificadas": getattr(doc, "justificadas", None) or []}
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


MODOS_JUSTIFICADAS = ("reemplazar", "agregar")


def nombres_del_tablero(doc) -> set[str]:
    """Lo que el ERC nombra en `elementos` y no es un id de la escena: designaciones de aparatos
    y cables e ids de conductores y tubos del carril (la puerta los muestra como «piezas»)."""
    from .electrico import modelo

    m = modelo(doc)
    return {x for x in (*(d.designacion for d in m.dispositivos),
                        *(c.designacion for c in m.cables), *(c.id for c in m.conductores),
                        *(t.id for t in m.tubos)) if x}


def cambiar_justificadas(doc, valor, modo: str = "reemplazar") -> dict:
    """Pone el metadato `doc.justificadas` (puerta-sin-sobrediseno D6/D11: avisos y piezas
    aceptados por escrito; manifest, fuera del log). `reemplazar` cambia la lista entera (`[]` la
    vacía); `agregar` suma o reemplaza por (regla, pieza) sin tocar el resto. Devuelve la lista y
    las cuentas (`quedaron`, y `borradas` o `agregadas`/`reemplazadas`): nunca se pierde una
    justificación sin decirlo. Valida antes de tocar nada; `ServiceError(400)` con la corrección.
    `pieza` es un id de la escena o lo que el ERC nombra (`nombres_del_tablero`: «-MM1»)."""
    from apolo.library.calidad.justificadas import clave, fusionar, validar_justificadas

    from .errors import ServiceError

    if modo not in MODOS_JUSTIFICADAS:
        raise ServiceError(400, f"justificadas: modo «{modo}» no reconocido; válidos: "
                                + ", ".join(MODOS_JUSTIFICADAS))
    try:
        limpio = validar_justificadas(valor)
    except ValueError as exc:
        raise ServiceError(400, str(exc)) from exc
    piezas = {j["pieza"] for j in limpio if "pieza" in j} - set(doc.scene)
    faltan = sorted(piezas - nombres_del_tablero(doc)) if piezas else []
    if faltan:
        raise ServiceError(400, f"justificadas: pieza(s) inexistente(s) {', '.join(faltan)}: "
                                "`pieza` es el id de una pieza (c12) o la designación de un "
                                "aparato o cable del tablero (-Q1), tal como la muestra la evidencia")
    previas = list(getattr(doc, "justificadas", None) or [])
    if modo == "agregar":
        doc.justificadas, agregadas, reemplazadas = fusionar(previas, limpio)
        cuentas = {"agregadas": agregadas, "reemplazadas": reemplazadas}
    else:
        nuevas = {clave(j) for j in limpio}
        doc.justificadas = limpio
        cuentas = {"borradas": sum(1 for j in previas if clave(j) not in nuevas)}
    return {"justificadas": doc.justificadas, "quedaron": len(doc.justificadas), **cuentas}


def poner_justificadas(doc, valor) -> list[dict]:
    """Reemplaza el metadato `doc.justificadas` (la lista; las cuentas, `cambiar_justificadas`)."""
    return cambiar_justificadas(doc, valor)["justificadas"]


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


def items_de_fuentes(doc, registro=None, contexto: Contexto | None = None,
                     tiempos: dict | None = None) -> dict:
    """{clave: {"items": [ítems como dict], "riesgos"?: [filas]}} de cada `Fuente` del registro
    (cada servicio corre UNA vez, `función(doc, contexto=)`), o {clave: {"error"}} si no corre.
    `tiempos` recibe `fuentes.<clave>` en segundos."""
    from apolo.library.calidad.item import Item
    from apolo.library.calidad.registro import fuentes

    contexto = contexto or Contexto()
    tiempos = {} if tiempos is None else tiempos
    out: dict = {}
    for f in fuentes(registro):
        modulo, nombre = f.servicio.split(":")
        with _cronometro(tiempos, f"fuentes.{f.clave}"):
            try:
                r = getattr(importlib.import_module(modulo), nombre)(doc, contexto=contexto)
                items = r["items"] if isinstance(r, dict) else r
                out[f.clave] = {"items": [i.to_dict() if isinstance(i, Item) else dict(i)
                                          for i in items]}
                if isinstance(r, dict) and r.get("riesgos") is not None:
                    out[f.clave]["riesgos"] = list(r["riesgos"])
            except Exception as exc:  # noqa: BLE001 — una fuente que no corre: SIN_EVALUAR
                out[f.clave] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def reunir(doc, *, expand, gravedad: dict, registro=None, tiempos: dict | None = None,
           sobrantes: bool = True) -> dict:
    """Los insumos del registro, salvo la marcha. `gravedad` = {"resultado": dict | None,
    "motivo"}: la simulación que la API corrió con su lock (None = no corrió → SIN_EVALUAR).
    `sobrantes=False` no prueba qué sobra (SIN_EVALUAR): sólo el presupuesto de los defectos
    sembrados que miran otro ítem; la API la corre siempre. La geometría de masa de cada forma se
    mide UNA vez en la corrida (`engineering/mass.memo_de_geometria`; F3c: las reglas de
    estructura se rehacen en cada prueba de sobrantes sobre las mismas formas)."""
    from apolo.library.engineering.mass import memo_de_geometria

    with memo_de_geometria():
        return _reunir(doc, expand=expand, gravedad=gravedad, registro=registro, tiempos=tiempos,
                       sobrantes=sobrantes)


def _reunir(doc, *, expand, gravedad: dict, registro, tiempos: dict | None,
            sobrantes: bool) -> dict:
    from apolo.library.delivery import delivery_report

    from .delivery_inputs import delivery_inputs
    from .memoria_reglas import veredicto_memoria
    from .puerta_hechos import fabricacion, hechos

    tiempos = {} if tiempos is None else tiempos
    contexto = Contexto()
    por_regla: dict = {}
    with _cronometro(tiempos, "entrega"):
        kw = delivery_inputs(doc, expand=expand, tiempos=por_regla)
        entrega = delivery_report(**kw, gravedad=gravedad.get("resultado"))
    tiempos.update({f"entrega.{k}": v for k, v in por_regla.items()})
    with _cronometro(tiempos, "hechos"):
        h = hechos(doc, kw, contexto)
    with _cronometro(tiempos, "flujo"):
        from .flujo_producto import evaluar as evaluar_flujo

        flujo = evaluar_flujo(doc, mueve=h["mueve_producto"])  # balance-de-producto D9
    with _cronometro(tiempos, "interferencia_interna"):
        interna = interferencia_interna(doc)
    with _cronometro(tiempos, "memoria"):
        try:
            memoria = veredicto_memoria(doc)
        except Exception as exc:  # noqa: BLE001 — sin memoria: SIN_EVALUAR
            memoria = {"error": f"{type(exc).__name__}: {exc}"}
    with _cronometro(tiempos, "fuentes"):
        fuentes = items_de_fuentes(doc, registro, contexto, tiempos)
    with _cronometro(tiempos, "fabricabilidad"):
        fab = fabricacion(doc)
    with _cronometro(tiempos, "sobrantes"):  # D7: sólo en esta puerta, tras las fuentes
        from .calidad_sobrantes import sobrantes as probar_sobrantes

        try:
            sobra = (probar_sobrantes(doc, contexto) if sobrantes else
                     {"error": "no se probó en esta corrida (sobrantes=False)"})
        except Exception as exc:  # noqa: BLE001 — no se pudo probar: SIN_EVALUAR
            sobra = {"error": f"{type(exc).__name__}: {exc}"}
    h["sobrantes_candidatas"] = bool(sobra.get("candidatas")) or "error" in sobra
    return {"firma": firma(doc), "hechos": h, "entrega": entrega, "gravedad": gravedad,
            "acceso": kw.get("acceso_herramienta"), "electrico": kw.get("electrico"),
            "escenarios": kw.get("escenarios"), "nombres": kw.get("nombres"),
            "interna": interna, "memoria": memoria,
            "fuentes": fuentes, "fabricacion": fab, "flujo": flujo,
            "funciones": list(getattr(doc, "funciones", None) or []), "tiempos": tiempos,
            "sobrantes": sobra, "justificadas": list(getattr(doc, "justificadas", None) or []),
            "cadenas": h["cadenas_de_rodillos"]}


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
