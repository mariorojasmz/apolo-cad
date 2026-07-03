"""Servidor MCP de Genix Apolo CAD (stdio).

Expone el CAD como tools estándar MCP para que CUALQUIER agente (Claude Code,
Claude Desktop…) pueda diseñar en Apolo. Es un cliente fino de la API HTTP:
exactamente las mismas operaciones que la UI y el chat integrado, y los
cambios aparecen en vivo en el navegador (WebSocket).

Uso:  python -m apolo.mcp_server   (APOLO_URL configura el servidor, por
defecto http://127.0.0.1:8000 — el servidor Apolo debe estar corriendo).
"""

from __future__ import annotations

import json
import os

import httpx
from mcp.server.fastmcp import FastMCP, Image

from apolo.design import design_brief

APOLO_URL = os.environ.get("APOLO_URL", "http://127.0.0.1:8000")

mcp = FastMCP(
    "apolo-cad",
    instructions=(
        # Criterio de ingeniería SIEMPRE presente (capa 1): el agente diseña como un
        # ingeniero/estructurista por defecto, no solo ejecuta al pie de la letra.
        # El detalle y los ejemplos están en el tool get_design_guidelines (capa 2).
        design_brief() + "\n\n"
        "CAD paramétrico Genix Apolo. Unidades mm, eje Z arriba, primitivas centradas. "
        "El documento es un log de comandos: cada operación es editable y deshacible. "
        "Consulta get_command_schemas para los parámetros de cada comando; usa '$k' en lotes "
        "para referenciar sólidos creados en el mismo lote, y '=expresión' en campos numéricos "
        "para usar variables del proyecto (resuélvelas con resolve_expression y consulta la "
        "gramática con get_expression_grammar). Verifica tus montajes con check_interference y "
        "render_view (highlight_ids resalta una pieza; combínalo con set_visibility para aislar). "
        "Para elegir bien una arista/cara antes de fillet/chamfer/drill/add_mate, mira la geometría "
        "con get_topology(id) y traduce a un selector declarativo (cara/direccion/longitud/cerca). "
        "Antes de escribir, PRUEBA en seco con test_sketch/test_script (no tocan el "
        "documento) y valida una faja por sus parámetros con engineering_check(conveyor=...). "
        "get_command(id) devuelve los parámetros actuales de un comando para editarlo. Si una "
        "llamada falla con error de conexión, el servidor Apolo no está arrancado "
        "(uvicorn apolo.api.main:app --port 8000)."
    ),
)


def _api(method: str, path: str, **kwargs):
    try:
        with httpx.Client(base_url=APOLO_URL, timeout=120) as client:
            response = client.request(method, path, **kwargs)
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"No hay conexión con Apolo en {APOLO_URL}: arranca el servidor "
            "(uvicorn apolo.api.main:app --port 8000)"
        ) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"Apolo rechazó la operación ({response.status_code}): {detail}")
    return response


def _scene_brief(payload: dict, detail: str = "diff") -> dict:
    """Resumen sin mallas (las mallas son para el viewport, no para el agente).

    detail controla qué sólidos se listan tras una mutación:
      - "full"    → todos los sólidos de la escena (con bbox).
      - "diff"    → solo los del/los comando(s) afectado(s) por esta operación
                    (`affected_command_ids`). Si no hay afectados (consultas), lista
                    todos. Es el default: evita volcar cientos de sólidos al editar uno.
      - "summary" → solo id/nombre/comando de los afectados (sin bbox/volumen).
    Siempre incluye `total_solidos` (conteo de la escena) y `solidos_mostrados`.
    """
    doc = payload.get("document", {})
    feats = payload.get("features", [])
    total = payload.get("total_features", len(feats))
    affected = set(payload.get("affected_command_ids") or [])

    if detail == "full" or (detail == "diff" and not affected):
        shown = feats
    else:
        # prefijo: las piezas de un insert_project llevan command_id sintético
        # '{cmd}_{cmd_origen}' — también son "del comando afectado"
        shown = [
            f for f in feats
            if f["command_id"] in affected
            or any(f["command_id"].startswith(a + "_") for a in affected)
        ]

    if detail == "summary":
        solidos = [
            {"id": f["id"], "nombre": f["name"], "comando": f["command_id"]} for f in shown
        ]
    else:
        solidos = [
            {
                "id": f["id"],
                "nombre": f["name"],
                "visible": f["visible"],
                "bbox": f["bbox"],
                "volumen_mm3": f["volume_mm3"],
                "componente": f["component"],
                "comando": f["command_id"],
                **({"grupo": f["group"]} if f.get("group") else {}),
            }
            for f in shown
        ]
    # `variables` es verboso (~33 entradas) y se repetía en CADA mutación. Lo incluimos
    # solo cuando aporta: vista completa, consulta (sin afectados) o cuando la operación
    # tocó alguna variable (su command_id es un set_variable). Las mutaciones de geometría
    # —el caso común— ya no lo arrastran. Para verlas siempre, usar get_scene.
    var_ids = {c["id"] for c in doc.get("commands", []) if c.get("type") == "set_variable"}
    include_vars = detail == "full" or not affected or bool(affected & var_ids)
    out = {
        "proyecto": doc.get("name"),
        "configuraciones": doc.get("configurations"),
        "puede_deshacer": doc.get("can_undo"),
        "puede_rehacer": doc.get("can_redo"),
        "total_solidos": total,
        "solidos_mostrados": len(solidos),
        "solidos": solidos,
    }
    if include_vars:
        out["variables"] = doc.get("variables")
    return out


# ----------------------------------------------------------------- consulta
@mcp.tool()
def get_scene() -> str:
    """Estado actual del modelo: sólidos (id, nombre, bbox, volumen, componente),
    variables del proyecto y configuraciones."""
    return json.dumps(_scene_brief(_api("GET", "/api/scene").json()), ensure_ascii=False)


