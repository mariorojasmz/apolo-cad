"""Tools MCP de lectura e introspección: comandos del log, croquis y script en seco, `redo`,
mates y GDL, conectividad y puerta de entrega, gravedad, movimiento, stack-up y revisiones.

Bloque de `mcp_server.py` movido tal cual, con 4 espacios más de sangría (plan
partir-nucleo-congelado, F1). `mcp_server` llama `registrar` EN EL LUGAR del bloque con
`globals().update(...)`: el orden de `list_tools()` no cambia y cada tool sigue siendo un
atributo de `apolo.mcp_server`. NO importa `apolo.mcp_server` (con `-m` el servidor es
`__main__`: `tests/test_mcp_registro.py`). `_api` y `_paso`: lambdas que buscan el del servidor en
CADA llamada (un test que lo parchea por nombre también llega aquí). Importa lo que nombran
las anotaciones: FastMCP las evalúa.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from apolo.brief import _one_or_many, _scene_brief


def registrar(mcp, _api, _paso) -> dict[str, Callable]:
    """Registra en `mcp` (el del servidor que corre) las tools de `introspeccion` y las
    devuelve por nombre para que `mcp_server` las re-exporte."""

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
    def find_commands(
        type: str | None = None, feature: str | None = None,
        name: str | None = None, limit: int = 100,
    ) -> str:
        """Busca COMANDOS en el log del documento y devuelve filas compactas
        [{id, type, resumen}] — para encontrar el command_id que quieres editar/borrar
        SIN deducirlo por aritmética de lotes. Al menos un filtro:
          - type: tipo exacto ('chamfer', 'create_box', 'add_joint', …).
          - feature: comandos que CREARON ese sólido o lo REFERENCIAN en sus params
            (feature/feature_a/b, members, parent/child, selectores…).
          - name: substring (sin mayúsculas) del nombre; en el carril eléctrico, '-M1', 'NMRV'…
        Combínalos (type='chamfer', feature='c14' = los chaflanes sobre c14). Read-only."""
        params: dict = {"limit": limit}
        if type:
            params["type"] = type
        if feature:
            params["feature"] = feature
        if name:
            params["name"] = name
        return json.dumps(_api("GET", "/api/commands", params=params).json(), ensure_ascii=False)

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
    def redo(detail: str = "diff") -> str:
        """Rehace la última operación deshecha. `detail` como en undo (`rehecho` = qué rehízo)."""
        return _paso("/api/redo", "rehecho", detail)

    @mcp.tool()
    def get_mates() -> str:
        """Mates de ensamblaje del documento (uniones persistentes entre piezas)."""
        return json.dumps(_api("GET", "/api/mates").json(), ensure_ascii=False)

    @mcp.tool()
    def get_dof() -> str:
        """Reporte de GRADOS DE LIBERTAD del ensamblaje (análogo 3D del dof/redundantes del
        croquis): por sólido, cuántos GDL le quedan tras ground/juntas/mates y su estado
        (fijo | parcial | libre | sobre_restringido) + qué lo restringe. Conteo Grübler
        determinista. OJO: el conteo es heurístico (no ve redundancia geométrica); un
        'sobre_restringido' puede ser redundancia benigna — los conflictos REALES los rechaza
        el solver de mates al editar. Útil para responder '¿qué puede moverse y qué está
        sobre-restringido?'."""
        return json.dumps(_api("GET", "/api/assembly/dof").json(), ensure_ascii=False)

    @mcp.tool()
    def check_assembly(with_autodetect: bool = False, detail: str = "summary") -> str:
        """Validación de ensamblaje por CONECTIVIDAD: ¿cada pieza tiene un camino de sujeción
        hasta el piso? Devuelve las piezas FLOTANTES (caerían bajo gravedad — eje suelto, rodillo
        sin sujetar, guarda sin tornillo, motor flotando) y las AISLADAS (sin ninguna unión).
        Determinista. Por defecto cuenta SOLO lo DECLARADO (como delivery_check); True superpone
        sin persistir los contactos geométricos para EXPLORAR ('si fijara todo lo que se toca, ¿qué
        seguiría flotando?'). Declara uniones reales con run_command(type='ground'|'fasten').
        `detail`: "summary" (def.) da los conteos y SÓLO lo que flota (`floating_detail` con nombre,
        `isolated`); "full" suma los ids sujetos y las componentes conexas."""
        body = {"with_autodetect": with_autodetect, "resumen": detail != "full"}
        return json.dumps(_api("POST", "/api/assembly/soundness", json=body).json(), ensure_ascii=False)

    @mcp.tool()
    def autodetect_connections() -> str:
        """Propone uniones de ensamblaje desde la GEOMETRÍA (piezas que apoyan en el piso +
        pares en contacto por caja envolvente), para poblar la conectividad de un modelo que no
        la declara. Read-only: confirma las que quieras con run_command(type='ground'|'fasten').
        Heurística por AABB (propone, no impone)."""
        payload = _api("POST", "/api/assembly/autodetect", json={}).json()
        return json.dumps(payload, ensure_ascii=False)

    @mcp.tool()
    def get_connections(
        ids: list[str] | None = None, kind: str | None = None, resumen: bool | None = None
    ) -> str:
        """Uniones de ensamblaje DECLARADAS (persistidas) del documento: fijadores (a↔b) y anclajes a
        tierra, con sus nombres (para borrarlas con delete_connection). Read-only. Filtra con `ids`
        (piezas, NOMBRES DE GRUPO o command_ids: las uniones donde participa alguna) y `kind` (perno |
        soldadura | pegado | contacto | anclaje). Con más de 40 uniones responde el RESUMEN —conteos
        por tipo y una fila por tipo y PAR de piezas {kind, a, b, n, ejemplo}—; `resumen=true` lo
        fuerza y `resumen=false` trae la lista entera."""
        params = {"resumen": {None: "auto", True: "si", False: "no"}[resumen],
                  **({"ids": ",".join(ids)} if ids else {}), **({"kind": kind} if kind else {})}
        return json.dumps(_api("GET", "/api/connectivity", params=params).json(), ensure_ascii=False)

    @mcp.tool()
    def delete_connection(name: str | None = None, names: list[str] | None = None) -> str:
        """Borra una o VARIAS uniones declaradas por NOMBRE (fijadores o anclajes a tierra) —
        para corregir el auto-declarado o para cirugías. Pasa `name` (una) o `names` (lote),
        no ambos. El lote es ATÓMICO (1 undo): si un nombre no existe, no se borra ninguna.
        Consulta los nombres con get_connections."""
        wanted = _one_or_many(name, names, "name")
        payload = _api("POST", "/api/connections/remove", json={"names": wanted}).json()
        borradas = payload.get("conexiones_borradas", [])
        return json.dumps({"borradas": borradas, "n": len(borradas)}, ensure_ascii=False)

    @mcp.tool()
    def delivery_check(con_gravedad: bool = False) -> str:
        """LA PUERTA DE SALIDA (V6.9): antes de dar un proyecto por TERMINADO, corre TODA la
        batería de cierre en UNA llamada y devuelve un SEMÁFORO accionable:
        {veredicto: VERDE|AMARILLO|ROJO, bloqueantes, avisos, no_aplica, resumen}.
        Chequeos: interferencias en diseño (exclusiones normales) · sujeción DECLARADA
        (¿todo tiene camino de carga a tierra? — sin autodetect: cuenta lo que DECLARASTE
        con ground/fasten) · lints pre-entrega (barreno sin perno, pieza suelta) · salud del
        documento · colisión EN POSE en los fotogramas de REPOSO de los estudios de movimiento
        declarados (extremos + poses sostenidas; el TRÁNSITO interpolado se valida con
        scan_motion; el contacto de asiento ≤50 mm³ se tolera y se declara).
        `con_gravedad=true` añade la simulación MuJoCo (cara; opt-in).
        ROJO = defecto que el cliente verá (piezas flotantes, colisiones, poses rotas):
        NO ENTREGUES EN ROJO — corrige (declare_structure / ground / fasten / reposiciona)
        y re-corre hasta VERDE o AMARILLO declarando los avisos. `no_aplica` lista lo que
        no pudo evaluarse — no cuenta como verde. `tiempos_s`: total y por regla. Read-only."""
        payload = _api("POST", "/api/delivery-check", json={"con_gravedad": con_gravedad}).json()
        return json.dumps(payload, ensure_ascii=False)

    @mcp.tool()
    def gravity_test(
        with_autodetect: bool = False, exclude: list[str] | None = None,
        seconds: float = 2.0, gravity: float = 9.81, path: str | None = None,
    ) -> str:
        """Simula la GRAVEDAD sobre TODA la máquina (cuerpos rígidos + colisión por casco
        convexo, motor MuJoCo) y reporta qué piezas SE CAEN y cuáles aguantan. A diferencia
        del chequeo estático, la FÍSICA decide si una pieza no-sujeta REPOSA sobre algo firme
        (no cae) o cuelga en el aire (cae). Por defecto sujeta SOLO lo DECLARADO (ground/fasten);
        with_autodetect=True suma el contacto geométrico (exploración). `exclude` trata esas
        piezas como NO sujetas ('¿y si a esta le falta el tornillo?'). Con `path` guarda además
        un GIF animado de la caída. Read-only: NO modifica el modelo."""
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
    def set_motion(name: str, keyframes: list[dict]) -> str:
        """Define (o borra, con lista vacía) un ESTUDIO DE MOVIMIENTO con nombre — autoría de
        cinemática sin salir del MCP (V6.8-C). Fotograma: {"t": segundos, "values": {junta:
        valor}} — los valores van ANIDADOS en "values" (el formato plano se rechaza) y las
        juntas se validan contra las declaradas (get_kinematics). OJO FK: una junta mueve solo
        sus HIJOS declarados — completa un cuerpo rígido multi-pieza con juntas 'fija' colgadas
        del conductor. Verifica el recorrido con scan_motion, míralo con motion_gif; en la UI
        aparece en el panel Cinemática."""
        payload = _api("PUT", "/api/motion", json={"name": name, "keyframes": keyframes}).json()
        estudios = [
            {"name": s["name"], "duration": s["duration"], "n_fotogramas": len(s["keyframes"])}
            for s in payload.get("studies", [])
        ]
        return json.dumps({"ok": True, "estudios": estudios}, ensure_ascii=False)

    @mcp.tool()
    def scan_motion(name: str, steps: int = 24) -> str:
        """Escanea las COLISIONES de un estudio de movimiento a lo largo del recorrido:
        muestrea `steps` instantes (FK + interferencia por instante — costo ≈ steps ×
        check_interference posado) y devuelve SOLO los que colisionan, con pares y volumen.
        Lista vacía = recorrido limpio. Corre esto tras cada cambio del mecanismo; para
        garantizarlo por CONTRATO en un lote usa `expect` con joint_values. Read-only."""
        payload = _api("POST", "/api/motion/scan", json={"name": name, "steps": steps}).json()
        return json.dumps(payload, ensure_ascii=False)

    @mcp.tool()
    def motion_gif(
        name: str, path: str, steps: int = 48, fps: int = 12, pingpong: bool = False,
        view: str = "iso", azimuth: float | None = None, elevation: float | None = None,
        zoom: float = 1.0, size_px: int = 720,
    ) -> str:
        """GIF animado de un estudio de movimiento, ESCRITO a `path` (las tools no devuelven
        binarios). Cada fotograma se pinta con el mismo motor VTK que render_view, con la
        cámara FIJA a la unión de todo el recorrido; `pingpong` añade la vuelta (bucle sin
        salto). COSTO REAL: el teselado no se cachea entre fotogramas (≈ steps × render de la
        escena) — en modelos grandes usa steps moderados (24-48) y baja size_px; si supera
        ~2 min el cliente corta por timeout aunque el servidor termine."""
        from pathlib import Path

        body: dict = {"name": name, "steps": steps, "fps": fps, "pingpong": pingpong,
                      "view": view, "zoom": zoom, "size_px": size_px}
        if azimuth is not None:
            body["azimuth"] = azimuth
        if elevation is not None:
            body["elevation"] = elevation
        gif = _api("POST", "/api/motion.gif", json=body).content
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gif)
        return json.dumps({"gif": str(target), "bytes": len(gif)}, ensure_ascii=False)

    @mcp.tool()
    def get_stackup(scope: str = "all") -> str:
        """Evalúa las CADENAS DE COTAS (stack-up, V7.3): por cadena da el cierre nominal, el
        intervalo por PEOR CASO y por RSS (√Σt²), y el veredicto contra el requisito. Incluye
        las cadenas auto del patrón de pernos (join_bolted = cerrada por construcción). Verifica
        que la suma de tolerancias cierra el ajuste declarado SIN encadenar N measure. scope =
        all | declared | auto. Read-only."""
        return json.dumps(_api("GET", "/api/stackup", params={"scope": scope}).json(), ensure_ascii=False)

    @mcp.tool()
    def set_stackup(name: str, eslabones: list, requisito: dict | None = None) -> str:
        """Declara una CADENA DE COTAS 1D con nombre (metadato del proyecto, se persiste;
        lista de eslabones vacía → la borra). Cada eslabón es UNO de:
        - {nombre, nominal_mm, sentido:±1, tol} — cota literal; nominal_mm acepta '=expr'
          (sigue a las variables → la cadena se re-verifica al cambiarlas).
        - {id, eje:x|y|z, sentido:±1, tol?} — mide el BBOX VIVO de esa pieza (auto-actualiza).
        `tol` es UNA fuente: {"pm":0.2} (± mm) · {"fit":"h7"} (ISO 286) · {"iso2768":"m"} (general)
        · {"lim":[lo,hi]} (límites absolutos). `requisito` de cierre: {min_mm|max_mm|entre:[a,b]}.
        Devuelve la evaluación inmediata (peor caso + RSS + veredicto). La memoria de cálculo
        incluye una sección con las cadenas declaradas."""
        body = {"name": name, "eslabones": eslabones, "requisito": requisito or {}}
        return json.dumps(_api("PUT", "/api/stackup", json=body).json(), ensure_ascii=False)

    @mcp.tool()
    def list_revisions() -> str:
        """Lista las revisiones (instantáneas restaurables) del proyecto abierto."""
        return json.dumps(_api("GET", "/api/revisions").json(), ensure_ascii=False)

    @mcp.tool()
    def restore_revision(revision_id: int) -> str:
        """Restaura una revisión por id (red de seguridad tras ediciones arriesgadas)."""
        payload = _api("POST", f"/api/revisions/{revision_id}/restore").json()
        return json.dumps(_scene_brief(payload), ensure_ascii=False)

    return {f.__name__: f for f in (
        get_command, find_commands, test_sketch, test_script, redo, get_mates, get_dof,
        check_assembly, autodetect_connections, get_connections, delete_connection, delivery_check,
        gravity_test, get_motion, set_motion, scan_motion, motion_gif, get_stackup, set_stackup,
        list_revisions, restore_revision,
    )}
