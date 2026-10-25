"""Tools MCP del despiece de fabricación y los entregables: lista de corte, nesting, juego de
planos, memoria de cálculo, cotización, manual de ensamblaje y plano por intención.

Bloque de `mcp_server.py` movido tal cual, con 4 espacios más de sangría (plan
partir-nucleo-congelado, F1). `mcp_server` llama `registrar` EN EL LUGAR del bloque con
`globals().update(...)`: el orden de `list_tools()` no cambia y cada tool sigue siendo un
atributo de `apolo.mcp_server`. NO importa `apolo.mcp_server` (con `-m` el servidor es
`__main__`: `tests/test_mcp_registro.py`). `_api` y `_submit_and_wait`: lambdas que buscan el del servidor en
CADA llamada (un test que lo parchea por nombre también llega aquí). Importa lo que nombran
las anotaciones: FastMCP las evalúa.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from . import entregable


def registrar(mcp, _api, _submit_and_wait) -> dict[str, Callable]:
    """Registra en `mcp` (el del servidor que corre) las tools de `fabricacion` y las
    devuelve por nombre para que `mcp_server` las re-exporte."""

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
        a color (estilo Inventor). Devuelve nº de bytes guardados. ¿DWG para clientes AutoCAD?
        GET /api/drawingset.dwg = ZIP con un DWG por lámina (V5.9, requiere ODA File Converter).
        Si tarda, RECIBO {"job"}: get_job lo guarda en `path` al terminar."""
        return entregable.pedir(_api, _submit_and_wait, "/api/drawingset.pdf",
                                {"template": template, "sheet": sheet, "shaded": shaded}, path)

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
        (set_requirements); exige al menos carga y largo de paquete (aquí o en requisitos).
        Si tarda, RECIBO {"job"}: get_job lo guarda en `path` al terminar."""
        params: dict = {"rev": rev, "sheet": sheet}
        for key, val in (("carga_kg", carga_kg), ("largo_paquete_mm", largo_paquete_mm),
                         ("ancho_paquete_mm", ancho_paquete_mm), ("velocidad_m_s", velocidad_m_s)):
            if val is not None:
                params[key] = val
        return entregable.pedir(_api, _submit_and_wait, "/api/calc-report.pdf", params, path)

    @mcp.tool()
    def quotation(path: str, margin_pct: float = 25.0, tax_pct: float = 0.0,
                  currency: str | None = None, fx: float | None = None) -> str:
        """Genera la COTIZACIÓN (PDF multipágina) y la guarda en `path` (.pdf): resumen económico
        (catálogo vs fabricación, desglose por categoría, margen %, impuesto % opcional, PRECIO DE
        VENTA, notas) + detalle de partidas con la FUENTE de cada precio. Complemento comercial de
        calc_report. Devuelve `precio` (moneda, costo_directo, margen, impuesto si hay,
        precio_venta: las cifras del resumen) junto al path, sin leer el PDF. Si algo se cobra dos
        veces (dispositivo sin ligar a su pieza 3D) o no se cobra (cable 3D sin add_cable), devuelve
        `avisos` con su `monto_en_riesgo_usd` y cómo arreglarlo; el PDF los lista en su hoja 2.
        Precios referenciales: confirmar con proveedor."""
        params: dict = {"margin_pct": margin_pct, "tax_pct": tax_pct}
        if currency:
            params["currency"] = currency
        if fx is not None:
            params["fx"] = fx
        resp = _api("GET", "/api/quote.pdf", params=params)
        entregable.escribir(path, resp.content)
        return json.dumps({"ok": True, "path": path, "bytes": len(resp.content),
                           **entregable.precio_de(resp), **entregable.avisos_de_cobro(resp)},
                          ensure_ascii=False)

    @mcp.tool()
    def assembly_manual(path: str, sheet: str = "A3", isolate: list[str] | None = None,
                        title: str | None = None) -> str:
        """Genera el MANUAL DE ENSAMBLAJE paso a paso (instructivo de montaje, estilo Inventor/IKEA) en
        PDF MULTIPÁGINA y lo guarda en `path` (.pdf): portada con la SECUENCIA de montaje + 1 lámina por
        PASO. Cada paso muestra el render 3D acumulado (las piezas NUEVAS resaltadas a color, lo ya
        montado en gris fantasma, cámara estable) + la lista de piezas/herraje del paso (con norma) + la
        instrucción. La secuencia sale de las uniones DECLARADAS (fasten/ground): lo soldado primero,
        cada pieza tras aquella a la que se fija y lo que tapa al final (sin ellas, del log). A diferencia
        del plano de CONJUNTO (drawing cutlist) que solo lista piezas, esto EXPLICA el armado paso a paso.
        `isolate` (lista de ids o NOMBRES de grupo) acota el manual a un SUB-ENSAMBLAJE (p. ej. una hoja: sus tablas + vidrio
        + bisagras) sin tocar el documento; `title` rotula la portada/archivo. Devolverá nº de bytes.
        (El render tarda; ~40 s en un modelo de ~80 piezas, mucho menos en un sub-ensamblaje.) Read-only.
        Si tarda, RECIBO {"job"}: get_job lo guarda en `path` al terminar."""
        params: dict = {"sheet": sheet}
        if isolate:
            params["isolate"] = ",".join(isolate)
        if title:
            params["title"] = title
        return entregable.pedir(_api, _submit_and_wait, "/api/assembly-manual.pdf", params, path)

    @mcp.tool()
    def drawing(spec: dict, path: str | None = None) -> str:
        """Plano profesional por INTENCIÓN (el moat agente-nativo): UNA spec declara qué quieres y
        el motor lo dibuja con cotas/cortes/detalles/cajetín pro. spec = {sheet:"A3", section:"x"/"y"/"z",
        detail:{view,u,v,radius,scale}, dims:[ids] (tamaño), datum_dims:[ids] (posición desde la base),
        bom:true, cutlist:true (tabla DESPIECE con L×A×E por tabla, globos en el alzado — para ENSAMBLAJES, no
        solo el bbox), hardware:true (añade CÉDULA DE HERRAJE bajo el despiece, con columna Norma — DIN/ISO/EN/ASTM),
        auto_dims:true (acota SOLO la posición x/y de cada agujero desde el datum — para FABRICAR),
        interface_dims:true (cotas de MONTAJE: pitch centro-a-centro del patrón de agujeros + luz total — para acoplar),
        explode:{axis:"x"/"y"/"z",factor} (VISTA EXPLOSIONADA: piezas separadas + globos de secuencia),
        shaded:true (isométrica SOMBREADA a color, estilo Inventor, embebida en la lámina; pdf/svg),
        notes:["...","..."] (bloque de NOTAS generales en la lámina),
        assembly_notes:[] (auto-genera NOTAS DE MONTAJE desde el herraje) o ["..."] (notas explícitas),
        member_detail:{member,pick:[t,w,l],locate:[ids],scale,name} (vista de DETALLE de UNA tabla con sus
        mortajas/bisagras acotadas desde la base; reemplaza la planta), isolate:[ids] (solo esas piezas, sin
        tocar el documento), format:"pdf"/"svg"/"dxf"/"dwg" (dwg V5.9: requiere ODA File Converter instalado
        — sin él, 400 con la instrucción), hole_fits:{"20":"H7"} y hole_threads:{"6.8":"M8"} (overrides de
        los callouts de ajuste/rosca — los drill_hole con fit/thread ya se rotulan SOLOS: "Ø20 H7 (+0.021/0)" y "M8 - 6H (broca Ø6.8)"
        + cosmético ISO 6410 en capa DXF ROSCA), meta:{drawing_no,material,...}}.
        ESQUEMA ISO 1219 del aire del carril (no un plano): {esquema:"neumatico", format, sheet, neumatica:{ciclo:
        ["-MM1",...] (orden de los cilindros), detectores:{"-BG1":{cilindro:"-MM1", en:"atras"|"adelante"}}}}.
        Con `path` guarda el archivo; si format="svg" y sin path devuelve el SVG (show_widget lo muestra). Read-only.
        Si tarda, RECIBO {"job"}: get_job lo guarda en `path` al terminar."""
        return entregable.plano(_api, _submit_and_wait, spec, path)

    return {f.__name__: f for f in (
        cut_list, nesting, drawing_set, calc_report, quotation, assembly_manual, drawing,
    )}