@mcp.tool()
def get_command_schemas(command_type: str | None = None) -> str:
    """Comandos CAD con su JSON Schema de parámetros. Consúltalo antes de
    run_command/run_batch. Sin argumento lista TODOS (es grande, ~77 KB); pasa
    `command_type` (p. ej. "create_belt_conveyor") para traer SOLO ese schema."""
    if command_type:
        return json.dumps(
            _api("GET", f"/api/schemas/{command_type}").json(), ensure_ascii=False
        )
    return json.dumps(_api("GET", "/api/schemas").json(), ensure_ascii=False)


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
def get_bom() -> str:
    """Lista de materiales del modelo actual, agrupada por referencia y longitud
    (las piezas a-medida idénticas se agrupan e incluyen peso por volumen×densidad)."""
    return json.dumps(_api("GET", "/api/bom").json(), ensure_ascii=False)


@mcp.tool()
def get_costing() -> str:
    """BOM COSTEADO en USD: cada fila del BOM con costo_ud/costo_total y su FUENTE
    (precio referencial de catálogo / estimación de hardware peso×material×3 /
    fabricación a medida peso×material×2.5) + totales por categoría, catálogo vs
    fabricación y el ÍTEM MÁS COSTOSO. Úsalo para optimizar costos ('¿qué pieza es la
    más cara?', comparar alternativas) y como base de la cotización. Precios
    referenciales — confirmar con proveedor para cotizar en firme. Read-only."""
    return json.dumps(_api("GET", "/api/costing.json").json(), ensure_ascii=False)


@mcp.tool()
def set_material(feature: str, material: str | None = None) -> str:
    """Fija (anula) el material de un sólido para el BOM/peso/rayado de sección.
    material=None vuelve al automático (catálogo o heurística por nombre).
    Ej.: 'acero', 'aluminio', 'acero inoxidable', 'laton', 'madera', 'vidrio'."""
    payload = _api("POST", f"/api/features/{feature}/material", json={"material": material}).json()
    return json.dumps(_scene_brief(payload), ensure_ascii=False)


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


# ----------------------------------------------------------------- modelado
@mcp.tool()
def run_command(type: str, params: dict, detail: str = "diff") -> str:
    """Ejecuta un comando CAD (ver get_command_schemas). Los campos numéricos
    aceptan '=expresión' con variables del proyecto. `detail`: "diff" (def.) devuelve
    solo los sólidos nuevos + `total_solidos`; "full" toda la escena; "summary" solo
    id/nombre de lo nuevo. El bloque `variables` solo aparece si la operación tocó
    alguna (o detail="full"); usa get_scene para verlas siempre."""
    payload = _api("POST", "/api/commands", json={"type": type, "params": params}).json()
    return json.dumps(_scene_brief(payload, detail), ensure_ascii=False)


@mcp.tool()
def run_batch(actions: list[dict], detail: str = "diff") -> str:
    """Ejecuta un lote ordenado de comandos [{type, params}, …]. Usa '$k' en los
    campos de id de feature para referenciar el sólido creado por la k-ésima
    acción del lote. `detail`: "diff" (def.) devuelve solo los sólidos creados por el
    lote + `total_solidos`; "full" toda la escena; "summary" solo id/nombre."""
    payload = _api("POST", "/api/commands/batch", json={"actions": actions}).json()
    return json.dumps(_scene_brief(payload, detail), ensure_ascii=False)


@mcp.tool()
def edit_command(command_id: str, params: dict, merge: bool = True, detail: str = "diff") -> str:
    """Edita los parámetros de un comando pasado y regenera (edición paramétrica del
    historial). Por defecto hace PATCH (`merge=True`): combina con los params actuales,
    así que basta enviar los campos a cambiar. Merge SUPERFICIAL: un sub-objeto
    (position, rotation) se reemplaza entero. `merge=False` reemplaza todos los params
    (los omitidos vuelven a su default). `detail` como en run_command."""
    payload = _api(
        "PUT",
        f"/api/commands/{command_id}",
        params={"merge": str(merge).lower()},
        json={"params": params},
    ).json()
    return json.dumps(_scene_brief(payload, detail), ensure_ascii=False)


@mcp.tool()
def edit_batch(edits: list[dict], merge: bool = True, detail: str = "diff") -> str:
    """Edita VARIOS comandos en UN lote ATÓMICO: un solo regenerate y un solo paso de
    undo (frente a N round-trips + N regenerates de llamar edit_command en bucle). Úsalo
    al reparametrizar muchas piezas a la vez. edits = [{"command_id": "c38", "params":
    {...}}, …]. PATCH por defecto (merge=True, superficial: un sub-objeto position/rotation
    se reemplaza entero); merge=False reemplaza todos los params. Si una edición falla,
    revierte TODO el lote. `detail` como en run_command (y `variables` solo aparece si el
    lote tocó alguna)."""
    payload = _api(
        "PATCH",
        "/api/commands/batch",
        params={"merge": str(merge).lower()},
        json={"edits": edits},
    ).json()
    return json.dumps(_scene_brief(payload, detail), ensure_ascii=False)


@mcp.tool()
def undo() -> str:
    """Deshace la última operación."""
    return json.dumps(_scene_brief(_api("POST", "/api/undo").json()), ensure_ascii=False)


@mcp.tool()
def set_variable(name: str, expression: str) -> str:
    """Define o actualiza una variable de proyecto (p. ej. L = 2000). Cambiarla
    regenera todo lo que la usa."""
    payload = _api("POST", "/api/variables", json={"name": name, "expression": expression}).json()
    return json.dumps(_scene_brief(payload), ensure_ascii=False)


# -------------------------------------------------------------- validación
@mcp.tool()
def check_interference(joint_values: dict | None = None) -> str:
    """Interferencias entre sólidos (booleanas OCCT). Con joint_values
    {junta: valor} comprueba la colisión del mecanismo EN POSE."""
    payload = _api("POST", "/api/checks", json={"joint_values": joint_values or {}}).json()
    return json.dumps(payload["interferencias"], ensure_ascii=False)


