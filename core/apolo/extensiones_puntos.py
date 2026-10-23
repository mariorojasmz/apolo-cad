"""Cada punto de extensión, validado y sumado al registro vivo del núcleo (plan
nucleo-abierto-extensiones-privadas, D3, A4, A7). Lo usa `apolo/extensiones.py`, que es el
contrato público; aquí está el detalle por punto.

Cada `sumar_*` valida TODO lo suyo antes de tocar su registro y lo actualiza EN SITIO (los demás
módulos guardan la referencia: `REGISTRY`, `CATALOG`, `MODELOS`…). Si un punto posterior
rechaza la extensión, `extensiones.cargar` devuelve los registros a su instantánea: todo o nada.
Los imports del núcleo van dentro de cada función: sólo se cargan los puntos que la extensión usa.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


class ExtensionRechazada(Exception):
    """Por qué una extensión no se carga: el texto llega tal cual a `GET /api/health`."""


#: Lo que puede ser un comando de extensión (A7): el carril eléctrico tiene UN evaluador
#: (`doc/carril.py`); un `kind="electrico"` de extensión necesita su plan (V8.6).
KINDS_EXTENSION = ("scene", "vars")


def valor(x):
    """Un campo pesado: tal cual, o lo que devuelve su función sin argumentos (perezoso)."""
    if callable(x) and not isinstance(x, (Mapping, list, tuple, type)):
        return x()
    return x


def con_prefijo(nombre, prefijo: str, que: str) -> None:
    if not isinstance(nombre, str) or not nombre.startswith(prefijo + ".") or nombre == prefijo + ".":
        raise ExtensionRechazada(f"{que} «{nombre}» no lleva el prefijo «{prefijo}.»")


def sumar_builders(ext) -> list[str]:
    builders, anclas = dict(valor(ext.builders) or {}), dict(valor(ext.anclas) or {})
    if not builders and not anclas:
        return []
    from apolo.library import loader

    for nombre in builders:
        con_prefijo(nombre, ext.prefijo, "el builder")
        if nombre in loader.BUILDERS:
            raise ExtensionRechazada(f"el builder «{nombre}» ya existe")
    huerfanas = sorted(set(anclas) - set(builders))
    if huerfanas:
        raise ExtensionRechazada(f"anclas de builders que la extensión no declara: {', '.join(huerfanas)}")
    loader.BUILDERS.update(builders)
    loader.ANCLAS.update(anclas)
    return sorted(builders)


def sumar_modelos(ext) -> list[str]:
    """Los modelos de la co-simulación: a `MODELOS` (con su origen, A4) y sus tipos a
    `TIPOS_MODELO`, ANTES del catálogo (su YAML los nombra en `electrico.modelo.tipo`)."""
    modelos = dict(valor(ext.modelos_cosim) or {})
    if not modelos:
        return []
    from apolo.cosim import modelos as M
    from apolo.library.electrico import ficha

    for tipo, clase in modelos.items():
        con_prefijo(tipo, ext.prefijo, "el tipo de modelo")
        if tipo in M.MODELOS:
            raise ExtensionRechazada(f"el tipo de modelo «{tipo}» ya existe")
        if not (isinstance(clase, type) and issubclass(clase, M.Modelo)):
            raise ExtensionRechazada(f"el modelo «{tipo}» no es una clase de apolo.cosim.modelos.Modelo")
        if getattr(clase, "tipo", None) != tipo:
            raise ExtensionRechazada(f"la clase {clase.__name__} declara tipo «{clase.tipo}», no «{tipo}»")
    M.registrar_modelos(modelos, origen=(ext.nombre, ext.version))
    ficha.TIPOS_MODELO.extend(t for t in modelos if t not in ficha.TIPOS_MODELO)
    return sorted(modelos)


def sumar_catalogo(ext) -> list[str]:
    """Las carpetas YAML de la extensión: refs «prefijo.x» nuevas (un choque no carga), sus
    categorías al final del orden de la UI y su `epoch_catalogo` a la firma (A4)."""
    if not ext.catalogo:
        return []
    from apolo.commands import spec
    from apolo.library import catalog, loader

    nuevos: dict = {}
    for carpeta in ext.catalogo:
        carpeta = Path(carpeta)
        if not carpeta.is_dir() or not any(carpeta.glob("*.yaml")):
            raise ExtensionRechazada(f"el catálogo {carpeta} no existe o no tiene YAML")
        try:
            comps = loader.load_catalog(str(carpeta))
        except (ValueError, KeyError, TypeError) as exc:
            raise ExtensionRechazada(f"catálogo {carpeta.name}: {exc}") from exc
        for ref, comp in comps.items():
            con_prefijo(ref, ext.prefijo, "la ref")
            if ref in catalog.CATALOG or ref in nuevos:
                raise ExtensionRechazada(f"la ref «{ref}» ya existe en el catálogo")
            nuevos[ref] = comp
    catalog.CATALOG.update(nuevos)
    for categoria in dict.fromkeys(c.category for c in nuevos.values()):
        if categoria not in catalog.CATEGORIES:
            catalog.CATEGORIES.append(categoria)
    etiqueta = f"{ext.nombre}@{ext.epoch_catalogo}"
    spec.REFS_DE_EXTENSION.update({ref: etiqueta for ref in nuevos})
    return sorted(nuevos)


def sumar_comandos(ext) -> list[str]:
    """Los `CommandSpec` al MISMO `REGISTRY` (schema-driven: el agente y la UI los ven como
    cualquier comando), con sus pistas y las pestañas de sus categorías nuevas."""
    specs = list(valor(ext.comandos) or ())
    if not specs and not (ext.pistas or ext.pistas_campo or ext.pestanas):
        return []
    from apolo.commands import pistas as P
    from apolo.commands.registry import REGISTRY
    from apolo.commands.spec import CommandSpec

    for categoria, pestana in ext.pestanas.items():
        if categoria in P.PESTANAS:
            raise ExtensionRechazada(f"la pestaña «{categoria}» ya es del núcleo")
        if not isinstance(pestana, dict) or not {"orden", "rotulo"} <= set(pestana):
            raise ExtensionRechazada(f"la pestaña «{categoria}» es {{orden, rotulo}}")
    tipos: list[str] = []
    for s in specs:
        if not isinstance(s, CommandSpec):
            raise ExtensionRechazada(f"un comando no es un CommandSpec: {s!r}")
        con_prefijo(s.type, ext.prefijo, "el comando")
        if s.type in REGISTRY or s.type in tipos:
            raise ExtensionRechazada(f"el comando «{s.type}» ya existe")
        if s.kind not in KINDS_EXTENSION:
            raise ExtensionRechazada(f"el comando «{s.type}» es de kind «{s.kind}»: una extensión sólo "
                                     f"suma {' o '.join(KINDS_EXTENSION)} (el carril eléctrico tiene "
                                     "un solo evaluador, A7)")
        if not (ext.pestanas.get(s.category) or P.PESTANAS.get(s.category)):
            raise ExtensionRechazada(f"el comando «{s.type}» es de la categoría «{s.category}», que no "
                                     "tiene pestaña en el ribbon: declárala en `pestanas`")
        tipos.append(s.type)
    ajenas = sorted(set(ext.pistas) - set(tipos))
    if ajenas:
        raise ExtensionRechazada(f"pistas de comandos que la extensión no declara: {', '.join(ajenas)}")
    for clave in ext.pistas_campo:
        if clave in P.PISTAS_CAMPO or "." not in clave:
            raise ExtensionRechazada(f"pista de campo «{clave}»: ya existe o no es «Modelo.campo»")
    REGISTRY.update({s.type: s for s in specs})
    P.PESTANAS.update(ext.pestanas)
    P.PISTAS.update(ext.pistas)
    P.PISTAS_CAMPO.update(ext.pistas_campo)
    return tipos


def resolver_routers(ext, reservados: set[str]) -> list:
    """Los routers de la extensión: toda ruta bajo «/api/<prefijo>/», un prefijo que no es un
    tramo de rutas del núcleo y ninguna (método, path) repetida."""
    rs = ext.routers
    rs = [rs] if hasattr(rs, "routes") else list(valor(rs) or ())
    if not rs:
        return []
    p = ext.prefijo
    if p in reservados:
        raise ExtensionRechazada(f"el prefijo «{p}» ya es un tramo de rutas del núcleo (/api/{p}/…)")
    vistas: set = set()
    for router in rs:
        if not hasattr(router, "routes"):
            raise ExtensionRechazada(f"un router no es un APIRouter: {router!r}")
        for ruta in router.routes:
            path = getattr(ruta, "path", "")
            if not path.startswith(f"/api/{p}/"):
                raise ExtensionRechazada(f"la ruta «{path}» no va bajo /api/{p}/")
            for metodo in sorted(getattr(ruta, "methods", None) or {"WS"}):
                if (metodo, path) in vistas:
                    raise ExtensionRechazada(f"la ruta {metodo} {path} está dos veces")
                vistas.add((metodo, path))
    return rs


class Grabador:
    """Un `mcp` de mentira: anota las tools que registraría la extensión, sin registrarlas."""

    def __init__(self) -> None:
        self.tools: list[tuple] = []  # (nombre, name, kwargs, fn)

    def tool(self, name=None, **kwargs):
        if callable(name):
            raise TypeError("usa @mcp.tool(), con paréntesis")

        def decorar(fn):
            self.tools.append((name or fn.__name__, name, kwargs, fn))
            return fn

        return decorar

    def __getattr__(self, atributo):
        raise ExtensionRechazada(f"tools_mcp sólo puede usar mcp.tool() (usó mcp.{atributo})")


def _nunca(*_a, **_k):
    raise RuntimeError("una tool de extensión no corre al registrarse")


def grabar_tools(ext, de_otras: Mapping[str, str], api=_nunca, mutacion=_nunca,
                 esperar=_nunca) -> list[tuple]:
    """Corre el `tools_mcp` de la extensión contra un `Grabador` y valida los nombres (A7): sin
    punto, con «prefijo_», sin chocar con una del núcleo ni de otra extensión (`de_otras`:
    tool → extensión). Devuelve lo grabado: `extensiones.registrar_tools` lo registra."""
    import re

    if ext.tools_mcp is None:
        if ext.tools_chat:
            raise ExtensionRechazada("tools_chat sin tools_mcp")
        return []
    from apolo.tools import catalogo

    g = Grabador()
    ext.tools_mcp(g, api, mutacion, esperar)
    nombres = [t[0] for t in g.tools]
    for n in nombres:  # la API de Anthropic acepta ^[A-Za-z0-9_-]{1,64}$ (sin punto)
        if not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", n):
            raise ExtensionRechazada(f"la tool «{n}» no es un nombre válido (sin punto: «{ext.prefijo}_x», A7)")
        if not n.startswith(ext.prefijo + "_"):
            raise ExtensionRechazada(f"la tool «{n}» no lleva el prefijo «{ext.prefijo}_»")
        # una del núcleo no tiene dueño (None); una de esta misma extensión puede re-registrarse
        dueno = catalogo.DE_EXTENSION.get(n, de_otras.get(n))
        en_catalogo = n in catalogo.CHAT or n in catalogo.FUERA_DEL_CHAT or n in de_otras
        if (en_catalogo and dueno != ext.nombre) or nombres.count(n) > 1:
            raise ExtensionRechazada(f"la tool «{n}» ya existe")
    sobran = sorted(set(ext.tools_chat) - set(nombres))
    if sobran:
        raise ExtensionRechazada(f"tools_chat nombra tools que no registra: {', '.join(sobran)}")
    if any(not isinstance(v, catalogo.EnChat) for v in ext.tools_chat.values()):
        raise ExtensionRechazada("tools_chat: cada valor es un apolo.tools.catalogo.EnChat")
    return g.tools


def webui_efectiva(ext, con_ui: Mapping[str, Path]) -> tuple[Path | None, str | None]:
    """`(carpeta, aviso)`: la UI que la API sirve de esta extensión (D5). La UI NUNCA rechaza la
    extensión (F1c): sin `index.html`, o si otra cargada ya sirve la suya (`con_ui`: nombre →
    carpeta; hay una sola UI), se descarta con un aviso y la extensión carga sin UI propia. Así
    la API y el MCP, que no mira la UI, cargan lo mismo."""
    if ext.webui is None:
        return None, None
    if not (Path(ext.webui) / "index.html").is_file():
        return None, f"su UI no se sirve: {ext.webui} no tiene index.html (¿falta el build?)"
    if con_ui:
        otra = next(iter(con_ui))
        return None, f"su UI no se sirve: ya sirve la suya la extensión «{otra}» (hay una sola UI)"
    return Path(ext.webui), None
