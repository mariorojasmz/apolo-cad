"""Tools MCP de validación: interferencias, chequeo de ingeniería, render y ensayo fantasma
(`preview`).

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

from mcp.server.fastmcp import Image


def registrar(mcp, _api) -> dict[str, Callable]:
    """Registra en `mcp` (el del servidor que corre) las tools de `validacion` y las
    devuelve por nombre para que `mcp_server` las re-exporte."""

    @mcp.tool()
    def check_interference(joint_values: dict | None = None, ids: list[str] | None = None,
                           desde: int = 0, excluir_declaradas: bool = False) -> str:
        """Interferencias entre sólidos (booleanas OCCT). Con joint_values {junta: valor}
        comprueba la colisión del mecanismo EN POSE. Con `ids` (feature_ids o NOMBRES DE GRUPO)
        ACOTA a las parejas donde participa al menos uno de ellos (O(k·n) en vez de O(n²)):
        valida TU zona de trabajo tras una operación en vez de la máquina entera. Hasta 400 parejas
        por llamada: con más, `truncado` suma `parejas_sin_revisar`, `desde_siguiente` y
        `como_acotar` (la llamada siguiente); `desde` pide esa página. `excluir_declaradas=true` deja
        fuera los pares con unión declarada (como la puerta)."""
        body = {"joint_values": joint_values or {}, "interference_desde": desde,
                "excluir_declaradas": excluir_declaradas, **({"interference_ids": ids} if ids else {})}
        payload = _api("POST", "/api/checks", json=body).json()
        return json.dumps(payload["interferencias"], ensure_ascii=False)

    @mcp.tool()
    def engineering_check(
        carga_kg: float | None = None, largo_paquete_mm: float | None = None,
        velocidad_m_s: float | None = None, ancho_paquete_mm: float | None = None,
        conveyor: dict | None = None, conveyor_solid_ids: list[str] | None = None,
        grupo: str | None = None, solo_fallas: bool = False, detail: str = "summary",
    ) -> str:
        """Valida el modelo con criterio de ingeniería. Devuelve DOS bloques: `ingenieria`
        (reglas del transportador: apoyo del paquete, capacidad de rodillo, ancho útil,
        motorización por CONSTRUCCIÓN — CEMA slider-bed si banda sobre cama / ISO 5048-DIN
        22101 si banda sobre rodillos —, par + par de arranque, adherencia del tambor
        motriz Euler-Eytelwein con la T2 mínima que el tensor debe garantizar, flecha del
        bastidor, flexión del eje) y `estructura` (chequeo UNIVERSAL de cualquier ensamblaje: uniones
        apernadas vs ISO 898-1, soldaduras, vida L10 de rodamientos, pandeo de patas,
        vuelco). Sin argumentos usa los REQUISITOS guardados del proyecto (set_requirements);
        los parámetros explícitos ganan. Sin `conveyor` valida la faja del documento; con
        `conveyor` (dict {largo,ancho,altura,paso,rodillo,motor}) valida ANTES de construir;
        `conveyor_solid_ids` marca qué sólidos forman la faja. `grupo` filtra por familia de regla
        ('unión apernada', 'soldadura', 'flecha de viga', 'transmisión por cadena'…) y `solo_fallas`
        deja lo que no está ok. `detail`: "summary" (def.) agrupa lo repetido (las reglas de una
        unión, por su par de piezas) en UNA línea (`n`, estado y detalle del PEOR caso, `peor`; lo ok
        sin detalle salvo con `grupo`), suma `conteo` por estado y sólo trae `calc` (fórmula,
        criterio, FS) donde da error; "full" lo da todo."""
        body = {"carga_kg": carga_kg, "largo_paquete_mm": largo_paquete_mm,
                "ancho_paquete_mm": ancho_paquete_mm, "conveyor": conveyor,
                "conveyor_solid_ids": conveyor_solid_ids, "grupo": grupo, "solo_fallas": solo_fallas,
                "resumen": detail != "full"}
        if velocidad_m_s is not None:
            body["velocidad_m_s"] = velocidad_m_s
        payload = _api("POST", "/api/checks", json=body).json()
        claves = ["ingenieria", "estructura"] + (["conteo"] if "conteo" in payload else [])
        return json.dumps({k: payload.get(k) for k in claves}, ensure_ascii=False)

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
        highlight_ids resalta esos sólidos y atenúa el resto; show_axes dibuja un triedro X/Y/Z en la
        esquina (no cambia el encuadre); show_bbox la caja envolvente de lo resaltado. Un subgrupo
        vale también por su último tramo («Rodillos» = «Transportador/Rodillos»).
        section ∈ {x,y,z} corta el modelo a la mitad de
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
        for clave, lista in (("highlight", highlight_ids), ("fit", fit_ids), ("isolate", isolate)):
            if lista:
                params[clave] = ",".join(lista)
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
        params.update({k: "true" for k, v in (("xray", xray), ("labels", labels)) if v})
        if roll:
            params["roll"] = roll
        if pan and len(pan) == 2:
            params["pan"] = ",".join(str(x) for x in pan)
        response = _api("GET", "/api/render.png", params=params)
        return Image(data=response.content, format="png")

    @mcp.tool()
    def preview(
        actions: list[dict], view: str = "iso", labels: bool = False,
        section: str | None = None, data: bool = False,
    ):
        """GHOST: aplica `actions` (mismo formato que run_batch: [{type, params}, …]) sobre una
        COPIA del documento SIN tocar el modelo real — ensaya una colocación y equivocarte sale
        gratis (sin escombro de log). Dos modos:
        - `data=false` (default): devuelve el PNG con los sólidos nuevos resaltados (para VERLO).
          `labels` rotula ids; `section` ∈ {x,y,z} corta para ver dentro.
        - `data=true` (V6.5d): devuelve JSON `{fantasmas:[{name,bbox,volumen_mm3}], colisiones_
          nuevas:[{a,b,tipo,volumen_mm3}]}` — las colisiones SOLO de los fantasmas (contra la escena
          y entre sí). Prueba N colocaciones con datos EXACTOS y compromete la buena con run_batch,
          sin mutar el documento. (No trae imagen; usa data=false o render_view para verla.)"""
        body: dict = {"actions": actions, "view": view, "labels": labels, "data": data}
        if section:
            body["section"] = section
        response = _api("POST", "/api/commands/preview", json=body)
        if data:
            return json.dumps(response.json(), ensure_ascii=False)
        return Image(data=response.content, format="png")

    return {f.__name__: f for f in (check_interference, engineering_check, render_view, preview,)}
