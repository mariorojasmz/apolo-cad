"""Tools MCP de cálculo: expresiones, ajustes ISO 286 y FEA estático (pieza y ensamblaje).

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


def registrar(mcp, _api) -> dict[str, Callable]:
    """Registra en `mcp` (el del servidor que corre) las tools de `calculo` y las
    devuelve por nombre para que `mcp_server` las re-exporte."""

    @mcp.tool()
    def resolve_expression(expression: str) -> str:
        """Evalúa una expresión (=expr) contra las variables del proyecto SIN modificar nada;
        devuelve {ok, value} o {ok:false, error}, con `aviso` si casi seguro dice otra cosa
        (sin/cos/tan toman GRADOS: tan(30) = 0,577; no conviertas con pi/180). Para comprobar
        una fórmula antes de usarla."""
        return json.dumps(
            _api("GET", "/api/resolve-expression", params={"expr": expression}).json(),
            ensure_ascii=False,
        )

    @mcp.tool()
    def get_expression_grammar() -> str:
        """Funciones, constantes, operadores permitidos en los campos '=expr' y las variables
        del proyecto disponibles. Consúltalo antes de escribir expresiones complejas."""
        return json.dumps(_api("GET", "/api/expression-grammar").json(), ensure_ascii=False)

    @mcp.tool()
    def get_fit(nominal_mm: float, hole: str = "", shaft: str = "") -> str:
        """Límites y análisis de AJUSTE ISO 286 (V5.4) — consúltalo al DISEÑAR un asiento.
        Con `hole` (H7/G7/JS7/K7/M7/N7/P7…) y `shaft` (g6/h7/js6/k6/m6/n6/p6…): análisis
        completo del ajuste — juego/transición/apriete con juego_min/max en µm. Con uno
        solo: sus límites (ei/es µm, lo/hi mm) sobre el nominal. Criterio de asientos:
        inserto de chumacera UC → eje h7 (desliza; fijan los prisioneros); rodamiento
        prensado con anillo interior giratorio → k6. Los taladros llevan `fit` en
        drill_hole y los ejes la clase en el NOMBRE («Eje motriz Ø35 h7») — el plano
        rotula "Ø35 h7 (0/-0.025)" y engineering_check verifica el asiento. Para taladros
        ROSCADOS usa el campo `thread` de drill_hole ("M8": taladra a la broca Ø6.8 y el
        plano rotula la rosca; ficha en GET /api/threads). Read-only."""
        params = {"nominal": nominal_mm}
        if hole:
            params["hole"] = hole
        if shaft:
            params["shaft"] = shaft
        return json.dumps(_api("GET", "/api/fits", params=params).json(), ensure_ascii=False)

    @mcp.tool()
    def fea_static(feature_id: str, fixed: dict, loads: list[dict] | None = None,
                   material: str = "", yield_mpa: float = 0.0,
                   self_weight: bool = False, mesh_size_mm: float = 0.0,
                   fs_min: float = 2.0, fringe_path: str = "") -> str:
        """FEA ESTÁTICO LINEAL de UNA pieza (V5.6): malla tet P2 (gmsh) + elasticidad lineal
        (scikit-fem). Devuelve σ_vm máx (MPa) con su ubicación, desplazamiento máx (mm), FS =
        σy/σ_vm (criterio: ≥2 estático, <1.2 sobrecargada) y las HIPÓTESIS declaradas; el resumen
        se GUARDA y entra solo a la memoria de cálculo (con aviso automático si la geometría
        cambia después). `fixed` y `loads[].selector` son selectores declarativos de CARAS
        ({mode: cara|direccion|cerca…} — elige con get_topology); para cargar un TALADRO o una
        cara grande junto a taladros usa cerca con `medir: "superficie"` y un punto SOBRE la cara.
        Cada load lleva force_n=[Fx,Fy,Fz] (fuerza TOTAL en N, repartida sobre la cara) O
        pressure_mpa (normal entrante); self_weight añade el peso propio. `fringe_path` guarda el
        PNG del campo von Mises (mapa de colores + escala) — MÍRALO: te dice DÓNDE está el
        esfuerzo. Material/σy salen de la pieza (si el material no tiene σy tabulado, pasa
        yield_mpa). GOTCHA: σ_vm máx pegado al empotramiento suele ser concentración numérica del
        encastre ideal (el retorno lo marca con max_en_encastre). Read-only sobre la geometría;
        tarda unos segundos (malla gruesa por defecto, afina con mesh_size_mm)."""
        from pathlib import Path

        body: dict = {"feature_id": feature_id, "fixed": fixed, "loads": loads or [],
                      "self_weight": self_weight, "fs_min": fs_min}
        if material:
            body["material"] = material
        if yield_mpa:
            body["yield_mpa"] = yield_mpa
        if mesh_size_mm:
            body["mesh_size_mm"] = mesh_size_mm
        resumen = _api("POST", "/api/fea/static", json=body).json()
        if fringe_path:
            # el campo del solve queda cacheado en el server → el fringe NO re-resuelve
            png = _api("GET", f"/api/fea/{feature_id}/fringe.png").content
            target = Path(fringe_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png)
            resumen["fringe"] = str(target)
        return json.dumps(resumen, ensure_ascii=False)

    @mcp.tool()
    def fea_assembly(group: str = "", ids: list[str] | None = None, name: str = "",
                     carga_kg: float = 0.0, self_weight: bool = True,
                     yield_mpa: float = 0.0, loads: list[dict] | None = None,
                     fixed_pieces: list[str] | None = None, mesh_size_mm: float = 0.0,
                     fs_min: float = 2.0, fringe_path: str = "", nota: str = "") -> str:
        """FEA ESTÁTICO LINEAL BONDED de un SUB-ENSAMBLAJE (V7.4): el bastidor SOLDADO completo (N
        sólidos PEGADOS, nodos compartidos en las interfaces = sin contacto) bajo la carga de diseño,
        MULTI-MATERIAL, con σ_vm y FS reportados POR PIEZA (la gobernante es la de menor FS). Pasa
        `group` (nombre de sub-ensamblaje) o `ids` (piezas sueltas + `name`). El empotramiento se
        DERIVA de los grounds (base de las patas/placas ancladas a piso) — o pasa `fixed_pieces`; la
        carga se DERIVA de requirements.carga_kg repartida sobre la cama/mesa (nómbrala
        cama/mesa/deck) — o `carga_kg`, o `loads` explícitos [{feature_id, selector,
        force_n|pressure_mpa}]: para cargar un TALADRO o una cara grande junto a taladros, el selector
        es cerca con `medir: "superficie"` y un punto SOBRE la cara. `self_weight` (por defecto SÍ)
        añade el peso propio con densidad por pieza. El HERRAJE de catálogo (motor/rodamientos/pernos)
        se EXCLUYE de la malla y su peso entra como carga sustituta DECLARADA. `yield_mpa` = σy de
        respaldo para piezas sin σy tabulado. El resumen se GUARDA y entra a la memoria (aviso
        automático si la geometría cambia). `fringe_path` guarda el PNG del campo — MÍRALO. GOTCHA: el
        solve del bastidor puede tardar MINUTOS; invoca con mesh_size_mm GENEROSO primero (malla
        gruesa) y afina después. El FEA CONTRASTA la verificación analítica de flecha/pandeo (dos
        caminos al mismo número = confianza para firmar)."""
        from pathlib import Path

        body: dict = {"self_weight": self_weight, "fs_min": fs_min, "loads": loads or []}
        opcionales = {"group": group, "ids": ids, "name": name, "carga_kg": carga_kg,
                      "yield_mpa": yield_mpa, "fixed_pieces": fixed_pieces,
                      "mesh_size_mm": mesh_size_mm, "nota": nota}
        body.update({k: v for k, v in opcionales.items() if v})  # sólo los que vienen
        resumen = _api("POST", "/api/fea/assembly", json=body).json()
        if fringe_path:
            gname = resumen.get("grupo", group or name)
            png = _api("GET", f"/api/fea/group/{gname}/fringe.png").content
            target = Path(fringe_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png)
            resumen["fringe"] = str(target)
        return json.dumps(resumen, ensure_ascii=False)

    return {f.__name__: f for f in (
        resolve_expression, get_expression_grammar, get_fit, fea_static, fea_assembly,
    )}