@mcp.tool()
def engineering_check(
    carga_kg: float | None = None, largo_paquete_mm: float | None = None,
    velocidad_m_s: float | None = None, ancho_paquete_mm: float | None = None,
    conveyor: dict | None = None, conveyor_solid_ids: list[str] | None = None,
) -> str:
    """Valida el modelo con criterio de ingeniería. Devuelve DOS bloques: `ingenieria`
    (reglas del transportador: apoyo del paquete, capacidad de rodillo, ancho útil,
    motorización con μ real banda-cama, par + par de arranque, flecha del bastidor,
    flexión del eje) y `estructura` (chequeo UNIVERSAL de cualquier ensamblaje: uniones
    apernadas vs ISO 898-1, soldaduras, vida L10 de rodamientos, pandeo de patas,
    vuelco). Sin argumentos usa los REQUISITOS guardados del proyecto (set_requirements);
    los parámetros explícitos ganan. Sin `conveyor` valida la faja del documento; con
    `conveyor` (dict {largo,ancho,altura,paso,rodillo,motor}) valida ANTES de construir;
    `conveyor_solid_ids` marca qué sólidos forman la faja. Las reglas numéricas traen
    `calc` (fórmula, sustitución, criterio, factor de seguridad)."""
    body = {
        "carga_kg": carga_kg,
        "largo_paquete_mm": largo_paquete_mm,
        "ancho_paquete_mm": ancho_paquete_mm,
        "conveyor": conveyor,
        "conveyor_solid_ids": conveyor_solid_ids,
    }
    if velocidad_m_s is not None:
        body["velocidad_m_s"] = velocidad_m_s
    payload = _api("POST", "/api/checks", json=body).json()
    return json.dumps(
        {"ingenieria": payload.get("ingenieria"), "estructura": payload.get("estructura")},
        ensure_ascii=False,
    )


@mcp.tool()
def render_view(
    view: str = "iso",
    highlight_ids: list[str] | None = None,
    show_axes: bool = False,
    show_bbox: bool = False,
    joint_values: dict[str, float] | None = None,
    fit_ids: list[str] | None = None,
    zoom: float = 1.0,
    section: str | None = None,
    isolate: list[str] | None = None,
    azimuth: float | None = None,
    elevation: float | None = None,
    measure: list[str] | None = None,
    edges: bool = True,
    xray: bool = False,
    labels: bool = False,
    roll: float = 0.0,
    pan: list[float] | None = None,
) -> Image:
    """Render del modelo para VERLO. SIEMPRE motor VTK → sombreado SUAVE a color (color real por
    pieza, igual que el viewport web), normales interpoladas, sin bandas ni cuadrícula: la captura
    más limpia para auto-revisar tu trabajo. (Si el entorno no tuviera contexto OpenGL, da error
    claro en vez de degradar a una imagen con rejilla.)
    view ∈ {iso, frente, lateral, planta} elige el ángulo preset; azimuth/elevation (GRADOS) lo
    ANULAN para enfocar desde un ÁNGULO LIBRE cuando ningún preset sirve (azimuth = giro alrededor
    de Z, elevation = altura sobre el plano; override parcial: puedes dar solo uno).
    isolate (lista de ids o NOMBRES DE GRUPO — un grupo se expande a todas sus piezas, ver
    get_groups) renderiza SOLO esas piezas — la forma LIMPIA de fotografiar una pieza
    o sub-conjunto de cerca: aísla sobre una copia de la escena, SIN ocultar/restaurar nada en el
    documento. Combínalo con fit_ids (encuadra en esas piezas) y zoom>1 (acerca) para un primer
    plano que llene el cuadro. (Prefiérelo a set_visibility, que sí muta el documento en vivo.)
    highlight_ids y fit_ids también aceptan nombres de grupo.
    highlight_ids resalta esos sólidos y atenúa el resto; show_axes dibuja los ejes del origen;
    show_bbox la caja envolvente de lo resaltado. section ∈ {x,y,z} corta el modelo a la mitad de
    ese eje para VER DENTRO (interferencias/encajes ocultos).
    joint_values posa el mecanismo (CINEMÁTICA) antes de renderizar — p. ej. {"j_tensor_cola": 12};
    las juntas dependientes (restricción de riel) se resuelven solas → ves una pose sin mover el
    documento (read-only). Consulta las juntas con get_kinematics.
    measure=[idA, idB] dibuja una COTA (línea + "X mm") del gap mínimo entre dos piezas SOBRE el
    render → ves la medida, no la calculas (reusa la distancia OCCT, misma que el tool measure).
    Combínalo con isolate/fit_ids/zoom/azimuth para encuadrar la zona a acotar.
    edges (def. True) dibuja las aristas vivas (creases/borde) → separa visualmente piezas
    adyacentes del MISMO color; ponlo False si quieres el sombreado liso sin líneas.
    xray=true (rayos-X): en vez de ocultar/atenuar a gris lo no resaltado, lo deja TRANSLÚCIDO EN SU
    COLOR para ver una pieza INTERNA en su contexto sin cortar (combínalo con highlight_ids: la pieza
    resaltada sale sólida y el resto translúcido). El vidrio ya sale translúcido siempre (no gris).
    labels=true rotula el id de cada pieza SOBRE el render (billboard VTK) → lees el id directo en la
    imagen para identificar y editar (combínalo con isolate/fit_ids para no saturar con 80 etiquetas).
    roll (grados) gira la cámara sobre su eje de visión (3.er GDL: endereza una pieza inclinada);
    pan=[px,py] desplaza el encuadre en el plano de vista (fracción de la semialtura; +px→derecha,
    +py→arriba) para centrar un detalle fuera del centro sin aislar. azimuth/elevation siguen siendo
    la ÓRBITA (cualquier dirección); en proyección ortográfica la distancia del ojo no afecta, así que
    azimuth+elevation+roll+zoom+fit/pan cubren toda la cámara de inspección."""
    params: dict = {
        "view": view,
        "show_axes": show_axes,
        "show_bbox": show_bbox,
        "zoom": zoom,
        "shade": "true",      # VTK siempre sombreado a color
        "vtk_only": "true",   # fuerza VTK; sin fallback a matplotlib (captura limpia garantizada)
    }
    if highlight_ids:
        params["highlight"] = ",".join(highlight_ids)
    if fit_ids:
        params["fit"] = ",".join(fit_ids)
    if isolate:
        params["isolate"] = ",".join(isolate)
    if joint_values:
        params["joints"] = json.dumps(joint_values)
    if section:
        params["section"] = section
    if azimuth is not None:
        params["azimuth"] = azimuth
    if elevation is not None:
        params["elevation"] = elevation
    if measure and len(measure) == 2:
        params["measure"] = ",".join(measure)
    if not edges:
        params["edges"] = "false"   # default del endpoint es true
    if xray:
        params["xray"] = "true"
    if labels:
        params["labels"] = "true"
    if roll:
        params["roll"] = roll
    if pan and len(pan) == 2:
        params["pan"] = ",".join(str(x) for x in pan)
    response = _api("GET", "/api/render.png", params=params)
    return Image(data=response.content, format="png")


