"""El ORDEN de las rutas de la API que pueden casar la misma URL no cambia sin que se decida.

Starlette atiende la PRIMERA ruta que casa path y método; si ninguna casa el método, el 405
lleva el `Allow` de la primera que casó el path. Con las rutas repartidas en `api/routers/`,
ese orden lo dan el router y la posición dentro de él: declarar una ruta antes que otra, o
mudarla de router, puede cambiar quién responde una URL. Sobre la `app` viva, este test fija
(D5 del plan `docs/plans/partir-api-main.md`):

- los pares de rutas que pueden casar la misma URL con paths distintos, y cuál va primero;
- los paths con varios métodos, y en qué orden se declaran;
- que cada uno de esos grupos vive en un solo router.

Una ruta nueva que se solape con otra lo pone ROJO hasta que se decida su orden y se anote
aquí. Lo esperado va escrito en el test (nada congelado de una máquina): corre igual en el CI.
La UI (`Mount` en «/», sólo si existe `ui/dist`) queda fuera de la comparación.
"""

from __future__ import annotations

import re
from collections import defaultdict

from starlette.routing import Match

import apolo.api.main as api

#: (la que se declara ANTES, la que va DESPUÉS) por cada par de rutas que puede casar la
#: misma URL con paths distintos. Medido en la F0 del plan: 11 pares (10 de paths, porque
#: `/api/commands/batch` entra por POST y por PATCH).
PARES_EN_ORDEN = [
    ("POST /api/commands/batch", "PUT /api/commands/{command_id}"),
    ("PATCH /api/commands/batch", "PUT /api/commands/{command_id}"),
    ("POST /api/commands/preview", "PUT /api/commands/{command_id}"),
    ("PUT /api/commands/{command_id}", "POST /api/commands/remove"),
    ("DELETE /api/projects/{project_id}", "PATCH /api/projects/current"),
    ("POST /api/constraints/solve", "DELETE /api/constraints/{name}"),
    ("POST /api/fea/static", "GET /api/fea/{feature_id}"),
    ("POST /api/fea/static.png", "GET /api/fea/{feature_id}"),
    ("POST /api/fea/assembly", "GET /api/fea/{feature_id}"),
    ("POST /api/fea/assembly.png", "GET /api/fea/{feature_id}"),
    # el único del MISMO método: `GET /api/fea/group/fringe.png` lo atiende el grupo
    ("GET /api/fea/group/{name}", "GET /api/fea/{feature_id}/fringe.png"),
]

#: Paths con varios métodos, en el orden en que se declaran (el primero da el `Allow`).
METODOS_EN_ORDEN = {
    "/api/agent/notes": ["GET", "POST"],
    "/api/commands": ["POST", "GET"],
    "/api/commands/batch": ["POST", "PATCH"],
    "/api/configurations/{name}": ["PUT", "DELETE"],
    "/api/projects": ["GET", "POST"],
    "/api/revisions": ["POST", "GET"],
    "/api/requirements": ["GET", "PUT"],
    "/api/stackup": ["GET", "PUT", "DELETE"],
    "/api/motion": ["GET", "PUT", "DELETE"],
}


def _segmento_casa(a: str, b: str) -> bool:
    """¿Hay un segmento de URL que casen los dos patrones? `{x}` = texto sin «/» (el
    convertidor `str` de Starlette, el único que usa la API)."""
    pa, pb = "{" in a, "{" in b
    if not pa and not pb:
        return a == b
    if pa and pb:
        return True  # dos segmentos con parámetro: se asume que pueden casar
    patron, literal = (a, b) if pa else (b, a)
    rx = "".join("[^/]+" if p.startswith("{") else re.escape(p)
                 for p in re.split(r"(\{[^}]+\})", patron))
    return re.fullmatch(rx, literal) is not None


def solapan(p: str, q: str) -> bool:
    """¿Pueden los paths `p` y `q` casar la MISMA URL? (un path consigo mismo, también)."""
    a, b = p.split("/"), q.split("/")
    return len(a) == len(b) and all(map(_segmento_casa, a, b))


def _rutas_http(app) -> list[tuple[str, str, object]]:
    """(«MÉTODO path», path, ruta) de cada ruta HTTP de `app`, en el orden en que Starlette
    las prueba. Sin `Mount` (la UI) ni WebSocket: no compiten con las rutas HTTP de la API."""
    return [(f"{m} {r.path}", r.path, r)
            for r in app.routes if getattr(r, "methods", None)
            for m in sorted(r.methods - {"HEAD"})]


def _modulo(ruta) -> str:
    return ruta.endpoint.__module__


