"""Rutas de la prueba virtual (plan V8.3 D11–D14): escenarios, co-simulación y lectura paginada.

  - `GET /api/escenarios` (`?nombre=`), `PUT|DELETE /api/escenarios/{nombre}`: el metadato D12
    (`services/escenarios.py`), con el estado y la vigencia de cada uno;
  - `POST /api/cosim/run`: corre un escenario (guardado o inline) y evalúa sus aserciones;
  - `POST /api/cosim/plc/test`: compila un ST y, con escenario, lo corre SIN guardarlo;
  - `GET /api/cosim/simulaciones[/{id}]`: las últimas corridas, por partes (`cosim/consulta.py`);
  - `POST /api/cosim/vivo/escenario`: una sesión en vivo terminada vuelta escenario, corrida por
    lote y con aserciones sugeridas (V8.4 F4, `services/sesion_viva.py`).

Coreografía de una corrida (D11): (a) bajo `STATE_LOCK`, el snapshot (`snapshot_cosim`), la firma
del documento y el hash del escenario; (b) FUERA de todo lock, el worker en su proceso
(`cosim.proceso`, que serializa con `COSIM_LOCK`); (c) el veredicto, puro; (d) bajo `STATE_LOCK`,
el resultado compacto al manifest SÓLO si el documento activo sigue siendo el del snapshot. Con
`?async=true` la corrida va a `COSIM_JOBS` (su cola, una a la vez) y vuelve el recibo.
Las trazas completas viven en memoria (`SIMULACIONES`, las últimas 8): nunca en el `.apolo`.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any
from collections import OrderedDict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apolo.services.errors import ServiceError
from apolo.state import STATE_LOCK

from ..common import _autosave, _job_cosim, _verificar_documento
from ..fea_runs import _http_error
from ..session import S

router = APIRouter()


class Simulaciones:
    """Las últimas corridas EN MEMORIA (resultado entero + compacto), por id. Lock HOJA."""

    TOPE = 8

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._d: OrderedDict = OrderedDict()

    def guardar(self, entrada: dict) -> None:
        with self._lock:
            self._d[entrada["id"]] = entrada
            while len(self._d) > self.TOPE:
                self._d.popitem(last=False)

    def get(self, sim_id: str) -> dict | None:
        with self._lock:
            return self._d.get(sim_id)

    def con_hipotesis(self, proyecto, hid: str) -> str | None:
        """La última corrida EN MEMORIA del proyecto con la misma lista de hipótesis `hid` (F6b):
        su `resumen` las da completas."""
        with self._lock:
            return next((e["id"] for e in reversed(self._d.values())
                         if e.get("proyecto") == proyecto and e.get("hipotesis_id") == hid), None)

    def lista(self) -> list[dict]:
        with self._lock:
            return [{k: e[k] for k in ("id", "proyecto", "escenario", "veredicto", "creado", "prueba_plc")}
                    for e in reversed(self._d.values())]


SIMULACIONES = Simulaciones()


def _correr(escenario, *, programas=None, guardar=True, proyecto=None, extra=None,
            plc_externo=None) -> dict:
    from apolo.cosim.consulta import compacto, hipotesis_id
    from apolo.cosim.proceso import CosimError, LazoCortadoError, correr_en_proceso
    from apolo.cosim.veredicto import evaluar
    from apolo.services import cosim_externo
    from apolo.services import escenarios as E
    from apolo.services.cosim_snapshot import snapshot_cosim

    pedir_guardar, guardar = guardar, guardar and not plc_externo  # D7: con externo, nunca
    with STATE_LOCK:  # (a) el snapshot, en una adquisición
        if proyecto is not None and S.project_id != proyecto:
            raise HTTPException(status_code=409, detail=(
                f"El proyecto activo cambió mientras la co-simulación esperaba en cola (era "
                f"{proyecto}, ahora {S.project_id}): no se corrió. Abre el proyecto y reenvíala."))
        pid, doc = S.project_id, S.doc
        try:
            nombre, esc = E.resolver(doc, escenario)
            if nombre and guardar:
                _verificar_documento()  # va a escribir su resultado en ESTE documento
            firma, h = E.firma_documento(doc), E.hash_escenario(esc)
            snap = snapshot_cosim(doc, esc, programas=programas, plc_externo=plc_externo)
        except ServiceError as exc:
            raise _http_error(exc) from exc
    try:  # (b) fuera de todo lock
        res = correr_en_proceso(snap)
    except LazoCortadoError as exc:  # plc-en-el-lazo D8: el PLC de afuera o su red, no el núcleo
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except CosimError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if getattr(snap, "externos", None):  # D7: sin veredicto, con el conector que se usó
        res["plc_externo"] = cosim_externo.resultado(plc_externo)
        ver = cosim_externo.veredicto_nulo()
    else:
        ver = evaluar(snap.escenario.aserciones, res)  # (c)
    sim_id = "s" + uuid.uuid4().hex[:8]
    hid = hipotesis_id(res.get("hipotesis") or [])
    previa = SIMULACIONES.con_hipotesis(pid, hid)  # F6b: las mismas ya salieron → sólo el id
    base = compacto(res, ver, simulacion=sim_id, escenario=nombre, hipotesis_vistas_en=previa)
    if extra:
        base.update(extra)
    SIMULACIONES.guardar({"id": sim_id, "proyecto": pid, "escenario": nombre,
                          "veredicto": ver["veredicto"], "creado": time.strftime("%H:%M:%S"),
                          "prueba_plc": programas is not None, "res": res, "base": base,
                          "hipotesis_id": hid})
    out = dict(base)
    if nombre and pedir_guardar and not guardar:
        out.update(guardado=False, aviso_guardado=cosim_externo.MOTIVO)
    if nombre and guardar:  # (d)
        with STATE_LOCK:
            if S.project_id != pid or S.doc is not doc:
                out["guardado"] = False
                out["aviso_guardado"] = ("El proyecto activo cambió durante la co-simulación: el "
                                         "resultado NO se guardó en el escenario (sería el documento "
                                         "equivocado). Abre el proyecto y vuelve a correrlo.")
            else:
                out["guardado"] = E.guardar_resultado(doc, nombre, E.resultado_compacto(
                    ver, res, firma=firma, hash_esc=h, simulacion=sim_id,
                    extensiones=getattr(snap, "extensiones", None)))
                if out["guardado"]:
                    _autosave()
                out["estado"] = E.estado(doc, nombre)["estado"] if nombre in doc.escenarios else None
    return out


# ── escenarios (metadato D12) ──────────────────────────────────────────────────────────────


@router.get("/api/escenarios")
def get_escenarios(nombre: str | None = None) -> dict:
    """Los escenarios de prueba con su estado (sin_correr, pasa, falla, sin_aserciones o vencido);
    con `nombre`, ése entero: definición y último resultado. Read-only."""
    from apolo.services.escenarios import listar

    with STATE_LOCK:
        try:
            return listar(S.doc, nombre)
        except ServiceError as exc:
            raise _http_error(exc) from exc


class EscenarioIn(BaseModel):
    escenario: dict


@router.put("/api/escenarios/{nombre}")
def put_escenario(nombre: str, body: EscenarioIn) -> dict:
    """Declara o reemplaza un escenario (metadato: no entra al log ni al undo)."""
    from apolo.services.escenarios import poner

    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
        try:
            out = poner(S.doc, nombre, body.escenario)
        except ServiceError as exc:
            raise _http_error(exc) from exc
        _autosave()
        return out


@router.delete("/api/escenarios/{nombre}")
def delete_escenario(nombre: str) -> dict:
    from apolo.services.escenarios import listar, quitar

    with STATE_LOCK:
        _verificar_documento()
        try:
            quitar(S.doc, nombre)
        except ServiceError as exc:
            raise _http_error(exc) from exc
        _autosave()
        return {"borrado": nombre, **listar(S.doc)}


# ── co-simulación ──────────────────────────────────────────────────────────────────────────


class CorrerIn(BaseModel):
    escenario: str | dict
    guardar: bool = True  # sólo un escenario con nombre guarda su resultado
    plc_externo: Any = None  # {"-K1": {"conector", "config"}}: lo valida el servicio (400)


@router.post("/api/cosim/run", response_model=dict)
def cosim_run(body: CorrerIn, async_: bool = Query(False, alias="async")):
    """Corre la máquina entera con un escenario (D11) y evalúa sus aserciones (D12). Un escenario
    con nombre guarda su resultado con su vigencia (lo lee la puerta de entrega, D14). Con
    `plc_externo` (plan plc-en-el-lazo D6–D8) esos PLC son los de afuera, a ritmo de pared: el
    resultado no es determinista, no tiene veredicto ni se guarda; un lazo cortado es 502."""
    return _job_cosim("cosim", lambda proyecto: _correr(body.escenario, guardar=body.guardar,
                                                        proyecto=proyecto,
                                                        plc_externo=body.plc_externo), async_)


class PruebaPlcIn(BaseModel):
    fuente: str
    plc: str | None = None
    nombre: str = ""
    ciclo_ms: int = 10
    ciclos: dict[str, int] = {}
    escenario: str | dict | None = None
    senales: list[str] | None = None


def _compilar_prueba(body: PruebaPlcIn) -> tuple[dict, dict | None]:
    """({compila, …}, programa para el snapshot o None). Bajo STATE_LOCK (lee el tablero)."""
    from apolo.library.electrico.referencias import sufijo_sugerencia
    from apolo.plc import ErrorCompilacion, compilar
    from apolo.services.electrico import modelo

    bornes = None
    if body.plc:
        plcs = {d.designacion: d for d in modelo(S.doc).dispositivos if (d.modelo or {}).get("tipo") == "plc"}
        d = plcs.get(body.plc)
        if d is None:
            raise HTTPException(status_code=400, detail=(
                f"«{body.plc}» no es un PLC del tablero; PLC: {', '.join(plcs) or 'ninguno'}."
                f"{sufijo_sugerencia(body.plc, list(plcs))}"))
        bornes = {b.id for b in d.bornes}
    try:
        comp = compilar(body.fuente, bornes=bornes)
    except ErrorCompilacion as exc:
        return {"compila": False, "errores": [e.a_dict() for e in exc.errores], "error": str(exc)}, None
    progs = [n for n, _, _ in comp.programas]
    malos = [p for p in body.ciclos if p.lower() not in {c for _, c, _ in comp.programas}]
    if malos:
        return {"compila": False, "error": f"`ciclos`: la fuente no tiene PROGRAM {malos}; "
                                           f"PROGRAM: {', '.join(progs)}"}, None
    info = {"compila": True, "programas": progs, "tags": comp.tags,
            **({} if body.plc else {"aviso_bornes": "sin `plc` no se comprueban las direcciones "
                                                    "contra los bornes de un PLC"})}
    prog = {"plc": body.plc, "nombre": body.nombre or (progs[0] if progs else "prueba"),
            "fuente": body.fuente, "ciclo_ms": body.ciclo_ms, "ciclos": dict(body.ciclos)}
    return info, prog


@router.post("/api/cosim/plc/test", response_model=dict)
def cosim_plc_test(body: PruebaPlcIn, async_: bool = Query(False, alias="async")):
    """Compila un programa ST (errores con línea y columna) y, con `escenario`, lo corre en la
    máquina SIN guardarlo (reemplaza al programa de su PLC sólo en esta corrida)."""
    with STATE_LOCK:
        info, prog = _compilar_prueba(body)
    if not info["compila"] or body.escenario is None:
        return info
    if not body.plc:
        raise HTTPException(status_code=400, detail="para correr el programa en la máquina indica "
                                                    "`plc` (la designación del PLC, «-K1»)")

    def _work(proyecto):
        from apolo.cosim.consulta import parte

        out = _correr(body.escenario, programas=[prog], guardar=False, proyecto=proyecto, extra=info)
        ent = SIMULACIONES.get(out["simulacion"])
        senales = body.senales or [f"{body.plc}.*"]
        tr = parte(ent["res"], ent["base"], "trazas", senales=senales, limite=60)
        out["trazas"] = {k: tr[k] for k in ("discretas", "analogicas", "problemas", "senales_recortadas")
                         if tr.get(k)}
        return out

    return _job_cosim("test_plc", _work, async_)


# ── de la sesión en vivo a la prueba (V8.4 F4) ─────────────────────────────────────────────


class SesionIn(BaseModel):
    nombre: str
    sesion: str | None = None            # el `sesion` del `fin`; sin él ni grabación, la última
    grabacion: list[dict] | None = None  # o la sesión entera, como la trae el `fin`
    duracion_s: float | None = None
    base: str | None = None
    firma: str | None = None
    hash_base: str | None = None
    hasta_s: float | None = None         # guardar sólo el tramo inicial
    reemplazar: bool = False


def _sesion_de(body: SesionIn, pid) -> dict:
    """La sesión a guardar: la del cuerpo, la `sesion` en memoria o la última del proyecto."""
    from ..sims import SESIONES_GRABADAS

    if body.grabacion is not None:
        return {k: getattr(body, k) for k in ("grabacion", "duracion_s", "base", "firma", "hash_base")}
    ent = SESIONES_GRABADAS.get(body.sesion) if body.sesion else SESIONES_GRABADAS.ultima(pid)
    if ent is None:
        hay = ", ".join(f"{e['id']} ({e['hora']}, proyecto {e['proyecto']}, {e['duracion_s']:g} s)"
                        for e in SESIONES_GRABADAS.lista())
        que = f"«{body.sesion}»" if body.sesion else "terminada de este proyecto"
        raise HTTPException(status_code=404, detail=(
            f"No hay sesión en vivo {que} en memoria (se guardan las últimas "
            f"{SESIONES_GRABADAS.TOPE}; un reinicio las pierde, pero el `fin` de la sesión las trae "
            f"enteras: pasa su grabacion, duracion_s, base y firma). Sesiones: {hay or 'ninguna'}"))
    if ent.get("proyecto") != pid:
        raise HTTPException(status_code=409, detail=(
            f"La sesión {ent['id']} es del proyecto {ent.get('proyecto')} y el abierto es el {pid}: "
            "ábrelo para guardarla."))
    return ent


def _guardar_sesion(body: SesionIn, proyecto) -> dict:
    """(a) bajo STATE_LOCK: validar y armar el escenario + el snapshot; (b) la corrida por lote
    fuera de todo lock; (c) las aserciones sugeridas, puras; (d) el escenario y su corrida al
    manifest si el documento sigue siendo el mismo."""
    from apolo.cosim.consulta import compacto
    from apolo.cosim.proceso import CosimError, correr_en_proceso
    from apolo.cosim.veredicto import evaluar
    from apolo.services import escenarios as E
    from apolo.services import sesion_viva as SV
    from apolo.services.cosim_snapshot import snapshot_cosim

    with STATE_LOCK:  # (a)
        if proyecto is not None and S.project_id != proyecto:
            raise HTTPException(status_code=409, detail=(
                f"El proyecto activo cambió mientras esperaba en cola (era {proyecto}, ahora "
                f"{S.project_id}): no se guardó. Abre el proyecto y reenvíalo."))
        pid, doc = S.project_id, S.doc
        _verificar_documento()
        sesion = _sesion_de(body, pid)
        try:
            prep = SV.preparar(doc, body.nombre, sesion, hasta_s=body.hasta_s, reemplazar=body.reemplazar)
            esc, nombre = prep["escenario"], prep["nombre"]
            firma, h = E.firma_documento(doc), E.hash_escenario(esc)
            snap = snapshot_cosim(doc, esc)
        except ServiceError as exc:
            raise _http_error(exc) from exc
    try:  # (b)
        res = correr_en_proceso(snap)
    except CosimError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    ver = evaluar([], res)  # (c) se guarda sin aserciones: las sugeridas se proponen
    sugeridas = SV.sugerir(esc, res)
    sim_id = "s" + uuid.uuid4().hex[:8]
    base = compacto(res, ver, simulacion=sim_id, escenario=nombre)
    SIMULACIONES.guardar({"id": sim_id, "proyecto": pid, "escenario": nombre, "veredicto": ver["veredicto"],
                          "creado": time.strftime("%H:%M:%S"), "prueba_plc": False, "res": res,
                          "base": base, "hipotesis_id": base.get("hipotesis_id")})
    out = {"nombre": nombre, **({"sesion": sesion["id"]} if sesion.get("id") else {}),
           **{k: prep[k] for k in ("base", "duracion_s", "recortada", "n_acciones", "n_eventos", "cola")},
           "simulacion": sim_id, "huella": (res.get("resumen") or {}).get("huella"),
           "aserciones_sugeridas": sugeridas,
           "aceptar": (f"son sugerencias: para que la prueba las exija, declara «{nombre}» (este "
                       "`escenario`) con las que quieras en `aserciones` (set_scenario o PUT "
                       f"/api/escenarios/{nombre}) y córrelo con simulate(escenario=\"{nombre}\")"),
           "avisos": list(res.get("avisos") or []), "escenario": esc}
    with STATE_LOCK:  # (d)
        if S.project_id != pid or S.doc is not doc or E.firma_documento(doc) != firma:
            out["guardado"] = False
            out["aviso_guardado"] = ("El documento cambió durante la corrida: el escenario NO se guardó "
                                     "(la grabación es del modelo de antes). Reinicia la sesión en vivo.")
            return out
        if nombre in doc.escenarios and not body.reemplazar:  # lo declararon mientras corría
            out["guardado"] = False
            out["aviso_guardado"] = (f"Mientras corría se declaró otro escenario «{nombre}»: NO se pisó. "
                                     "Vuelve a guardar con otro nombre o con reemplazar=true.")
            return out
        try:
            puesto = E.poner(doc, nombre, esc)
        except ServiceError as exc:
            raise _http_error(exc) from exc
        E.guardar_resultado(doc, nombre, E.resultado_compacto(ver, res, firma=firma, hash_esc=h,
                                                              simulacion=sim_id,
                                                              extensiones=getattr(snap, "extensiones", None)))
        _autosave()
        out.update(guardado=True, estado=E.estado(doc, nombre)["estado"])
        out["avisos"] += puesto["avisos"]
    return out


@router.post("/api/cosim/vivo/escenario", response_model=dict)
def cosim_vivo_escenario(body: SesionIn, async_: bool = Query(False, alias="async")):
    """Guarda una sesión EN VIVO terminada como escenario de prueba (V8.4 D10): sus acciones y
    eventos con la hora virtual en que entraron, sobre su escenario de base (con la cola de cajas
    que tuvo la sesión). La corre por lote —mismas trazas que la sesión— y propone aserciones con
    lo que pasó (`aserciones_sugeridas`, que pasan sobre esa corrida); no las impone."""
    return _job_cosim("sesion_viva", lambda proyecto: _guardar_sesion(body, proyecto), async_)


@router.get("/api/cosim/simulaciones")
def cosim_simulaciones() -> dict:
    """Las últimas corridas (en memoria: un reinicio las pierde; el veredicto de un escenario con
    nombre queda en su metadato)."""
    return {"simulaciones": SIMULACIONES.lista()}


@router.get("/api/cosim/simulaciones/{sim_id}")
def cosim_simulacion(sim_id: str, parte: str = "resumen", senales: str | None = None,
                     desde_s: float | None = None, hasta_s: float | None = None,
                     limite: int = 200, offset: int = 0) -> dict:
    """Una corrida por partes (resumen, eventos, final, trazas); `senales` separadas por coma,
    con patrones `*`. Paginado con `limite`/`offset`."""
    from apolo.cosim.consulta import parte as leer_parte

    ent = SIMULACIONES.get(sim_id)
    if ent is None:
        ids = [e["id"] for e in SIMULACIONES.lista()]
        raise HTTPException(status_code=404, detail=(
            f"No hay simulación «{sim_id}» en memoria (se guardan las últimas "
            f"{Simulaciones.TOPE}; un reinicio las pierde): vuelve a correr el escenario. "
            f"Disponibles: {', '.join(ids) or 'ninguna'}"))
    lista = [s.strip() for s in senales.split(",") if s.strip()] if senales else None
    try:
        return leer_parte(ent["res"], ent["base"], parte, senales=lista, desde_s=desde_s,
                          hasta_s=hasta_s, limite=limite, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