@mcp.tool()
def preview(
    actions: list[dict], view: str = "iso", labels: bool = False, section: str | None = None
) -> Image:
    """GHOST RENDER: aplica `actions` (mismo formato que run_batch: [{type, params}, …])
    sobre una COPIA del documento y devuelve el PNG resultante SIN tocar el modelo real
    (los sólidos nuevos van resaltados). Úsalo para VER una propuesta de colocación antes
    de ejecutarla de verdad con run_command/run_batch — equivocarse sale gratis. `labels`
    rotula ids; `section` ∈ {x,y,z} corta para ver dentro."""
    body: dict = {"actions": actions, "view": view, "labels": labels}
    if section:
        body["section"] = section
    response = _api("POST", "/api/commands/preview", json=body)
    return Image(data=response.content, format="png")


# ---------------------------------------------------------------- proyectos
@mcp.tool()
def list_projects() -> str:
    """Proyectos guardados (SQLite, con autoguardado)."""
    return json.dumps(_api("GET", "/api/projects").json(), ensure_ascii=False)


@mcp.tool()
def open_project(project_id: int) -> str:
    """Abre un proyecto por id."""
    payload = _api("POST", f"/api/projects/{project_id}/open").json()
    return json.dumps(_scene_brief(payload), ensure_ascii=False)


@mcp.tool()
def create_project(name: str, template: str | None = None) -> str:
    """Crea y abre un proyecto. template: null | 'transportador' | 'brazo'."""
    payload = _api("POST", "/api/projects", json={"name": name, "template": template}).json()
    return json.dumps(_scene_brief(payload), ensure_ascii=False)


@mcp.tool()
def save_revision(note: str) -> str:
    """Guarda una revisión (instantánea restaurable) del proyecto abierto."""
    return json.dumps(_api("POST", "/api/revisions", json={"note": note}).json())


@mcp.tool()
def export_step(path: str) -> str:
    """Exporta el modelo a un archivo STEP en la ruta local indicada."""
    from pathlib import Path

    data = _api("GET", "/api/export/step").content
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return f"STEP guardado en {target} ({len(data)} bytes)"


@mcp.tool()
def export_stl(path: str, tolerance: float = 0.5) -> str:
    """Exporta los sólidos VISIBLES como UN STL binario (malla) en la ruta local
    indicada — para impresión 3D, visores de malla o simuladores externos.
    `tolerance` = desviación máxima de teselado en mm (menor = más fino y pesado).
    Para CAD/interop usa export_step (B-rep exacto); el STL es malla aproximada."""
    from pathlib import Path

    data = _api("GET", "/api/export/stl", params={"tolerance": tolerance}).content
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return f"STL guardado en {target} ({len(data)} bytes)"


@mcp.tool()
def export_flat_pattern(feature_id: str, path: str) -> str:
    """Exporta el patrón plano (desplegado) de una chapa metálica a un DXF local
    para corte láser. feature_id es el id del sólido de la chapa (ver get_scene);
    debe haberse creado con el comando create_sheet_metal. Soporta las pestañas
    ricas de V5.5 (multi-pliegue, taladros/recortes en pestañas — proyectados al
    blank) y K-factor por material (k_factor vacío = tabla según material)."""
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


# ---------------------------------------------------------- lectura/introspección
@mcp.tool()
def get_command(command_id: str) -> str:
    """Devuelve {type, params} del comando indicado (su estado ACTUAL) para editarlo con
    edit_command. Usa get_scene para ver los ids (campo 'comando' de cada sólido)."""
    doc = _api("GET", "/api/document").json()
    cmd = next((c for c in doc.get("commands", []) if c.get("id") == command_id), None)
    if cmd is None:
        raise RuntimeError(f"No existe el comando '{command_id}' en el documento")
    return json.dumps({"type": cmd["type"], "params": cmd["params"]}, ensure_ascii=False)


@mcp.tool()
def test_sketch(sketch: dict) -> str:
    """Prueba en seco un croquis: lo resuelve con el solver (PlaneGCS) y devuelve {ok,
    residual, diagnostico, dof, redundantes, conflictivas, ...} SIN crear geometría.
    dof = grados de libertad restantes (0 = totalmente restringido); redundantes/
    conflictivas identifican las restricciones culpables por nombre. Soporta tangent/
    symmetric/equal_radius/concentric/midpoint/distance_point_line además de los tipos
    clásicos (el formato completo está en el schema de sketch_extrude). Itera hasta
    dof=0 sin redundantes antes de extruir/barrer."""
    return json.dumps(_api("POST", "/api/sketch/solve", json={"sketch": sketch}).json(), ensure_ascii=False)


@mcp.tool()
def test_script(code: str) -> str:
    """Prueba en seco un script build123d en el sandbox: devuelve {ok, volumen_mm3, bbox} o
    {ok:false, error} SIN tocar el documento. Itera la geometría sin crear/deshacer sólidos."""
    return json.dumps(_api("POST", "/api/script/test", json={"code": code}).json(), ensure_ascii=False)


@mcp.tool()
def redo() -> str:
    """Rehace la última operación deshecha."""
    return json.dumps(_scene_brief(_api("POST", "/api/redo").json()), ensure_ascii=False)


@mcp.tool()
def get_mates() -> str:
    """Mates de ensamblaje del documento (uniones persistentes entre piezas)."""
    return json.dumps(_api("GET", "/api/mates").json(), ensure_ascii=False)


