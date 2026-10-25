"""Tools MCP de consulta: escena, schemas, catálogo, BOM y costeo, material, color, vertical,
juntas y criterio de diseño.

Bloque de `mcp_server.py` movido tal cual, con 4 espacios más de sangría (plan
partir-nucleo-congelado, F1). `mcp_server` llama `registrar` EN EL LUGAR del bloque con
`globals().update(...)`: el orden de `list_tools()` no cambia y cada tool sigue siendo un
atributo de `apolo.mcp_server`. NO importa `apolo.mcp_server` (con `-m` el servidor es
`__main__`: `tests/test_mcp_registro.py`). `_api`: lambdas que buscan el del servidor en
CADA llamada (un test que lo parchea por nombre también llega aquí). Importa lo que nombran
las anotaciones: FastMCP las evalúa.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from apolo.brief import _one_or_many, _scene_brief


def registrar(mcp, _api) -> dict[str, Callable]:
    """Registra en `mcp` (el del servidor que corre) las tools de `consulta` y las
    devuelve por nombre para que `mcp_server` las re-exporte."""

    @mcp.tool()
    def get_scene(
        ids: list[str] | None = None,
        name: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        summary: bool = False,
    ) -> str:
        """Estado del modelo. Sin argumentos: TODA la escena (sólidos con id/nombre/bbox/volumen/
        componente + variables + configuraciones) — cuidado en proyectos grandes.
        Para trabajar a ESCALA (miles de piezas) usa los filtros y NO vuelques la escena entera:
        - `summary=true`: entra por aquí — resumen por GRUPO (n_piezas, masa, bbox conjunto,
          sub-grupos) + «(sin grupo)» + totales + variables. La vista de una ojeada del proyecto.
        - `ids`: feature_ids o NOMBRES DE GRUPO o de subgrupo (se expanden a sus piezas) → sólo esas.
        - `name`: substring del nombre (case-insensitive), p. ej. "chumacera".
        - `limit` (def. 200) + `offset`: paginación; la respuesta trae `total_filtrado` y
          `truncado` (sin recortes silenciosos). Los briefs filtrados NO traen mallas ni variables
          (pídelas con summary o get_scene() sin filtros)."""
        if summary:
            return json.dumps(_api("GET", "/api/scene/summary").json(), ensure_ascii=False)
        params: dict = {}
        if ids:
            params["ids"] = ",".join(ids) if isinstance(ids, list) else str(ids)
        if name:
            params["name"] = name
        if limit is not None:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        if params:  # brief filtrado/paginado ya listo desde el servidor (sin mallas)
            return json.dumps(_api("GET", "/api/scene", params=params).json(), ensure_ascii=False)
        return json.dumps(_scene_brief(_api("GET", "/api/scene").json()), ensure_ascii=False)

    @mcp.tool()
    def get_command_schemas(command_type: str | None = None) -> str:
        """Comandos CAD con su JSON Schema de parámetros. Consúltalo antes de
        run_command/run_batch. Sin argumento lista TODOS (es grande, ~180 KB); pasa
        `command_type` (p. ej. "create_belt_conveyor") para traer SOLO ese schema. Un campo con
        refs del catálogo trae `x-catalogo` (categorías) en vez de la lista: búscalas con get_catalog."""
        ruta = f"/api/schemas/{command_type}" if command_type else "/api/schemas"
        return json.dumps(_api("GET", ruta).json(), ensure_ascii=False)

    @mcp.tool()
    def get_catalog(category: str | None = None, names_only: bool = False) -> str:
        """Catálogo de componentes industriales (perfiles, rodillos, motorreductores,
        patas, guardas, sensores) con especificaciones y pesos. Es grande (~73 KB);
        filtra con `category` (p. ej. 'motorreductores', 'tubos_estructurales',
        'rodamientos', 'tornilleria', 'tensores_trotadora') y usa `names_only=True`
        para traer solo ref/name/category (payload ligero)."""
        params: dict = {}
        if category:
            params["category"] = category
        if names_only:
            params["names_only"] = "true"
        return json.dumps(_api("GET", "/api/catalog", params=params).json(), ensure_ascii=False)

    @mcp.tool()
    def get_bom(by_group: bool = False) -> str:
        """Lista de materiales del modelo actual, agrupada por referencia y longitud
        (las piezas a-medida idénticas se agrupan e incluyen peso por volumen×densidad).
        Con `by_group=true` cada fila lleva su sub-ensamblaje y las piezas iguales de grupos
        distintos salen separadas (subtotales por grupo/instancia — útil a escala)."""
        params = {"by_group": "true"} if by_group else None
        return json.dumps(_api("GET", "/api/bom", params=params).json(), ensure_ascii=False)

    @mcp.tool()
    def get_costing() -> str:
        """BOM COSTEADO en USD: cada fila con costo_ud/costo_total y su FUENTE (catálogo
        referencial / hardware peso×material×3 / a medida peso×material×2.5) + totales por categoría,
        catálogo vs fabricación y el ÍTEM MÁS COSTOSO: para optimizar costos y como base de la
        cotización. Si algo se cobra dos veces o no se cobra, trae `avisos` con su
        `monto_en_riesgo_usd` y la llamada que lo arregla (no se descuentan solos). Precios
        referenciales: confirmar con proveedor. Read-only."""
        return json.dumps(_api("GET", "/api/costing.json").json(), ensure_ascii=False)

    @mcp.tool()
    def set_material(
        feature: str | None = None, material: str | None = None,
        features: list[str] | None = None,
    ) -> str:
        """Fija (anula) el material de uno o VARIOS sólidos para el BOM/peso/rayado de
        sección. Pasa `feature` (uno) o `features` (lote — N piezas en 1 llamada, atómico:
        un id inexistente no aplica nada), no ambos. material=None vuelve al automático
        (catálogo o heurística por nombre). Ej.: 'acero', 'aluminio', 'acero inoxidable',
        'laton', 'madera', 'vidrio'."""
        ids = _one_or_many(feature, features)
        payload = _api("POST", "/api/features/material", json={"ids": ids, "material": material}).json()
        return json.dumps(_scene_brief(payload), ensure_ascii=False)

    @mcp.tool()
    def set_color(
        color: str | None = None, feature: str | None = None,
        features: list[str] | None = None,
    ) -> str:
        """Color de VISUALIZACIÓN de uno o VARIOS sólidos ('#rrggbb'; None = volver al color
        automático). Pasa `feature` (uno) o `features` (lote — atómico), no ambos. Solo
        apariencia del viewport/render — no toca material, BOM ni peso."""
        ids = _one_or_many(feature, features)
        payload = _api("POST", "/api/features/color", json={"ids": ids, "color": color}).json()
        return json.dumps(_scene_brief(payload, "summary"), ensure_ascii=False)

    @mcp.tool()
    def set_vertical(vertical: str) -> str:
        """Define el vertical del proyecto ('metalmecanica' | 'carpinteria'), que fija el
        material por defecto de las piezas a-medida NO reconocidas (acero | madera)."""
        payload = _api("POST", "/api/vertical", json={"vertical": vertical}).json()
        # afecta a TODA la escena → resumen compacto sin mallas (no el payload crudo)
        return json.dumps(_scene_brief(payload, "summary"), ensure_ascii=False)

    @mcp.tool()
    def get_kinematics() -> str:
        """Juntas cinemáticas del modelo (nombre, tipo, padre/hijo, eje, límites)."""
        return json.dumps(_api("GET", "/api/kinematics").json(), ensure_ascii=False)

    @mcp.tool()
    def get_design_guidelines() -> str:
        """Criterio de INGENIERÍA que debes aplicar por DEFECTO al diseñar (máquinas, muebles,
        estructuras, cualquier objeto): el decálogo completo con detalle, CÓMO verificar cada
        regla en Apolo, cuándo preguntar vs. asumir, y ejemplos por dominio. Las instrucciones del
        servidor ya traen el resumen; consulta ESTO cuando vayas a diseñar algo no trivial (añadir
        una guarda, un soporte, un mueble) para no entregar piezas flotantes, sin montaje ni con la
        forma equivocada. Recuerda: el usuario es el CLIENTE y tú el INGENIERO — lo obvio se asume."""
        return json.dumps(_api("GET", "/api/design-guidelines").json(), ensure_ascii=False)

    return {f.__name__: f for f in (
        get_scene, get_command_schemas, get_catalog, get_bom, get_costing, set_material, set_color,
        set_vertical, get_kinematics, get_design_guidelines,
    )}
