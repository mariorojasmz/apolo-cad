"""Tools MCP de la prueba virtual (plan V8.3 D13): `test_plc`, `get_simulation`, `get_scenarios`,
`set_scenario` y `save_live_session` (V8.4 F4: una sesión en vivo vuelta escenario); y
`correr_escenario`, el camino de `simulate(escenario=…)`.

Cliente fino como el resto: sólo HTTP (`/api/escenarios`, `/api/cosim/…`). Vive fuera de
`mcp_server.py` (trinquete de tamaño), que la registra al final con `registrar(mcp, api,
esperar)`: `api` es su `_api` y `esperar` su `_submit_and_wait` (la corrida va como JOB y, si
tarda más que la espera, vuelve el RECIBO `{job, seguir}`), buscados en CADA llamada. NO importa
`apolo.mcp_server`: con `python -m apolo.mcp_server` el servidor es `__main__` y el import
cargaría una segunda copia (`tests/test_mcp_registro.py`).
"""

from __future__ import annotations

import json


def _recibo(job_id: str) -> str:
    """El mismo recibo que las mutaciones (`mcp_server._job_receipt`)."""
    return json.dumps({"job": job_id, "estado": "corriendo",
                       "seguir": f"llama get_job('{job_id}') para recoger el resultado"},
                      ensure_ascii=False)


def correr_job(esperar, path: str, body: dict) -> str:
    payload, job_id = esperar("POST", path, body)
    if job_id:
        return _recibo(job_id)
    return json.dumps(payload, ensure_ascii=False)


def correr_escenario(esperar, escenario) -> str:
    """`simulate(escenario=…)`: la co-simulación de la máquina entera (D11–D12)."""
    return correr_job(esperar, "/api/cosim/run", {"escenario": escenario})