@mcp.tool()
def check_assembly(with_autodetect: bool = True) -> str:
    """Validación de ensamblaje por CONECTIVIDAD: ¿cada pieza tiene un camino de sujeción
    hasta el piso? Devuelve las piezas FLOTANTES (caerían bajo gravedad — eje suelto, rodillo
    sin sujetar, guarda sin tornillo, motor flotando) y las AISLADAS (sin ninguna unión).
    Determinista, sin motor de física. with_autodetect=True superpone (sin persistir) las
    uniones detectadas por geometría → responde 'si fijara todo lo que se toca, ¿qué seguiría
    flotando?'. Declara uniones reales con run_command(type='ground'|'fasten')."""
    payload = _api("POST", "/api/assembly/soundness", json={"with_autodetect": with_autodetect}).json()
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def autodetect_connections() -> str:
    """Propone uniones de ensamblaje desde la GEOMETRÍA (piezas que apoyan en el piso +
    pares en contacto por caja envolvente), para poblar la conectividad de un modelo que no
    la declara. Read-only: confirma las que quieras con run_command(type='ground'|'fasten').
    Heurística por AABB (propone, no impone)."""
    payload = _api("POST", "/api/assembly/autodetect", json={}).json()
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def declare_structure() -> str:
    """Auto-declara la ESTRUCTURA real de la máquina (anclajes al piso + uniones de soporte) como
    comandos PERSISTIDOS, de forma INTELIGENTE (grafo de soporte dirigido): NO fija las piezas que
    cuelgan sin nada debajo (p. ej. rodillos de retorno). Idempotente (no duplica lo ya declarado).
    Después, `gravity_test(with_autodetect=False)` es la prueba EXACTA: solo cae lo de verdad suelto.
    Para corregir, borra una unión con `delete_connection(name)`. Devuelve el conteo y la lista de
    uniones declaradas (con sus nombres)."""
    _api("POST", "/api/assembly/declare")  # persiste; ignoramos el payload de escena (grande)
    conn = _api("GET", "/api/connectivity").json()
    return json.dumps(
        {"grounds": len(conn["grounds"]), "fasteners": len(conn["fasteners"]),
         "detalle": conn}, ensure_ascii=False)


@mcp.tool()
def get_connections() -> str:
    """Uniones de ensamblaje DECLARADAS (persistidas) del documento: fijadores (a↔b) y anclajes a
    tierra, con sus nombres (para borrarlas con delete_connection). Read-only."""
    return json.dumps(_api("GET", "/api/connectivity").json(), ensure_ascii=False)


@mcp.tool()
def delete_connection(name: str) -> str:
    """Borra una unión declarada por su NOMBRE (un fijador o un anclaje a tierra) — para corregir el
    auto-declarado (quitar una unión falsa). Consulta los nombres con get_connections."""
    try:
        _api("DELETE", f"/api/fasteners/{name}")
        return json.dumps({"borrado": name, "tipo": "fijador"}, ensure_ascii=False)
    except Exception:  # noqa: BLE001 — si no es fijador, prueba como anclaje
        _api("DELETE", f"/api/grounds/{name}")
        return json.dumps({"borrado": name, "tipo": "anclaje"}, ensure_ascii=False)


@mcp.tool()
def gravity_test(
    with_autodetect: bool = True, exclude: list[str] | None = None,
    seconds: float = 2.0, gravity: float = 9.81, path: str | None = None,
) -> str:
    """Simula la GRAVEDAD sobre TODA la máquina (cuerpos rígidos + colisión por casco
    convexo, motor MuJoCo) y reporta qué piezas SE CAEN y cuáles aguantan. A diferencia
    del chequeo estático, la FÍSICA decide si una pieza no-sujeta REPOSA sobre algo firme
    (no cae) o cuelga en el aire (cae) — resuelve "quién aguanta a quién". with_autodetect
    usa el contacto geométrico como estructura sujeta; `exclude` trata esas piezas como NO
    sujetas ('¿y si a esta le falta el tornillo?') para ver si se caen. Si das `path`,
    guarda además un GIF animado de la caída. Read-only: NO modifica el modelo."""
    from pathlib import Path

    body = {"with_autodetect": with_autodetect, "exclude": exclude or [],
            "seconds": seconds, "gravity": gravity}
    summary = _api("POST", "/api/assembly/stability", json=body).json()
    out = {k: summary.get(k) for k in ("n_grounded", "n_dynamic", "fell", "estables", "settled", "mensaje")}
    if path:
        gif = _api("POST", "/api/assembly/stability.gif", json=body).content
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gif)
        out["gif"] = str(target)
        out["bytes"] = len(gif)
    return json.dumps(out, ensure_ascii=False)


@mcp.tool()
def get_motion() -> str:
    """Estudio de movimiento: fotogramas de juntas y duración."""
    return json.dumps(_api("GET", "/api/motion").json(), ensure_ascii=False)


@mcp.tool()
def get_agent_notes() -> str:
    """Lee la memoria de sesión del agente (notas del proyecto)."""
    return json.dumps(_api("GET", "/api/agent/notes").json(), ensure_ascii=False)


@mcp.tool()
def add_agent_note(text: str) -> str:
    """Añade una nota a la memoria de sesión del agente (tope 30, persiste en el proyecto)."""
    return json.dumps(_api("POST", "/api/agent/notes", json={"text": text}).json(), ensure_ascii=False)


@mcp.tool()
def list_revisions() -> str:
    """Lista las revisiones (instantáneas restaurables) del proyecto abierto."""
    return json.dumps(_api("GET", "/api/revisions").json(), ensure_ascii=False)


@mcp.tool()
def restore_revision(revision_id: int) -> str:
    """Restaura una revisión por id (red de seguridad tras ediciones arriesgadas)."""
    payload = _api("POST", f"/api/revisions/{revision_id}/restore").json()
    return json.dumps(_scene_brief(payload), ensure_ascii=False)


# ----------------------------------------------------- topología / selectores
@mcp.tool()
def get_topology(feature_id: str) -> str:
    """Caras y aristas de un sólido con su geometría descriptiva (tipo plano/cilíndrico,
    centro, normal/eje, área; longitud, dirección, radio de aristas). Úsalo para ELEGIR el
    selector declarativo antes de fillet/chamfer/drill/add_mate: caras por orientación
    (normal) → 'cara'/'direccion'; aristas largas → 'longitud'; cerca de un punto → 'cerca'.
    Los 'idx' son solo referencia: la selección sigue siendo declarativa, no por id."""
    return json.dumps(_api("GET", f"/api/features/{feature_id}/topology").json(), ensure_ascii=False)


