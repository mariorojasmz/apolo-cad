"""Qué tools del MCP usa el chat de la app y cómo (plan chat-cliente-igual, D5).

Las 79 `@mcp.tool` de `mcp_server.py` son LA fuente (D1): el chat no redefine ninguna, sólo
decide cuáles ve. Cada tool está en UNO de los dos lados, y `tests/test_catalogo_chat.py`
falla si una tool nueva no está en ninguno:

- `CHAT`: el chat la recibe. `muta` = cambia el documento (en modo propuesta devuelve
  `is_error` en vez de ejecutarse, D6); `ocultar` = params opcionales que el modelo no ve y
  que el adaptador rechaza si los manda igual (rutas de archivo: escribirían en el servidor);
  `etiqueta` = el chip de la UI mientras corre, en gerundio y con el vocabulario de
  `ui/CLAUDE.md` (pieza, unión, variante, revisión…).
- `FUERA_DEL_CHAT`: el chat no la ve, con el motivo.

El ORDEN de `CHAT` es el orden de las definiciones que recibe el modelo (`agent/herramientas.py`):
fijo, para que el prefijo de la caché de prompt no cambie (D12). Puro: sin imports de `apolo`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnChat:
    """Cómo ve el chat una tool del MCP."""

    etiqueta: str
    muta: bool = False
    ocultar: tuple[str, ...] = ()


def _lee(etiqueta: str, ocultar: tuple[str, ...] = ()) -> EnChat:
    return EnChat(etiqueta, muta=False, ocultar=ocultar)


def _muta(etiqueta: str, ocultar: tuple[str, ...] = ()) -> EnChat:
    return EnChat(etiqueta, muta=True, ocultar=ocultar)


CHAT: dict[str, EnChat] = {
    # ── leer el modelo ───────────────────────────────────────────────────────
    "get_scene": _lee("Leyendo el modelo"),
    "get_command": _lee("Leyendo un comando"),
    "find_commands": _lee("Buscando comandos"),
    "get_command_schemas": _lee("Consultando los parámetros de un comando"),
    "get_catalog": _lee("Consultando el catálogo"),
    "get_groups": _lee("Leyendo los grupos"),
    "get_topology": _lee("Leyendo caras y aristas"),
    "get_kinematics": _lee("Leyendo las juntas"),
    "get_mates": _lee("Leyendo los mates"),
    "get_connections": _lee("Leyendo las uniones"),
    "get_motion": _lee("Leyendo los estudios de movimiento"),
    "get_requirements": _lee("Leyendo los requisitos"),
    "get_agent_notes": _lee("Leyendo las notas del proyecto"),
    "get_design_guidelines": _lee("Consultando el criterio de diseño"),
    "get_expression_grammar": _lee("Consultando las expresiones"),
    "resolve_expression": _lee("Evaluando una expresión"),
    "get_fit": _lee("Consultando un ajuste ISO"),
    "get_job": _lee("Esperando el resultado del cambio"),
    # ── modelar (cambian el documento) ───────────────────────────────────────
    "run_command": _muta("Ejecutando un comando"),
    "run_batch": _muta("Ejecutando un lote de comandos"),
    "edit_command": _muta("Editando un comando"),
    "edit_batch": _muta("Editando varios comandos"),
    "undo": _muta("Deshaciendo"),
    "redo": _muta("Rehaciendo"),
    "set_variable": _muta("Cambiando una variable"),
    "set_material": _muta("Asignando el material"),
    "set_color": _muta("Cambiando el color"),
    "set_vertical": _muta("Fijando el material por defecto"),
    "set_visibility": _muta("Mostrando u ocultando una pieza"),
    "set_visibility_bulk": _muta("Mostrando u ocultando piezas"),
    "save_configuration": _muta("Guardando una variante"),
    "apply_configuration": _muta("Aplicando una variante"),
    "auto_group": _muta("Agrupando piezas"),
    "declare_structure": _muta("Declarando la estructura"),
    "delete_connection": _muta("Eliminando uniones"),
    "set_motion": _muta("Definiendo un estudio de movimiento"),
    "set_stackup": _muta("Declarando una cadena de cotas"),
    "set_requirements": _muta("Guardando los requisitos"),
    "add_agent_note": _muta("Guardando una nota"),
    # ── ensayar y validar ────────────────────────────────────────────────────
    "preview": _lee("Ensayando sin aplicar"),
    "render_view": _lee("Mirando el modelo"),
    "pick_point": _lee("Señalando un punto"),
    "measure": _lee("Midiendo una distancia"),
    "near": _lee("Buscando piezas cercanas"),
    "verify": _lee("Verificando condiciones"),
    "check_interference": _lee("Revisando interferencias"),
    "check_assembly": _lee("Revisando la sujeción"),
    "autodetect_connections": _lee("Detectando uniones posibles"),
    "get_dof": _lee("Contando grados de libertad"),
    "gravity_test": _lee("Simulando la gravedad", ocultar=("path",)),
    "scan_motion": _lee("Revisando choques en movimiento"),
    "delivery_check": _lee("Revisando la entrega"),
    "test_sketch": _lee("Probando un croquis"),
    "test_script": _lee("Probando un script"),
    # ── ingeniería y fabricación ─────────────────────────────────────────────
    "engineering_check": _lee("Validando la ingeniería"),
    "get_mass_properties": _lee("Calculando masas"),
    "get_stackup": _lee("Evaluando cadenas de cotas"),
    # guarda su resumen en el proyecto (entra a la memoria de cálculo): muta
    "fea_static": _muta("Calculando esfuerzos (FEA)", ocultar=("fringe_path",)),
    "get_bom": _lee("Armando el BOM"),
    "get_costing": _lee("Costeando el BOM"),
    "cut_list": _lee("Armando la lista de corte"),
    "nesting": _lee("Optimizando el corte"),
    "drawing": _lee("Dibujando un plano", ocultar=("path",)),
}

_PROYECTO = ("el chat trabaja sobre el proyecto que la persona tiene abierto; cambiarlo o "
             "abrir otro es decisión suya, desde la app")
_REVISION = ("las revisiones las guarda y restaura la persona desde la app; restaurar "
             "reemplazaría el documento bajo el chat")
_ARCHIVO = ("sólo escribe un archivo en una ruta del servidor (escritura arbitraria); la "
            "persona descarga los entregables desde la app")
_GIF = ("exige una ruta donde escribir el GIF en el servidor (escritura arbitraria); para "
        "validar están gravity_test y scan_motion")

FUERA_DEL_CHAT: dict[str, str] = {
    "list_projects": _PROYECTO,
    "open_project": _PROYECTO,
    "create_project": _PROYECTO,
    "save_revision": _REVISION,
    "list_revisions": _REVISION,
    "restore_revision": _REVISION,
    "export_step": _ARCHIVO,
    "export_stl": _ARCHIVO,
    "export_flat_pattern": _ARCHIVO,
    "drop_test": _GIF,
    "motion_gif": _GIF,
    "drawing_set": _ARCHIVO,
    "calc_report": _ARCHIVO,
    "quotation": _ARCHIVO,
    "assembly_manual": _ARCHIVO,
    "fea_assembly": ("tarda minutos (malla de todo el bastidor): no cabe en una vuelta del "
                     "chat; se corre desde el MCP"),
}