def test_los_pares_que_casan_la_misma_url_y_su_orden():
    rutas = _rutas_http(api.app)
    pos = {clave: i for i, (clave, _, _) in enumerate(rutas)}
    por_clave = {clave: r for clave, _, r in rutas}
    vistos = {frozenset((a, b))
              for i, (a, pa, _) in enumerate(rutas) for b, pb, _ in rutas[i + 1:]
              if pa != pb and solapan(pa, pb)}
    esperados = {frozenset(par) for par in PARES_EN_ORDEN}
    nuevos = sorted(" · ".join(sorted(p)) for p in vistos - esperados)
    assert not nuevos, (
        "Rutas nuevas que pueden casar la misma URL que otra: decide cuál va primero, "
        "decláralas en ese orden en el MISMO router y anota el par en PARES_EN_ORDEN:\n"
        + "\n".join(nuevos))
    perdidos = sorted(" · ".join(sorted(p)) for p in esperados - vistos)
    assert not perdidos, "Pares que ya no se solapan (¿ruta borrada o renombrada?):\n" + \
        "\n".join(perdidos)
    invertidos = [f"{a} debe ir antes que {b}" for a, b in PARES_EN_ORDEN if pos[a] > pos[b]]
    assert not invertidos, "\n".join(invertidos)
    separados = [f"{a} ({_modulo(por_clave[a])}) · {b} ({_modulo(por_clave[b])})"
                 for a, b in PARES_EN_ORDEN if _modulo(por_clave[a]) != _modulo(por_clave[b])]
    assert not separados, "Un par solapado vive en UN router:\n" + "\n".join(separados)


def test_los_paths_con_varios_metodos_y_su_orden():
    por_path: dict[str, list] = defaultdict(list)
    for clave, path, ruta in _rutas_http(api.app):
        por_path[path].append((clave.split(" ", 1)[0], _modulo(ruta)))
    varios = {p: [m for m, _ in v] for p, v in por_path.items() if len(v) > 1}
    assert varios == METODOS_EN_ORDEN
    separados = [p for p in METODOS_EN_ORDEN if len({mod for _, mod in por_path[p]}) > 1]
    assert not separados, f"Paths con varios métodos repartidos en varios routers: {separados}"


def _atiende(metodo: str, url: str) -> tuple[str, Match]:
    """Quién atiende `metodo url`, con la regla de `starlette.routing.Router.app`: la primera
    ruta que casa path y método; si ninguna, la primera que casa el path (da el 405)."""
    scope = {"type": "http", "method": metodo, "path": url, "root_path": ""}
    parcial = None
    for _, _, ruta in _rutas_http(api.app):
        match, _ = ruta.matches(scope)
        if match == Match.FULL:
            return ruta.name, match
        if match == Match.PARTIAL and parcial is None:
            parcial = ruta.name
    return parcial, Match.PARTIAL


def test_el_orden_decide_quien_responde():
    """Lo que el orden protege, visto desde la URL: el par del mismo método decide qué
    endpoint responde y el path con varios métodos decide el `Allow` del 405."""
    assert _atiende("GET", "/api/fea/group/fringe.png") == ("get_fea_group", Match.FULL)
    assert _atiende("GET", "/api/fea/pieza-7/fringe.png") == ("get_fea_fringe", Match.FULL)
    assert _atiende("GET", "/api/commands/batch") == ("post_batch", Match.PARTIAL)


def test_la_ui_montada_va_despues_de_la_api():
    """Con `ui/dist`, la UI se monta en «/» y casa cualquier URL: si quedara antes de un router,
    taparía sus rutas. Sin build (el CI) no hay Mount y no hay nada que comparar."""
    tipos = [type(r).__name__ for r in api.app.routes]
    montajes = [i for i, t in enumerate(tipos) if t == "Mount"]
    rutas = [i for i, t in enumerate(tipos) if t != "Mount"]
    assert all(m > max(rutas) for m in montajes)


def test_el_detector_de_solapes():
    """Sin esto, un `solapan` roto (siempre False) dejaría verdes los tests de arriba sin
    comparar nada."""
    assert solapan("/api/stackup", "/api/stackup")
    assert solapan("/api/commands/batch", "/api/commands/{command_id}")
    assert solapan("/api/fea/static.png", "/api/fea/{feature_id}")
    assert solapan("/api/fea/group/{name}", "/api/fea/{feature_id}/fringe.png")
    assert solapan("/api/x/{a}", "/api/{b}/y")
    assert not solapan("/api/export/step", "/api/export/urdf")
    assert not solapan("/api/fea/group/{name}", "/api/fea/{feature_id}")  # otro largo
    assert not solapan("/api/fea/{feature_id}/fringe.png", "/api/fea/{feature_id}/mesh.png")
    assert not solapan("/api/{x}.png", "/api/static.svg")