@mcp.tool()
def get_requirements() -> str:
    """BASES DE DISEÑO del proyecto (requisitos guardados: carga_kg, largo/ancho/
    alto_paquete_mm, velocidad_m_s, inclinacion_deg, producto, entorno, normativa…).
    engineering_check y la memoria de cálculo los usan como defaults. Read-only."""
    return json.dumps(_api("GET", "/api/requirements").json(), ensure_ascii=False)


@mcp.tool()
def set_requirements(fields: dict) -> str:
    """Guarda las BASES DE DISEÑO del proyecto (reemplaza el dict completo; {} borra).
    Claves numéricas de convención: carga_kg, largo_paquete_mm, ancho_paquete_mm,
    alto_paquete_mm, velocidad_m_s, inclinacion_deg, temperatura_c. Texto libre:
    producto, entorno, normativa, notas. Con esto `engineering_check()` y `calc_report()`
    funcionan SIN argumentos y validan contra LO PEDIDO. Se persisten con el proyecto."""
    return json.dumps(
        _api("PUT", "/api/requirements", json={"fields": fields}).json(), ensure_ascii=False
    )


@mcp.tool()
def auto_group(dry_run: bool = False) -> str:
    """Auto-agrupa el modelo en SUB-ENSAMBLAJES por subsistema (Estructura,
    Transmision, Rodillos y tambores, Banda y mesa, Rodamientos, Tornilleria,
    Guardas…) usando la heurística super-comando → catálogo → palabra clave del
    nombre. Idempotente (no duplica grupos ni re-agrupa lo agrupado); `dry_run=true`
    solo PROPONE para revisar antes. Úsalo una vez para poblar un modelo existente;
    después refina con create_group/edit_command."""
    payload = _api("POST", "/api/assembly/auto-group", json={"dry_run": dry_run}).json()
    if "features" in payload:
        out = _scene_brief(payload, "summary")
        out["proposal"] = payload.get("proposal")
        out["created"] = payload.get("created")
        return json.dumps(out, ensure_ascii=False)
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def get_groups() -> str:
    """GRUPOS / sub-ensamblajes del documento: nombre, padre (anidación), rol, comandos
    miembro y members faltantes. Los grupos se CREAN con run_command(type='create_group',
    params={name, members:[command_ids], parent?, role?}) — la membresía es por COMANDO
    (estable: las instancias nuevas de un patrón editado entran solas) — y se MUEVEN
    enteros con run_command(type='transform_group', {group, translate, rotate}).
    isolate/highlight/fit de render_view, pick_point, drawing y assembly_manual aceptan
    NOMBRES de grupo directamente. Read-only."""
    return json.dumps(_api("GET", "/api/groups").json(), ensure_ascii=False)


@mcp.tool()
def get_mass_properties(ids: list[str] | None = None) -> str:
    """Masa (kg), centro de gravedad (mm) y bbox por pieza y del CONJUNTO. Sin `ids`
    analiza todas las piezas visibles; con ids solo esas (aunque estén ocultas). El
    catálogo pesa por su ficha (dato de placa); lo a-medida por volumen × densidad del
    material resuelto. Úsalo para vuelco/equilibrio (¿el COG cae dentro de la base?),
    repartos de carga y BOM de pesos. Read-only."""
    params = {"ids": ",".join(ids)} if ids else None
    return json.dumps(_api("GET", "/api/mass-properties", params=params).json(), ensure_ascii=False)


@mcp.tool()
def measure(a: str, b: str, face_a: dict | None = None, face_b: dict | None = None) -> str:
    """Distancia mínima (mm) y puntos más cercanos entre dos sólidos a y b (ids). El gap real
    deja de ser ensayo-error. Opcional: face_a/face_b = selector declarativo (mode cara/direccion/
    longitud/cerca) para medir contra UNA cara concreta. 0 = se tocan o solapan. Read-only."""
    body: dict = {"a": a, "b": b}
    if face_a:
        body["face_a"] = face_a
    if face_b:
        body["face_b"] = face_b
    return json.dumps(_api("POST", "/api/measure", json=body).json(), ensure_ascii=False)


@mcp.tool()
def near(point: list[float], radius: float = 50.0) -> str:
    """Features cuya caja envolvente está a ≤ radius mm de `point` ([x,y,z]), de más cerca a más
    lejos. Consulta espacial: '¿qué pieza hay por aquí?'. Combínalo con pick_point. Read-only."""
    return json.dumps(
        _api("GET", "/api/near", params={"point": json.dumps(point), "radius": radius}).json(),
        ensure_ascii=False,
    )


@mcp.tool()
def pick_point(
    u: float,
    v: float,
    view: str = "iso",
    fit_ids: list[str] | None = None,
    zoom: float = 1.0,
    azimuth: float | None = None,
    elevation: float | None = None,
    isolate: list[str] | None = None,
    section: str | None = None,
    roll: float = 0.0,
    pan: list[float] | None = None,
) -> str:
    """PÍXEL→3D: 'señala' un punto en un render y obtén qué pieza/cara hay ahí. (u,v) son
    coordenadas NORMALIZADAS [0,1] de la imagen (0,0 = arriba-izquierda). Devuelve la feature/cara
    cuyo centro proyectado queda más cerca + su coordenada mundo (snap a geometría con la MISMA
    cámara del render VTK). Así seleccionas/ubicas apuntando en vez de calcular coordenadas.
    IMPORTANTE: pasa los MISMOS `view`/`azimuth`/`elevation`/`roll`/`pan`/`fit_ids`/`zoom` que usaste
    en `render_view` para esa imagen → así el píxel coincide con lo que viste (incluido el ángulo
    libre, el roll y el encuadre desplazado). Si renderizaste AISLADO o SECCIONADO, pasa también los
    mismos `isolate`/`section`: el pick solo considerará ese subconjunto recortado igual que la foto
    (coherencia render↔pick). Read-only."""
    params: dict = {"u": u, "v": v, "view": view, "zoom": zoom}
    if fit_ids:
        params["fit"] = ",".join(fit_ids)
    if azimuth is not None:
        params["azimuth"] = azimuth
    if elevation is not None:
        params["elevation"] = elevation
    if isolate:
        params["isolate"] = ",".join(isolate)
    if section:
        params["section"] = section
    if roll:
        params["roll"] = roll
    if pan and len(pan) == 2:
        params["pan"] = ",".join(str(x) for x in pan)
    return json.dumps(_api("GET", "/api/pick", params=params).json(), ensure_ascii=False)