def registrar(mcp, api, esperar) -> None:
    """Registra las cinco tools en `mcp` (el del servidor que corre), en este orden."""

    @mcp.tool()
    def test_plc(
        fuente: str,
        plc: str | None = None,
        escenario: str | dict | None = None,
        ciclo_ms: int = 10,
        ciclos: dict | None = None,
        senales: list[str] | None = None,
    ) -> str:
        """Prueba un programa de PLC en texto estructurado (ST, IEC 61131-3) SIN guardarlo, como
        test_script. Compila contra los bornes del PLC `plc` («-K1»: %IX0.0 = borne I0.0, %QX0.0
        = Q0.0, %IW1 = AI1) y devuelve `compila`, los `errores` con línea y columna («¿quisiste
        decir…?») y la tabla de `tags`. Con `escenario` (nombre de uno guardado u objeto, como en
        set_scenario) además CORRE la máquina con este programa en lugar del de ese PLC y
        devuelve veredicto, aserciones, eventos y las trazas de `senales` (por defecto las del
        PLC, «-K1.*»). `ciclos` = {PROGRAM: ms}. Cuando funcione, guárdalo con
        run_command('add_program', {plc, fuente, ciclo_ms}). Si tarda, RECIBO {"job"}: get_job."""
        body: dict = {"fuente": fuente, "ciclo_ms": ciclo_ms}
        for k, v in (("plc", plc), ("escenario", escenario), ("ciclos", ciclos), ("senales", senales)):
            if v:
                body[k] = v
        return correr_job(esperar, "/api/cosim/plc/test", body)

    @mcp.tool()
    def get_simulation(
        simulacion: str | None = None,
        parte: str = "resumen",
        senales: list[str] | None = None,
        desde_s: float | None = None,
        hasta_s: float | None = None,
        limite: int = 200,
        offset: int = 0,
    ) -> str:
        """Lee por partes el resultado de una co-simulación (simulate con escenario o test_plc):
        sin `simulacion`, la lista de las últimas (en memoria; un reinicio las pierde). `parte`:
        'resumen' (veredicto, aserciones y los NOMBRES de todas las señales), 'eventos'
        (paginados), 'final' (valores al final; `senales` filtra) o 'trazas' (pide `senales`:
        nombres D10 como «-M1.rpm», «-K1.%QX0.0», «-K1.cuenta», o patrones «-M1.*»; ventana
        `desde_s`–`hasta_s`; discretas por cambio y analógicas a 50 Hz, paginadas con
        `limite`/`offset`). Read-only."""
        if not simulacion:
            return json.dumps(api("GET", "/api/cosim/simulaciones").json(), ensure_ascii=False)
        params: dict = {"parte": parte, "limite": limite, "offset": offset}
        if senales:
            params["senales"] = ",".join(senales)
        if desde_s is not None:
            params["desde_s"] = desde_s
        if hasta_s is not None:
            params["hasta_s"] = hasta_s
        return json.dumps(api("GET", f"/api/cosim/simulaciones/{simulacion}", params=params).json(),
                          ensure_ascii=False)

    @mcp.tool()
    def get_scenarios(nombre: str | None = None) -> str:
        """Los escenarios de prueba del proyecto (la FAT virtual) con su estado: sin_correr,
        pasa, falla, sin_aserciones o vencido (la máquina o el escenario cambiaron desde la
        última corrida); con `nombre`, ése entero (definición y último resultado). delivery_check
        da ROJO si uno falla y AMARILLO si hay sin correr o vencidos. Read-only."""
        params = {"nombre": nombre} if nombre else {}
        return json.dumps(api("GET", "/api/escenarios", params=params).json(), ensure_ascii=False)

    @mcp.tool()
    def set_scenario(nombre: str, escenario: dict | None = None) -> str:
        """Declara (o reemplaza) un ESCENARIO de prueba de la máquina con tablero; `escenario`
        null lo borra. Es metadato (no entra al log ni al undo). Forma:
        {duracion_s, descripcion?,
         condiciones?: {red_conectada, selectores {"-S5": "I"}, setas_retenidas [], plc_run,
                        presion_red_bar (la toma de aire, manométrica: obligatoria con aire)},
         acciones: [{t, accion: pulsar|soltar|presionar|liberar|girar|rearmar|abrir|cerrar|
                     reponer|accionar_manual (válvula: valor «14»|«12», «0» lo suelta),
                     dispositivo, valor?, durante_s?, actuador?}],
         eventos: [{t, tipo: atasco (junta, par_Nm) | corte_de_fase (fase) | caida_de_red
                    (factor) | cable_cortado (rama «-W3») | sensor_pegado (dispositivo) |
                    corte_de_aire | presion_de_red (bar) | fuga (puerto «-MM1:A», C, b?) |
                    falla | producto (como en simulate), duracion_s?}],
           ↑ falla = un aparato que falla A PROPÓSITO, para ver si la máquina para igual:
             {dispositivo, falla, valor?} con la que su modelo toma (contactor soldado |
             no_cierra; seta/pulsador/selector/seccionador/resguardo trabado; sensor pegado |
             sin_salida; ITM/guardamotor/relé térmico/fusible no_dispara | abierto; PLC
             entrada_pegada | salida_pegada {borne, valor} | detenido; relé de seguridad
             salida_pegada «13-14» | detenido; variador canal_sto_pegado (S1|S2) |
             falla_interna; fuente sin_salida; piloto fundido; electroválvula pegada (posición?) |
             bobina_cortada (14|12 si tiene dos)), {rama «-K1:13-14», falla: pegado,
             valor: true|false} (UN contacto) o abierto, o {falla: corto, a «-X1:1», b «-X1:PE»,
             R_ohm?}; quitar: true la repara. Ancla «desde falla -K1»; publica «-K1.averia».
         acoples: {motores: {"-M1": {junta, direccion_transporte}}, sensores: {"-B1": {origen,
                   direccion, alcance_mm?}} o, un detector de cilindro, {"-BG1": {junta, en_mm,
                   ventana_mm}}, cilindros: {"-MM1": {junta: "<cmd>_vastago"}}},   ← qué junta
                   mueve cada motor y cada cilindro y dónde mira cada sensor: obligatorio para
                   los motores y los cilindros
         mecanica?: {bandas, juntas, timestep, nstep, con_autodeteccion…},   ← una banda HECHA A
                    MANO va en bandas [{pieza, junta_motriz}]: sin ella no avanza y un escenario
                    con cajas encima o aserciones sobre ella es error,
         trazas?: {analogicas_hz, senales},
         aserciones: ["-M1.rpm >= 1700 dentro_de 3 s desde pulsar -S1",
                      "-M1.par_Nm == 0 dentro_de 0,5 s desde presionar -S0",
                      "-Q2.disparado dentro_de 10 s desde atasco", "-K1.cuenta == 10 al_final",
                      "-T2.f_Hz <= 61 siempre", "-K1.Main.en_marcha nunca desde liberar -S0",
                      "-M1.rpm > 100 en 2,5 s"]}
        Ventanas: al_final, en t, dentro_de Δ desde <acción o evento> [y se mantiene D s] (sin
        «y se mantiene» basta TOCAR el valor), siempre/nunca [desde … [+ 50 ms]] (sin margen
        miran también el instante del ancla: el filtro de entrada, el scan y el STO tardan ms).
        La comparación tipa: un texto con una señal de texto, true/false con una booleana; sin
        comparación, una booleana es «== true» y un texto «no vacío» (una numérica pide su
        umbral). Los tipos se revisan AL DECLARAR (400 con la forma correcta). Córrelo con simulate(escenario="<nombre>"): el resultado queda guardado con su vigencia."""
        if escenario is None:
            return json.dumps(api("DELETE", f"/api/escenarios/{nombre}").json(), ensure_ascii=False)
        return json.dumps(api("PUT", f"/api/escenarios/{nombre}", json={"escenario": escenario}).json(),
                          ensure_ascii=False)

    @mcp.tool()
    def save_live_session(
        nombre: str,
        sesion: str | None = None,
        hasta_s: float | None = None,
        reemplazar: bool = False,
    ) -> str:
        """Vuelve una SESIÓN EN VIVO (la persona maneja la máquina en el visor: aprieta el verde,
        la seta…) en el escenario de prueba `nombre`: sus acciones y eventos con la hora virtual
        en que entraron, sobre su escenario de base y con la cola de cajas que tuvo la sesión. La
        corre por lote (las mismas trazas que se vieron) y devuelve `aserciones_sugeridas` con lo
        que pasó («-M1.rpm >= 1570 dentro_de 1.6 s desde pulsar -S1», «-M1.par_Nm == 0
        dentro_de 0.2 s desde presionar -S0»), todas verdes sobre esa corrida: NO quedan en el
        escenario; acepta las que quieras con set_scenario(nombre, {…el `escenario` devuelto,
        aserciones: […]}). `sesion` = el id del `fin` de la sesión (sin él, la última terminada
        del proyecto; viven en memoria); `hasta_s` guarda sólo el tramo inicial (obligatorio si
        duró más de 60 s). Un nombre ya usado pide reemplazar=true. Si tarda, RECIBO {"job"}:
        get_job."""
        body: dict = {"nombre": nombre, "reemplazar": reemplazar}
        if sesion:
            body["sesion"] = sesion
        if hasta_s is not None:
            body["hasta_s"] = hasta_s
        return correr_job(esperar, "/api/cosim/vivo/escenario", body)
