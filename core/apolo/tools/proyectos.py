"""Tools MCP de proyectos: listar, abrir y crear, revisiones y variantes, exportes (STEP, STL,
desplegado DXF) y la prueba de caída.

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

from apolo.brief import _scene_brief

from . import entregable


def registrar(mcp, _api) -> dict[str, Callable]:
    """Registra en `mcp` (el del servidor que corre) las tools de `proyectos` y las
    devuelve por nombre para que `mcp_server` las re-exporte."""

    @mcp.tool()
    def list_projects() -> str:
        """Proyectos guardados (SQLite, con autoguardado)."""
        return json.dumps(_api("GET", "/api/projects").json(), ensure_ascii=False)

    @mcp.tool()
    def open_project(project_id: int) -> str:
        """Abre un proyecto por id. Devuelve además un `briefing` compacto (V6.5b) para arrancar la
        sesión en UNA llamada: resumen por GRUPO (n_piezas/masa/bbox) + variables + requisitos +
        notas del agente + salud (ok/suprimidos) + variantes de diseño. Ya NO hace falta encadenar
        get_scene(summary)+get_requirements+get_agent_notes al abrir."""
        payload = _api("POST", f"/api/projects/{project_id}/open").json()
        out = _scene_brief(payload)
        if "briefing" in payload:
            out["briefing"] = payload["briefing"]
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def create_project(name: str, template: str | None = None) -> str:
        """Crea y abre un proyecto: devuelve su `id` (para open_project), su `nombre` y la escena.
        template: null | 'transportador' | 'brazo'."""
        payload = _api("POST", "/api/projects", json={"name": name, "template": template}).json()
        doc = payload.get("document", {})
        out = {"id": doc.get("project_id"), "nombre": doc.get("name"), **_scene_brief(payload)}
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def save_revision(note: str) -> str:
        """Guarda una revisión (instantánea restaurable) del proyecto abierto."""
        return json.dumps(_api("POST", "/api/revisions", json={"note": note}).json())

    @mcp.tool()
    def save_configuration(name: str, values: dict[str, str] | None = None) -> str:
        """Guarda una VARIANTE SIN aplicarla: sólo sus COLUMNAS (las variables que la distinguen; lo
        demás es común). Sin `values` toma el valor ACTUAL de las columnas; la primera variante pide
        `values` (p. ej. {"largo_total": "4000"}), que crea o edita; una clave nueva entra en todas."""
        r = (_api("PUT", f"/api/configurations/{name}", json={"values": values}) if values is not None
             else _api("POST", "/api/configurations", json={"name": name}))
        return json.dumps(_scene_brief(r.json()), ensure_ascii=False)

    @mcp.tool()
    def apply_configuration(name: str) -> str:
        """Aplica una VARIANTE (un undo): reescribe sólo sus columnas; devuelve `cambios` y `aviso`."""
        payload = _api("POST", f"/api/configurations/{name}/apply").json()
        extra = {k: payload[k] for k in ("cambios", "aviso") if k in payload}  # qué movió el clic
        return json.dumps({**_scene_brief(payload), **extra}, ensure_ascii=False)

    @mcp.tool()
    def export_step(path: str) -> str:
        """Exporta el modelo a un archivo STEP en la ruta local indicada."""
        data = _api("GET", "/api/export/step").content
        return f"STEP guardado en {entregable.escribir(path, data)} ({len(data)} bytes)"

    @mcp.tool()
    def export_stl(path: str, tolerance: float = 0.5) -> str:
        """Exporta los sólidos VISIBLES como UN STL binario (malla) en la ruta local
        indicada — para impresión 3D, visores de malla o simuladores externos.
        `tolerance` = desviación máxima de teselado en mm (menor = más fino y pesado).
        Para CAD/interop usa export_step (B-rep exacto); el STL es malla aproximada."""
        data = _api("GET", "/api/export/stl", params={"tolerance": tolerance}).content
        return f"STL guardado en {entregable.escribir(path, data)} ({len(data)} bytes)"

    @mcp.tool()
    def export_flat_pattern(feature_id: str, path: str) -> str:
        """Exporta el patrón plano (desplegado) de una chapa metálica a un DXF local
        para corte láser. feature_id es el id del sólido de la chapa (ver get_scene);
        debe haberse creado con el comando create_sheet_metal. Soporta las pestañas
        ricas de V5.5 (multi-pliegue, taladros/recortes en pestañas — proyectados al
        blank) y K-factor por material (k_factor vacío = tabla según material).
        ¿DWG? GET /api/sheetmetal/{id}/flat.dwg (V5.9, requiere ODA File Converter)."""
        from pathlib import Path

        data = _api("GET", f"/api/sheetmetal/{feature_id}/flat.dxf").content
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"Desplegado DXF guardado en {target} ({len(data)} bytes)"

    @mcp.tool()
    def drop_test(products: list[dict], path: str, seconds: float = 2.0, gravity: float = 9.81) -> str:
        """Simula con FÍSICA (gravedad real, motor MuJoCo) la caída de cajas de 'producto'
        sobre la escena actual (faja, mesa…) y guarda un GIF animado de la caída en `path`.
        Cada producto es un dict {w,d,h (mm), x,y,z (mm pose inicial), mass (kg, opcional)}.
        Devuelve las posiciones de reposo [x,y,z] mm y si el sistema se asentó (settled).
        Es análisis read-only: NO modifica el modelo."""
        from pathlib import Path

        body = {"products": products, "seconds": seconds, "gravity": gravity}
        summary = _api("POST", "/api/physics/drop", json=body).json()
        gif = _api("POST", "/api/physics/drop.gif", json=body).content
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gif)
        return json.dumps(
            {
                "gif": str(target),
                "bytes": len(gif),
                "resting_mm": summary["resting"],
                "settled": summary["settled"],
                "frames": len(summary["frames"]),
            },
            ensure_ascii=False,
        )

    return {f.__name__: f for f in (
        list_projects, open_project, create_project, save_revision, save_configuration,
        apply_configuration, export_step, export_stl, export_flat_pattern, drop_test,
    )}