# ----------------------------------------------------- despiece de fabricación
@mcp.tool()
def cut_list() -> str:
    """Lista de corte de fabricación: piezas a CORTAR (a-medida + catálogo cortable)
    agrupadas por (material, espesor, ancho, largo) con cantidad y área; totales por
    material (m²/ml); y cédula de HERRAJE (catálogo no cortable: bisagras/tornillos/
    correderas...). Une los sólidos de las uniones (una hoja = 2 largueros). Read-only.
    El CSV está en GET /api/cutlist.csv."""
    return json.dumps(_api("GET", "/api/cutlist.json").json(), ensure_ascii=False)


@mcp.tool()
def nesting(
    mode: str = "2d", stock_w: float = 2440.0, stock_h: float = 1220.0,
    material: str | None = None, kerf: float = 3.0,
) -> str:
    """Optimización de corte (nesting) para minimizar desperdicio. `mode`: "2d" (tableros/
    vidrio en planchas stock_w×stock_h) o "1d" (barras/largueros de largo stock_w). `material`
    filtra (madera/vidrio/acero...). Devuelve nº de planchas/barras y % de desperdicio; el
    plano del acomodo está en GET /api/nesting.svg|dxf (mismos params). Read-only."""
    params: dict = {"mode": mode, "stock_w": stock_w, "stock_h": stock_h, "kerf": kerf}
    if material:
        params["material"] = material
    return json.dumps(_api("GET", "/api/nesting.json", params=params).json(), ensure_ascii=False)


@mcp.tool()
def drawing_set(path: str, template: str = "generico", sheet: str = "A3", shaded: bool = False) -> str:
    """Genera el JUEGO DE PLANOS profesional (PDF multipágina): conjunto con BOM + 1 lámina
    por pieza ACOTADA + cédula de corte/herraje, y lo guarda en `path` (.pdf). `template`:
    carpinteria/weldment/chapa/generico. `shaded=true`: el conjunto lleva isométrica SOMBREADA
    a color (estilo Inventor). Devuelve nº de bytes guardados."""
    import pathlib

    resp = _api("GET", "/api/drawingset.pdf",
                params={"template": template, "sheet": sheet, "shaded": shaded})
    pathlib.Path(path).write_bytes(resp.content)
    return json.dumps({"ok": True, "path": path, "bytes": len(resp.content)}, ensure_ascii=False)


@mcp.tool()
def calc_report(path: str, carga_kg: float | None = None, largo_paquete_mm: float | None = None,
                ancho_paquete_mm: float | None = None, velocidad_m_s: float | None = None,
                rev: str = "A", sheet: str = "A4") -> str:
    """Genera la MEMORIA DE CÁLCULO (PDF multipágina) y la guarda en `path` (.pdf): portada
    con BASES DE DISEÑO + índice de verificaciones + VEREDICTO (aprobado/con avisos/no
    conforme), y una página por verificación con datos de entrada, FÓRMULA, sustitución
    numérica, criterio de aceptación y FACTOR DE SEGURIDAD (motorización, par, flecha,
    flexión de eje, pernos, soldaduras, L10, pandeo, vuelco…). Es el entregable que
    JUSTIFICA el diseño ante el cliente. Sin argumentos usa los REQUISITOS guardados
    (set_requirements); exige al menos carga y largo de paquete (aquí o en requisitos)."""
    import pathlib

    params: dict = {"rev": rev, "sheet": sheet}
    for key, val in (("carga_kg", carga_kg), ("largo_paquete_mm", largo_paquete_mm),
                     ("ancho_paquete_mm", ancho_paquete_mm), ("velocidad_m_s", velocidad_m_s)):
        if val is not None:
            params[key] = val
    resp = _api("GET", "/api/calc-report.pdf", params=params)
    pathlib.Path(path).write_bytes(resp.content)
    return json.dumps({"ok": True, "path": path, "bytes": len(resp.content)}, ensure_ascii=False)


@mcp.tool()
def quotation(path: str, margin_pct: float = 25.0, tax_pct: float = 0.0,
              currency: str | None = None, fx: float | None = None) -> str:
    """Genera la COTIZACIÓN del proyecto (PDF multipágina) y la guarda en `path` (.pdf):
    resumen económico (catálogo vs fabricación, desglose por categoría, margen %,
    impuesto % opcional, PRECIO DE VENTA, ítem más costoso, notas comerciales) + detalle
    de partidas = el BOM costeado completo con la FUENTE de cada precio (referencial de
    catálogo / estimación). Complemento comercial de calc_report (la memoria justifica
    el diseño; la cotización lo VENDE). Precios referenciales — confirmar con proveedor."""
    import pathlib

    params: dict = {"margin_pct": margin_pct, "tax_pct": tax_pct}
    if currency:
        params["currency"] = currency
    if fx is not None:
        params["fx"] = fx
    resp = _api("GET", "/api/quote.pdf", params=params)
    pathlib.Path(path).write_bytes(resp.content)
    return json.dumps({"ok": True, "path": path, "bytes": len(resp.content)}, ensure_ascii=False)


