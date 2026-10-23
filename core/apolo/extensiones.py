"""Extensiones del núcleo: un paquete aparte suma comandos, rutas, tools, catálogo y modelos de la
co-simulación sin tocar el núcleo (plan nucleo-abierto-extensiones-privadas, D3, D12, A1–A7).

Contrato (lo que una extensión usa; `CONTRATO_EXTENSIONES` sube sólo si cambia esto, A1):

- Un paquete declara UN objeto `Extension` en el grupo de entry points `apolo.extensiones`
  (`[project.entry-points."apolo.extensiones"] nombre = "modulo:EXTENSION"`). En desarrollo,
  `APOLO_EXTENSIONES_EXTRA=modulo:objeto[,modulo:objeto]` carga además sin instalar nada, y
  `APOLO_EXTENSIONES=0` las apaga todas (la suite, `release.py` y `golden_mcp.py`, A3).
- NADA se carga al importar `apolo` (A3). `cargar()` es explícito e idempotente: lo llama
  `api/main.py` antes de `include_router`; el final de `mcp_server.py` sólo registra las tools
  (`registrar_tools`); el worker de la co-simulación recibe en el snapshot las clases de los
  modelos que usa el tablero (`cosim.modelos.registrar_modelos`).
- Todo lo que nombra una extensión lleva su `prefijo`: comandos, refs del catálogo, builders y
  tipos de modelo «x.algo»; tools «x_algo» (el chat las pasa a la API de Anthropic, que no
  admite el punto, A7); rutas «/api/x/…». Un nombre que ya existe o sin prefijo, un comando de
  kind «electrico» (A7) o un `nucleo` que no incluye `CONTRATO_EXTENSIONES` → la extensión NO
  se carga (todo o nada) y queda con su motivo en `estado()` (`GET /api/health`). Nunca tumba
  el arranque. El detalle de cada punto: `extensiones_puntos.py`. La `webui` NUNCA rechaza: sin
  build, o una segunda UI, se descarta con `aviso` y la extensión carga sin UI propia (F1c).
- API ↔ MCP (F1c): la API publica por extensión lo que sumó (`detalle()`, `GET /api/extensiones`:
  comandos, tools, rutas, refs…); el MCP por stdio registra sólo las tools de las extensiones que
  ESA API reporta cargadas con la misma versión (sin API que responda, ninguna).
- Lo que una extensión importa del núcleo está declarado en `apolo/extensiones_api.py`: quitar o
  renombrar algo de ahí sube `CONTRATO_EXTENSIONES`.
- Los campos pesados (`comandos`, `routers`, `modelos_cosim`, `builders`, `anclas`) aceptan el
  valor o una función sin argumentos que lo devuelve: el MCP resuelve sólo las tools y no carga
  OCCT por ellos.
- D12/A4: cada comando lleva su `CommandSpec.version`; `epoch_catalogo` entra a la firma de los
  comandos cuyos params nombran una ref de la extensión (`commands/spec.REFS_DE_EXTENSION`), y un
  resultado de escenario guarda `extensiones: {nombre: version}` si el tablero usa un modelo suyo.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apolo import extensiones_puntos as _P
from apolo.extensiones_puntos import KINDS_EXTENSION, ExtensionRechazada

__all__ = ["CONTRATO_EXTENSIONES", "GRUPO", "KINDS_EXTENSION", "Extension", "ExtensionRechazada",
           "aislado", "apagadas", "cargadas", "cargar", "descubrir", "detalle", "estado",
           "registrar_tools", "routers", "webui"]

#: La versión de lo que una extensión usa del núcleo (A1): `Extension.nucleo` es un rango sobre
#: ESTE número, no sobre la versión del paquete (todo checkout reporta 0.1.0).
CONTRATO_EXTENSIONES = 1
GRUPO = "apolo.extensiones"
_PREFIJO = re.compile(r"^[a-z][a-z0-9_]{1,23}$")


@dataclass(frozen=True)
class Extension:
    """Lo que declara un paquete de extensión (D3). Sólo `nombre`, `prefijo` y `version` son
    obligatorios; cada campo vacío es un punto que la extensión no usa."""

    nombre: str
    prefijo: str
    version: str
    nucleo: tuple[int, int] = (1, 1)  # rango [mín, máx] de CONTRATO_EXTENSIONES que acepta
    comandos: Any = ()  # [CommandSpec] (tipos «prefijo.x»), o una función que la devuelve
    pistas: Mapping[str, str] = field(default_factory=dict)  # tipo → pista para la persona
    pistas_campo: Mapping[str, str] = field(default_factory=dict)  # «Modelo.campo» → pista
    pestanas: Mapping[str, dict] = field(default_factory=dict)  # categoría nueva → {orden, rotulo}
    routers: Any = ()  # [APIRouter] con rutas «/api/<prefijo>/…», o una función
    tools_mcp: Callable | None = None  # registrar(mcp, api, mutacion, esperar), como tools/*.py
    tools_chat: Mapping[str, Any] = field(default_factory=dict)  # tool → tools.catalogo.EnChat
    catalogo: tuple = ()  # carpetas con YAML del catálogo (refs «prefijo.x»)
    builders: Any = field(default_factory=dict)  # builder «prefijo.x» → fábrica, o una función
    anclas: Any = field(default_factory=dict)  # anclas por familia de SUS builders
    modelos_cosim: Any = field(default_factory=dict)  # tipo «prefijo.x» → clase de cosim.Modelo
    epoch_catalogo: int = 1  # súbelo si cambia la geometría de sus refs con los mismos params
    webui: str | Path | None = None  # carpeta de un `dist` compilado (D5): la API lo sirve


@dataclass
class _Registro:
    hecho: bool = False  # `cargar()` ya corrió en este proceso
    descubiertas: list | None = None  # [(origen, Extension | None, error | None)]
    estado: list = field(default_factory=list)  # [{nombre, version, cargada, motivo?}]
    cargadas: list = field(default_factory=list)  # [Extension]
    routers: dict = field(default_factory=dict)  # nombre → [APIRouter] ya resueltos
    tools: dict = field(default_factory=dict)  # tool → nombre de su extensión
    webui: dict = field(default_factory=dict)  # nombre → carpeta de la UI que se sirve (una)
    detalle: dict = field(default_factory=dict)  # nombre → lo que sumó (`detalle()`)


_R = _Registro()


def apagadas() -> bool:
    return os.environ.get("APOLO_EXTENSIONES", "").strip() == "0"


# ── descubrir ───────────────────────────────────────────────────────────────────────────────

def _objeto(spec: str):
    modulo, _, atributo = spec.partition(":")
    if not modulo.strip() or not atributo.strip():
        raise ValueError(f"«{spec}» no es «modulo:objeto»")
    obj = importlib.import_module(modulo.strip())
    for parte in atributo.strip().split("."):
        obj = getattr(obj, parte)
    return obj


def _importar(origen: str, cargador: Callable[[], Any]) -> tuple:
    try:
        obj = cargador()
        if callable(obj) and not isinstance(obj, Extension):
            obj = obj()  # una fábrica sin argumentos también vale
        if not isinstance(obj, Extension):
            raise TypeError(f"no es una apolo.extensiones.Extension sino {type(obj).__name__}")
        return origen, obj, None
    except Exception as exc:  # noqa: BLE001 — una extensión rota nunca tumba el arranque
        return origen, None, f"no se pudo importar: {type(exc).__name__}: {exc}"


def descubrir() -> list[tuple]:
    """Las extensiones instaladas (entry points, por nombre) y las de `APOLO_EXTENSIONES_EXTRA`
    (en su orden), importadas una vez por proceso: `[(origen, Extension | None, error)]`."""
    if _R.descubiertas is None:
        out: list[tuple] = []
        if not apagadas():
            from importlib.metadata import entry_points

            for ep in sorted(entry_points(group=GRUPO), key=lambda e: e.name):
                out.append(_importar(f"{ep.name} ({ep.value})", ep.load))
            for spec in os.environ.get("APOLO_EXTENSIONES_EXTRA", "").split(","):
                if spec.strip():
                    out.append(_importar(spec.strip(), lambda s=spec: _objeto(s)))
        _R.descubiertas = out
    return list(_R.descubiertas)


# ── cargar ──────────────────────────────────────────────────────────────────────────────────

def _cabecera(ext: Extension, ya: Iterable[Extension]) -> None:
    """Nombre, prefijo, contrato (A1) y que no choque con otra ya cargada."""
    if not isinstance(ext.nombre, str) or not ext.nombre.strip():
        raise ExtensionRechazada("la extensión no tiene nombre")
    if not isinstance(ext.prefijo, str) or not _PREFIJO.match(ext.prefijo):
        raise ExtensionRechazada(f"prefijo «{ext.prefijo}» inválido: minúsculas, dígitos y «_», "
                                 "de 2 a 24, empezando por letra")
    try:
        minimo, maximo = (int(v) for v in ext.nucleo)
    except (TypeError, ValueError):
        raise ExtensionRechazada(f"`nucleo` es un rango (mín, máx), no {ext.nucleo!r}") from None
    if not minimo <= CONTRATO_EXTENSIONES <= maximo:
        raise ExtensionRechazada(f"pide el contrato de extensiones {minimo}–{maximo} y este núcleo "
                                 f"da el {CONTRATO_EXTENSIONES}: actualiza la extensión o el núcleo")
    for otra in ya:
        if otra.nombre == ext.nombre or otra.prefijo == ext.prefijo:
            raise ExtensionRechazada(f"choca con la extensión «{otra.nombre}» ya cargada (nombre o "
                                     f"prefijo «{otra.prefijo}»)")
    epoch = ext.epoch_catalogo
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        raise ExtensionRechazada(f"epoch_catalogo «{epoch}» inválido (entero ≥ 1)")


def _aplicar(ext: Extension, reservados: set[str]) -> tuple[list, list, dict]:
    """Valida y suma TODO lo de `ext`; si algo lanza, `cargar` deshace (todo o nada). Devuelve
    sus routers, sus tools grabadas y lo que sumó (para `detalle()`, sin pasar por el MCP)."""
    _cabecera(ext, _R.cargadas)
    builders = _P.sumar_builders(ext)
    modelos = _P.sumar_modelos(ext)  # antes del catálogo: su YAML nombra los tipos de modelo
    refs = _P.sumar_catalogo(ext)
    comandos = _P.sumar_comandos(ext)
    routers_ext = _P.resolver_routers(ext, reservados)
    tools = _P.grabar_tools(ext, _R.tools)
    rutas = [f"{m} {r.path}" for router in routers_ext for r in router.routes
             for m in sorted(getattr(r, "methods", None) or {"WS"})]
    return routers_ext, tools, {"comandos": comandos, "tools": [t[0] for t in tools],
                                "rutas": rutas, "refs": refs, "modelos_cosim": modelos,
                                "builders": builders}


def _registros() -> list:
    """Cada registro mutable que una extensión toca (para deshacer y para aislar tests)."""
    from apolo.commands import pistas, spec
    from apolo.commands.registry import REGISTRY
    from apolo.cosim import modelos
    from apolo.library import catalog, loader
    from apolo.library.electrico import ficha
    from apolo.tools import catalogo

    return [REGISTRY, pistas.PESTANAS, pistas.PISTAS, pistas.PISTAS_CAMPO, spec.REFS_DE_EXTENSION,
            loader.BUILDERS, loader.ANCLAS, catalog.CATALOG, catalog.CATEGORIES, ficha.TIPOS_MODELO,
            modelos.MODELOS, modelos.DE_EXTENSION, catalogo.CHAT, catalogo.FUERA_DEL_CHAT,
            catalogo.DE_EXTENSION]


def instantanea() -> list:
    return [(r, dict(r) if isinstance(r, dict) else list(r)) for r in _registros()]


def restaurar(foto: list) -> None:
    """Devuelve cada registro a la `instantanea` EN SITIO (otros módulos guardan la referencia)."""
    for vivo, copia in foto:
        if isinstance(vivo, dict):
            vivo.clear()
            vivo.update(copia)
        else:
            vivo[:] = copia


def cargar(rutas_nucleo: Iterable[str] = ()) -> list[dict]:
    """Carga las extensiones UNA vez por proceso (idempotente) y devuelve `estado()`.
    `rutas_nucleo`: los paths de la API del núcleo; su primer tramo tras /api/ no puede ser el
    prefijo de una extensión. Lo que una extensión no pasa no se carga: queda su motivo."""
    if _R.hecho:
        return estado()
    _R.hecho = True
    descubiertas = descubrir()
    if not descubiertas:
        return estado()
    reservados = {p.split("/")[2] for p in rutas_nucleo if p.startswith("/api/")}
    for origen, ext, error in descubiertas:
        if ext is None:
            _R.estado.append({"nombre": origen, "version": None, "cargada": False, "motivo": error})
            print(f"apolo: extensión {origen}: {error}", file=sys.stderr)
            continue
        foto = instantanea()
        try:
            routers_ext, tools, suma = _aplicar(ext, reservados)
        except Exception as exc:  # noqa: BLE001 — el código de la extensión también puede lanzar
            restaurar(foto)
            motivo = str(exc) if isinstance(exc, ExtensionRechazada) else f"{type(exc).__name__}: {exc}"
            _R.estado.append({"nombre": ext.nombre, "version": ext.version, "cargada": False,
                              "motivo": motivo})
            print(f"apolo: la extensión {ext.nombre} no se cargó: {motivo}", file=sys.stderr)
            continue
        _R.cargadas.append(ext)
        _R.routers[ext.nombre] = routers_ext
        _R.tools.update({t[0]: ext.nombre for t in tools})
        entrada = {"nombre": ext.nombre, "version": ext.version, "cargada": True}
        ui, aviso = _P.webui_efectiva(ext, _R.webui)  # la UI nunca rechaza la extensión (F1c)
        if ui is not None:
            _R.webui[ext.nombre] = ui
        if aviso:
            entrada["aviso"] = aviso
            print(f"apolo: extensión {ext.nombre}: {aviso}", file=sys.stderr)
        _R.detalle[ext.nombre] = {**suma, "ui": ui is not None}
        _R.estado.append(entrada)
    return estado()


# ── lo que leen la API y el MCP ─────────────────────────────────────────────────────────────

def estado() -> list[dict]:
    """`[{nombre, version, cargada, motivo?, aviso?}]` de cada extensión que se intentó cargar
    (`GET /api/health`). `aviso`: cargó, pero sin algo que no la rechaza (su UI, F1c)."""
    return [dict(e) for e in _R.estado]


def detalle() -> list[dict]:
    """`estado()` más, por cada cargada, lo que sumó al núcleo: `comandos`, `tools`, `rutas`
    («MÉTODO /api/x/…»), `refs`, `modelos_cosim`, `builders` y si se sirve su `ui`
    (`GET /api/extensiones`). Sale de la `Extension` al cargarla (las tools, grabadas con un
    `mcp` de mentira): la API lo sabe sin el proceso del MCP."""
    out = []
    for e in _R.estado:
        suma = _R.detalle.get(e["nombre"]) if e.get("cargada") else None
        out.append({**e, **{k: list(v) if isinstance(v, list) else v for k, v in (suma or {}).items()}})
    return out


def cargadas() -> list[Extension]:
    return list(_R.cargadas)


def routers() -> list:
    """Los routers de las extensiones cargadas: `api/main.py` los incluye DESPUÉS de los del
    núcleo y antes de montar la UI."""
    return [r for ext in _R.cargadas for r in _R.routers.get(ext.nombre, [])]


def webui() -> Path | None:
    """El `dist` de la extensión cargada que trae UI válida (D5), o None: `paths.ui_dist`
    decide. Una UI sin build o una segunda UI se descartaron con aviso al cargar."""
    return next((_R.webui[e.nombre] for e in _R.cargadas if e.nombre in _R.webui), None)


#: Cuánto espera el MCP por stdio a que la API diga qué extensiones tiene (sólo si hay alguna).
ESPERA_API_S = 3.0


def _en_la_api(servidor: Mapping) -> dict | None:
    """`{nombre: version}` de las extensiones CARGADAS en la API a la que habla este MCP
    (`GET /api/extensiones`), o None si no responde (caída, o una API anterior a F1c)."""
    api = servidor.get("_api")
    if api is None:
        return None
    try:
        datos = api("GET", "/api/extensiones", timeout=ESPERA_API_S).json()
        return {e["nombre"]: e.get("version") for e in datos if e.get("cargada")}
    except Exception as exc:  # noqa: BLE001 — sin API, el MCP arranca igual (sin estas tools)
        print(f"apolo: no pude preguntar a la API qué extensiones tiene: {exc}", file=sys.stderr)
        return None


def _para_tools(servidor: Mapping) -> list[Extension]:
    """Las extensiones cuyas tools se registran. Regla única (F1c): el MCP sólo expone las tools
    de una extensión que la API TIENE cargada, con la misma versión.

    - Con `cargar()` ya corrido (la API, cuando el chat importa el MCP): las cargadas.
    - Si no (el MCP por stdio, otro proceso): las descubiertas con el contrato al día (sin
      resolver sus comandos: no carga OCCT) que la API reporta cargadas. Si la API no responde,
      ninguna: el host se reinicia con la API arriba para verlas (como toda tool nueva)."""
    if _R.hecho:
        return list(_R.cargadas)
    out: list[Extension] = []
    for origen, ext, error in descubrir():
        try:
            if ext is None:
                raise ExtensionRechazada(error)
            _cabecera(ext, out)
        except ExtensionRechazada as exc:
            print(f"apolo: extensión {getattr(ext, 'nombre', origen)}: {exc}", file=sys.stderr)
            continue
        out.append(ext)
    if not out:
        return out
    en_api = _en_la_api(servidor) or {}
    for ext in out:
        if ext.nombre not in en_api:
            print(f"apolo: las tools de la extensión {ext.nombre} no se registran: la API no la "
                  "tiene cargada (mira GET /api/health; reinicia el host con la API arriba)",
                  file=sys.stderr)
        elif en_api[ext.nombre] != ext.version:
            print(f"apolo: las tools de la extensión {ext.nombre} no se registran: la API tiene la "
                  f"versión {en_api[ext.nombre]} y este MCP la {ext.version}", file=sys.stderr)
    return [e for e in out if en_api.get(e.nombre, object()) == e.version]

def registrar_tools(mcp, servidor: Mapping) -> list[str]:
    """Registra en `mcp` (el que CORRE: `__main__` con `-m`) las tools de las extensiones, con
    su lugar en el catálogo del chat (por defecto, FUERA_DEL_CHAT: no gasta su presupuesto).
    `servidor` = los `globals()` de `mcp_server`: `api`, `mutacion` y `esperar` buscan ahí
    `_api`, `_mutacion` y `_submit_and_wait` en CADA llamada (un test que los parchea se ve)."""
    from apolo.tools import catalogo

    def api(*a, **k):
        return servidor["_api"](*a, **k)

    def mutacion(*a, **k):
        return servidor["_mutacion"](*a, **k)

    def esperar(*a, **k):
        return servidor["_submit_and_wait"](*a, **k)

    hechas: list[str] = []
    for ext in _para_tools(servidor):
        otras = {t: e for t, e in _R.tools.items() if e != ext.nombre}
        try:
            grabadas = _P.grabar_tools(ext, otras, api, mutacion, esperar)
        except Exception as exc:  # noqa: BLE001
            print(f"apolo: las tools de la extensión {ext.nombre} no se registraron: {exc}",
                  file=sys.stderr)
            continue
        for nombre, name, kwargs, fn in grabadas:
            mcp.tool(name=name, **kwargs)(fn)
            catalogo.agregar(nombre, ext.nombre, ext.tools_chat.get(nombre),
                             f"tool de la extensión «{ext.nombre}» (no la declaró para el chat)")
            hechas.append(nombre)
    return hechas


@contextmanager
def aislado():
    """Para tests (`apolo.pruebas`): `cargar()` puede volver a correr adentro y, al salir, los
    registros y el estado de este módulo quedan como estaban."""
    foto = instantanea()
    previo = _Registro(**vars(_R))
    _R.__init__()
    try:
        yield
    finally:
        restaurar(foto)
        _R.__init__(**vars(previo))
