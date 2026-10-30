"""Tools MCP de topología y consultas: selectores, requisitos, grupos, masas, medición, `near`,
`verify` y `pick_point`.

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


def registrar(mcp, _api) -> dict[str, Callable]:
    """Registra en `mcp` (el del servidor que corre) las tools de `topologia` y las
    devuelve por nombre para que `mcp_server` las re-exporte."""

    @mcp.tool()
    def get_topology(feature_id: str, only: str | None = None, min_mm: float = 0.0) -> str:
        """Caras y aristas de un sólido con su geometría descriptiva (tipo plano/cilíndrico,
        centro, normal/eje, área; longitud, dirección, radio de aristas). Úsalo para ELEGIR el
        selector declarativo antes de fillet/chamfer/drill/add_mate: caras por orientación
        (normal) → 'cara'/'direccion'; aristas largas → 'longitud'; cerca de un punto → 'cerca'.
        Los 'idx' son solo referencia: la selección sigue siendo declarativa, no por id.
        A ESCALA (piezas con muchos taladros): `only` ∈ {caras|aristas|anclas} trae solo esa
        familia; `min_mm` omite aristas más cortas que ese valor y caras menores que min_mm²
        (filtra los micro-fillets/agujeros diminutos, el grueso del ruido)."""
        params: dict = {}
        if only:
            params["only"] = only
        if min_mm:
            params["min_mm"] = min_mm
        return json.dumps(
            _api("GET", f"/api/features/{feature_id}/topology", params=params).json(),
            ensure_ascii=False,
        )

    @mcp.tool()
    def get_requirements() -> str:
        """BASES DE DISEÑO del proyecto (requisitos guardados: carga_kg, largo/ancho/
        alto_paquete_mm, velocidad_m_s, inclinacion_deg, producto, entorno, normativa…).
        engineering_check y la memoria de cálculo los usan como defaults. Trae también
        `comercial` (titulo, cliente, numero, revision de la cotización) si hay. Read-only."""
        return json.dumps(_api("GET", "/api/requirements").json(), ensure_ascii=False)

    @mcp.tool()
    def set_requirements(fields: dict | None = None, comercial: dict | None = None) -> str:
        """Guarda las BASES DE DISEÑO del proyecto (reemplaza el dict completo; {} borra).
        Claves numéricas de convención: carga_kg, largo_paquete_mm, ancho_paquete_mm,
        alto_paquete_mm, velocidad_m_s, inclinacion_deg, temperatura_c. Texto libre:
        producto, entorno, normativa, notas. Sentido de marcha: sentido_transporte [x, y, z]
        (hacia dónde avanza el ramal de carga; la puerta resguarda sólo la cuña de ENTRADA de
        cada tambor) y reversible (sí/no: las dos cuñas). Vida L10 de una máquina que no es
        transportador: rpm_salida y carga_rodamiento_n (carga radial P por rodamiento, N); su
        factor de servicio: potencia_absorbida_kw (lo que absorbe en el eje de salida del
        reductor) o par_salida_nm. Servicio (el FS que se pide, AGMA): tipo_carga (uniforme |
        moderada | pesada) y horas_dia; sin ellos, 1,25. Equipo higiénico (alimentos, farma):
        higienico (sí/no; la puerta pide cada soldadura continua y cada tubo cerrado). Las
        funciones y sus alternativas NO van aquí: set_functions. Con esto `engineering_check()` y
        `calc_report()` funcionan SIN argumentos y validan contra LO PEDIDO. Se persisten con el proyecto.
        `comercial` = a quién va la COTIZACIÓN: {titulo, cliente, numero, revision} (texto;
        reemplaza el dict, {} borra); sin `fields`, los requisitos no se tocan."""
        if fields is None and comercial is None:
            return json.dumps({"error": "pasa `fields` (requisitos) o `comercial` "
                                        "(identificación de la cotización)"}, ensure_ascii=False)
        body: dict = {}
        if fields is not None:
            body["fields"] = fields
        if comercial is not None:
            body["comercial"] = comercial
        return json.dumps(_api("PUT", "/api/requirements", json=body).json(), ensure_ascii=False)

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
    def near(
        point: list[float] | None = None,
        feature: str | None = None,
        box: list[list[float]] | None = None,
        radius: float = 50.0,
        limit: int = 20,
    ) -> str:
        """Consulta espacial por caja envolvente, de más cerca a más lejos. Da EXACTAMENTE uno de:
        - `point` [x,y,z]: '¿qué pieza hay por aquí?' (combínalo con pick_point).
        - `feature` (id): '¿qué RODEA a X?' — distancia AABB-AABB al resto, excluyendo X.
        - `box` [[min_x,min_y,min_z],[max_x,max_y,max_z]]: '¿qué hay en esta REGIÓN?'.
        `radius` mm (radius=0 con box/feature = solo lo que lo toca) + `limit` (def. 20). Read-only."""
        params: dict = {"radius": radius, "limit": limit}
        if feature is not None:
            params["feature"] = feature
        elif box is not None:
            params["box"] = json.dumps(box)
        elif point is not None:
            params["point"] = json.dumps(point)
        else:
            raise RuntimeError("near necesita uno de: point, feature, box")
        return json.dumps(_api("GET", "/api/near", params=params).json(), ensure_ascii=False)

    @mcp.tool()
    def verify(checks: list[dict]) -> str:
        """Verifica en UNA llamada un lote de ASERCIONES numéricas sobre el modelo (READ-ONLY) —
        declara tus INVARIANTES y compruébalas de golpe en vez de encadenar N measure + aritmética
        mental. Devuelve {ok, resultados:[{check, ok, actual, esperado}]}. Cada aserción es un dict
        con `tipo` (y un `nombre` opcional para etiquetarla):
        - {tipo:"distancia", a, b, min?|max?|entre?:[lo,hi]} — gap OCCT entre dos sólidos.
        - {tipo:"volumen", id?|grupo?|ids?, min?|max?|entre?} — volumen (suma si son varios).
        - {tipo:"bbox", id?|grupo?|ids?, eje:"x"|"y"|"z", min?|max?|entre?} — tamaño de la caja conjunta.
        - {tipo:"sin_interferencia", ids?} — 0 colisiones (acotado a ids/grupos; sin ids = global).
        - {tipo:"existe", id?|name?} — el id existe / hay piezas cuyo nombre contiene name.
        `grupo`/`ids` aceptan NOMBRES de grupo (se expanden); `id` es un feature_id único (NO se
        expande). `sin_interferencia` con ids/grupo que no resuelven a nada → error «sin piezas»
        (no degrada al chequeo global). EN POSE (V6.8-C): `distancia` y `sin_interferencia` aceptan
        `joint_values` {junta: valor} POR ASERCIÓN → se evalúan con el mecanismo POSADO (costo ≈ un
        check_interference posado por pose distinta; junta desconocida = error, nunca verde en
        silencio). Úsalo tras snap_to/mover para confirmar holguras sin ojímetro."""
        return json.dumps(_api("POST", "/api/verify", json={"checks": checks}).json(), ensure_ascii=False)

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

    return {f.__name__: f for f in (
        get_topology, get_requirements, set_requirements, auto_group, get_groups,
        get_mass_properties, measure, near, verify, pick_point,
    )}