@mcp.tool()
def assembly_manual(path: str, sheet: str = "A3", isolate: list[str] | None = None,
                    title: str | None = None) -> str:
    """Genera el MANUAL DE ENSAMBLAJE paso a paso (instructivo de montaje, estilo Inventor/IKEA) en
    PDF MULTIPÁGINA y lo guarda en `path` (.pdf): portada con la SECUENCIA de montaje + 1 lámina por
    PASO. Cada paso muestra el render 3D acumulado (las piezas NUEVAS resaltadas a color, lo ya
    montado en gris fantasma, cámara estable) + la lista de piezas/herraje del paso (con norma) + la
    instrucción. La secuencia se DERIVA del modelo: orden del log de comandos (cómo se armó) +
    agrupación por familias de catálogo (todo el herraje junto) y por nombre de pieza. A diferencia
    del plano de CONJUNTO (drawing cutlist) que solo lista piezas, esto EXPLICA el armado paso a paso.
    `isolate` (lista de ids o NOMBRES de grupo) acota el manual a un SUB-ENSAMBLAJE (p. ej. una hoja: sus tablas + vidrio
    + bisagras) sin tocar el documento; `title` rotula la portada/archivo. Devolverá nº de bytes.
    (El render tarda; ~40 s en un modelo de ~80 piezas, mucho menos en un sub-ensamblaje.) Read-only."""
    import pathlib

    params: dict = {"sheet": sheet}
    if isolate:
        params["isolate"] = ",".join(isolate)
    if title:
        params["title"] = title
    resp = _api("GET", "/api/assembly-manual.pdf", params=params)
    pathlib.Path(path).write_bytes(resp.content)
    return json.dumps({"ok": True, "path": path, "bytes": len(resp.content)}, ensure_ascii=False)


@mcp.tool()
def drawing(spec: dict, path: str | None = None) -> str:
    """Plano profesional por INTENCIÓN (el moat agente-nativo): UNA spec declara qué quieres y
    el motor lo dibuja con cotas/cortes/detalles/cajetín pro. spec = {sheet:"A3", section:"x"/"y"/"z",
    detail:{view,u,v,radius,scale}, dims:[ids] (tamaño), datum_dims:[ids] (posición desde la base),
    bom:true, cutlist:true (tabla DESPIECE con L×A×E por tabla, globos en el alzado — para
    ENSAMBLAJES, no solo el bbox), hardware:true (añade CÉDULA DE HERRAJE bajo el despiece, con
    columna Norma — DIN/ISO/EN/ASTM — para los normalizados),
    auto_dims:true (acota SOLO la posición x/y de cada agujero desde el datum — para FABRICAR),
    interface_dims:true (cotas de MONTAJE: pitch centro-a-centro del patrón de agujeros + luz total — para acoplar),
    explode:{axis:"x"/"y"/"z",factor} (VISTA EXPLOSIONADA: piezas separadas + globos de secuencia),
    shaded:true (isométrica SOMBREADA a color, estilo Inventor, embebida en la lámina; pdf/svg),
    notes:["...","..."] (bloque de NOTAS generales en la lámina),
    assembly_notes:[] (auto-genera NOTAS DE MONTAJE desde el herraje) o ["..."] (notas explícitas),
    member_detail:{member,pick:[t,w,l],locate:[ids],scale,name} (vista de DETALLE de UNA tabla con
    sus mortajas/bisagras acotadas desde la base; reemplaza la planta),
    isolate:[ids] (solo esas piezas, sin tocar el documento), format:"pdf"/"svg"/"dxf",
    meta:{drawing_no,material,...}}. Con `path` guarda el archivo (pdf/dxf/svg); si format="svg" y sin
    path devuelve el SVG (úsalo con show_widget para VER el plano inline). Read-only."""
    import pathlib

    resp = _api("POST", "/api/drawing/spec", json=spec)
    if path:
        pathlib.Path(path).write_bytes(resp.content)
        return json.dumps({"ok": True, "path": path, "bytes": len(resp.content)}, ensure_ascii=False)
    if spec.get("format") == "svg":
        return resp.text
    return json.dumps(
        {"ok": True, "bytes": len(resp.content), "hint": "pasa path=... para guardar el pdf/dxf"},
        ensure_ascii=False,
    )


# ------------------------------------------------------------------ visibilidad
@mcp.tool()
def set_visibility(feature_id: str, visible: bool) -> str:
    """Muestra u oculta un sólido individual (útil para aislar antes de render_view)."""
    payload = _api("POST", f"/api/features/{feature_id}/visibility", json={"visible": visible}).json()
    return json.dumps(_scene_brief(payload), ensure_ascii=False)


@mcp.tool()
def set_visibility_bulk(feature_ids: list[str], visible: bool) -> str:
    """Muestra u oculta varios sólidos a la vez (patrón aislar / mostrar todo)."""
    payload = _api("POST", "/api/features/visibility", json={"ids": feature_ids, "visible": visible}).json()
    return json.dumps(_scene_brief(payload), ensure_ascii=False)


# ------------------------------------------------------------------ expresiones
@mcp.tool()
def resolve_expression(expression: str) -> str:
    """Evalúa una expresión (=expr) contra las variables del proyecto SIN modificar nada;
    devuelve {ok, value} o {ok:false, error}. Para comprobar una fórmula antes de usarla."""
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
    rotula "Ø35 h7 (0/-0.025)" y engineering_check verifica el asiento. Read-only."""
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
    """FEA ESTÁTICO LINEAL de UNA pieza (V5.6): malla tet P2 (gmsh) + elasticidad
    lineal (scikit-fem). Devuelve σ_vm máx (MPa) con su ubicación, desplazamiento
    máx (mm), FS = σy/σ_vm (criterio: ≥2 estático, <1.2 sobrecargada) y las
    HIPÓTESIS declaradas; el resumen se GUARDA y entra solo a la memoria de cálculo
    (con aviso automático si la geometría cambia después). `fixed` y
    `loads[].selector` son selectores declarativos de CARAS ({mode: cara|direccion|
    cerca…} — elige con get_topology); cada load lleva force_n=[Fx,Fy,Fz] (fuerza
    TOTAL en N, repartida sobre la cara) O pressure_mpa (normal entrante);
    self_weight añade el peso propio. `fringe_path` guarda el PNG del campo von
    Mises (mapa de colores + escala) — MÍRALO: te dice DÓNDE está el esfuerzo.
    Material/σy salen de la pieza (si el material no tiene σy tabulado, pasa
    yield_mpa). GOTCHA: σ_vm máx pegado al empotramiento suele ser concentración
    numérica del encastre ideal (el retorno lo marca con max_en_encastre).
    Read-only sobre la geometría; tarda unos segundos (malla gruesa por defecto,
    afina con mesh_size_mm)."""
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


if __name__ == "__main__":
    mcp.run()
