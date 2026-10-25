"""`WS /api/cosim/vivo`: la sesión EN VIVO de la co-simulación (plan V8.4 D1–D3).

Abrir: `ws://<api>/api/cosim/vivo?documento=<token>&escenario=<nombre>` — `documento` es el de
`GET /api/health` (el navegador no deja poner cabeceras en un WebSocket) y `escenario` uno
guardado que da los acoples, las condiciones, la mecánica y la cola de productos (si el
documento tiene uno solo, puede omitirse). Opcionales: `reemplazar=1` (cierra la sesión que
haya), `ritmo` (1 = tiempo real; 0 = sin dormir, para pruebas), `max_s` (tope virtual, ≤
`APOLO_VIVO_MAX_S`, 1800 s por defecto) y `plc_externo` (plan plc-en-el-lazo D6: JSON ≤ 1 KB,
`{"-K1": {"conector": "x.y", "config": {…}}}`, validado ANTES del worker como en el lote; con él
la sesión va al ritmo de la pared —`ritmo` ≠ 1 es 4400—, un intercambio por vez, y un lazo
cortado la PAUSA: `cosim/vivo_lazo.py`).

Coreografía (regla de dos locks): (a) bajo `STATE_LOCK`, la guardia del token, el escenario de
la sesión, la firma, el snapshot y lo que dibuja la faja y las cadenas (`sims._extraer_visual`);
(b) el worker en su proceso (`cosim.proceso_vivo`) — desde ahí nada toma `STATE_LOCK` ni
`PHYSICS_LOCK`, salvo la vigilancia de la firma cada `VIGILAR_FIRMA_S` (una lectura corta).
Lo que ve el cliente se copia, en el loop y en su orden, al bus EN PROCESO de las extensiones
(plan plc-en-el-lazo D11, `api/vivo_bus.py`: sin `STATE_LOCK`, colas acotadas propias); una
acción que llega por el bus la contesta sólo a su suscripción.

MENSAJES servidor → cliente (JSON salvo el fotograma):
  inicio        la tabla (`cosim/vivo_fotograma.py`: cuerpos, productos, juntas, bandas, señales,
                mandos, pilotos, dispositivos; su `pieza` es también la caja que dibujó un
                layout_tablero, `services/tablero.piezas_3d`) + firma, proyecto, escenario, dt_s, ventana_s,
                max_s, ritmo, fajas, cadenas, avisos, hipotesis, `plcs` si hay PLC
                ([{designacion, variables: [{ruta, tipo, escribible}]}], `services/variables_plc.py`)
                (con PLC externo, además `plc_externo` {designación: {conector, extension,
                version}} y `determinista: false`); a una extensión que llega tarde, con `tarde: true`
  binario       un fotograma float32 cada 1/30 s (formato en `cosim/vivo_fotograma.py`)
  ack/rechazo   la respuesta a cada acción, con su `id` y la hora virtual en que entró
  senales       señales nuevas para la tabla (antes del fotograma que las trae)
  textos        las señales de texto que cambiaron (estado del PLC, falla)
  factor        al cruzar ×0,95 del ritmo: la máquina no alcanza a la pared y va más lenta
  sesion_vieja  {vieja: true|false} cuando la firma del documento cambia (D3: la sesión sigue)
  pausa/reanudar, error (con `codigo`) y fin {motivo, t, grabacion, y si avanzó: sesion, base,
                firma, hash_base, duracion_s y `escenario` (o `aviso_escenario`)} — lo que pide
                `POST /api/cosim/vivo/escenario` para volverla prueba (F4). Con PLC externo: la
                pausa por lazo cortado lleva `motivo: "lazo"` y `mensaje`, y el fin suma
                `determinista: false`, `lazo` (lo medido por el núcleo) y, si hubo pausa,
                `aviso_externo` (el PLC de afuera siguió corriendo)
Cliente → servidor: las acciones de `cosim/vivo.py` («{"pulsar": "-S1"}», «{"control": "pausa"}»).
Códigos de cierre: 1000 fin, 4400 escenario que no corre, 4401 sin token, 4403 origen (sin
aceptar), 4409 token de otro documento, 4423 ya hay una sesión viva, 4500 el worker falló,
4502 el PLC externo no se pudo conectar (falló el PLC de afuera o su red, no el núcleo).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from urllib.parse import urlsplit

import anyio
from fastapi import APIRouter, WebSocket
from starlette.concurrency import run_in_threadpool

from apolo.services.errors import ServiceError
from apolo.state import STATE_LOCK

from ..common import VIVO_BUS, MAX_MENSAJE_VIVO, _token_documento, validar_mensaje_vivo
from ..session import S
from ..sims import SESIONES_GRABADAS, _extraer_visual, _sumar_visual

router = APIRouter()

LOOPBACK = {"localhost", "127.0.0.1", "::1"}
MAX_MENSAJE = MAX_MENSAJE_VIVO    # 4096 (`api/vivo_bus.py`: la misma validación para el bus)
VIGILAR_FIRMA_S = 2.0
COLA_MAX_FOTOGRAMAS = 60          # ~2 s de fotogramas sin enviar: los que llegan después se descartan
MAX_RITMO = 4.0


def max_s_vivo() -> float:
    """El tope de una sesión: `APOLO_VIVO_MAX_S` (s virtuales), 1800 por defecto."""
    try:
        return max(1.0, float(os.environ.get("APOLO_VIVO_MAX_S", "1800")))
    except ValueError:
        return 1800.0


def origen_permitido(origen: str | None, host: str | None) -> bool:
    """Sin `Origin` (un script, un test) o el mismo host:puerto que la API, o una página
    servida desde esta máquina (el dev server de Vite en otro puerto). Una página de otro
    sitio NO: este WebSocket acepta acciones y cualquier pestaña puede intentar 127.0.0.1."""
    if not origen:
        return True
    u = urlsplit(origen)
    if u.scheme not in ("http", "https"):
        return False
    if host and u.netloc == host:
        return True
    return (u.hostname or "") in LOOPBACK


class _Rechazo(Exception):
    def __init__(self, codigo: int, clave: str, motivo: str):
        super().__init__(motivo)
        self.codigo, self.clave, self.motivo = codigo, clave, motivo


class SesionViva:
    """Una sesión: su worker y su cola hacia el WebSocket (sólo `reenviar` envía). `_poner` (en
    el loop) deja cada frame del worker en la forma que ve el cliente —la tabla vuelta `inicio`,
    el `fin` con lo de volverla escenario, los errores— y lo copia, en el mismo orden, a la cola
    de la persona y al bus de las extensiones (plan plc-en-el-lazo D11, `api/vivo_bus.py`)."""

    def __init__(self, loop, proyecto):
        self.loop = loop
        self.cola: asyncio.Queue = asyncio.Queue()
        self.proc = None
        self.proyecto = proyecto
        self.desde = time.strftime("%H:%M:%S")
        self.motivo: str | None = None   # «reemplazada» lo pone otra sesión
        self.prep: dict | None = None    # los pone `cosim_vivo` antes de lanzar el worker
        self.config: dict | None = None
        self.inicio = self.fin = False
        self.codigo = 1000               # el cierre del WebSocket si termina el worker
        self._fotogramas = 0
        self.descartados = 0

    def info(self) -> dict:
        return {"desde": self.desde, "proyecto": self.proyecto,
                **({"pid": self.proc.pid} if self.proc is not None else {})}

    def _poner(self, etiqueta, cuerpo) -> None:
        if etiqueta == b"F":
            if not self.inicio:   # nada antes de la tabla
                return
            VIVO_BUS.difundir_fotograma(cuerpo)
            if self._fotogramas >= COLA_MAX_FOTOGRAMAS:
                self.descartados += 1
                return
            self._fotogramas += 1
            self.cola.put_nowait((etiqueta, cuerpo))
            return
        if etiqueta is None:  # el worker terminó
            if not self.fin:
                motivo = self.motivo or "worker"
                falla = cuerpo not in (0, None) and motivo != "reemplazada"
                cola = self.proc.cola_stderr() if self.proc is not None else ""
                self.json({"tipo": "fin", "motivo": motivo,
                           **({"mensaje": f"el worker salió con código {cuerpo}:\n{cola}"} if falla else {})})
                if falla:
                    self.codigo = 4500
            self.cola.put_nowait((None, cuerpo))
            return
        if etiqueta == b"E":
            msg = {"tipo": "error", "codigo": "worker", "motivo": cuerpo.decode("utf-8", "replace")}
            self.codigo = 4500
        elif etiqueta == b"L":  # plc-en-el-lazo D6: el PLC externo no se pudo conectar
            msg = {"tipo": "error", "codigo": "lazo", "motivo": cuerpo.decode("utf-8", "replace")}
            self.codigo, self.motivo = 4502, self.motivo or "lazo"
        else:
            msg = json.loads(cuerpo.decode("utf-8"))
            if msg.get("tipo") == "tabla":
                msg = _inicio(self.prep, msg, self.config, self.proc.pid if self.proc else None)
                self.inicio = True
            elif msg.get("tipo") == "fin":
                msg = _fin(self.prep, msg, self.motivo)
                self.fin = True
        self.json(msg)

    def al_mensaje(self, etiqueta, cuerpo) -> None:
        """Desde el hilo lector del worker: al loop del WebSocket."""
        try:
            self.loop.call_soon_threadsafe(self._poner, etiqueta, cuerpo)
        except RuntimeError:  # el loop ya cerró
            pass

    def json(self, msg: dict) -> None:
        """Un mensaje JSON al cliente (en el loop); la respuesta a una acción del bus va sólo a
        su suscripción."""
        texto = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        if not VIVO_BUS.difundir_json(msg, texto, self):
            self.cola.put_nowait((b"J", texto))

    def enviar(self, msg: dict) -> bool:
        """Una acción del bus al worker (desde cualquier hilo). False si no hay worker."""
        proc = self.proc
        return proc is not None and proc.enviar(msg)

    def reemplazar(self) -> None:
        self.motivo = "reemplazada"
        if self.proc is not None:
            self.proc.matar()


class Sesiones:
    """UNA sesión viva por API (un documento por API, como la flota). Lock HOJA."""

    def __init__(self):
        self._lock = threading.Lock()
        self.actual: SesionViva | None = None
        self.ultima: SesionViva | None = None   # la última que se abrió (los tests miran su worker)

    def tomar(self, ses: SesionViva, reemplazar: bool) -> dict | None:
        """None si `ses` quedó como la sesión viva; si no, la info de la que ya hay."""
        with self._lock:
            vieja = self.actual
            if vieja is not None and not reemplazar:
                return vieja.info()
            self.actual = self.ultima = ses
        if vieja is not None:
            vieja.reemplazar()
        return None

    def soltar(self, ses: SesionViva) -> None:
        with self._lock:
            if self.actual is ses:
                self.actual = None

    def cerrar_todas(self) -> None:
        """Al apagar la API: ningún worker vivo queda huérfano."""
        with self._lock:
            ses = self.actual
        if ses is not None and ses.proc is not None:
            ses.proc.matar()


SESIONES = Sesiones()


def _preparar(token: str | None, nombre: str | None, q_externo: str | None = None,
              q_ritmo: str | None = None) -> dict:
    """(a) Bajo STATE_LOCK: guardia, escenario de la sesión, firma, snapshot y la faja; con
    `?plc_externo=`, su forma y su ritmo antes del snapshot, que lo valida contra el tablero."""
    from apolo.cosim.vivo import escenario_vivo
    from apolo.services import cosim_externo
    from apolo.services import escenarios as E
    from apolo.services.cosim_snapshot import snapshot_cosim
    from apolo.services.tablero import piezas_3d

    with STATE_LOCK:
        if not token:
            raise _Rechazo(4401, "documento", "Falta ?documento=<token> (el campo `documento` de GET "
                                              "/api/health): la sesión en vivo se abre sobre ESE documento.")
        if token != _token_documento():
            raise _Rechazo(4409, "documento", "El proyecto abierto cambió (se abrió otro o se restauró una "
                                              "revisión): vuelve a leer `documento` de GET /api/health y "
                                              "abre la sesión de nuevo.")
        doc = S.doc
        if not nombre:
            guardados = sorted(doc.escenarios)
            if len(guardados) != 1:
                raise _Rechazo(4400, "escenario", (
                    "Indica ?escenario=<nombre>: el escenario de base da los acoples motor ↔ junta y "
                    "sensor ↔ rayo, las condiciones, la mecánica y la cola de cajas. Guardados: "
                    f"{', '.join(guardados) or 'ninguno (declara uno con set_scenario)'}"))
            nombre = guardados[0]
        try:
            externo = cosim_externo.de_query(q_externo, q_ritmo)
        except ServiceError as exc:
            raise _Rechazo(4400, "plc_externo", exc.detail) from exc
        try:
            nombre, base = E.resolver(doc, nombre)
            esc = escenario_vivo(base)
            hash_base = E.hash_escenario(base)
            firma = E.firma_documento(doc)
            snap = snapshot_cosim(doc, esc, plc_externo=externo)
        except ServiceError as exc:
            raise _Rechazo(4400, "escenario", f"escenario «{nombre}»: {exc.detail}") from exc
        vis = _extraer_visual(doc, snap.dinamica)
        piezas = piezas_3d(doc)   # pedidos-de-extensiones D15: lo que dibujó el layout, también
        return {"doc": doc, "proyecto": S.project_id, "nombre": nombre, "esc": esc, "firma": firma,
                "hash_base": hash_base, "snap": snap, "vis": vis, "piezas": piezas,
                "externo": cosim_externo.resultado(externo) if externo else None}


def _firma_ahora(doc) -> str | None:
    """La firma del documento activo, o None si ya no es el de la sesión."""
    from apolo.services.escenarios import firma_documento

    with STATE_LOCK:
        return firma_documento(S.doc) if S.doc is doc else None


def _inicio(prep: dict, tabla: dict, config: dict, pid) -> dict:
    from apolo.services.tablero import piezas_en_tabla
    from apolo.services.variables_plc import plcs as variables_plc

    snap = prep["snap"]
    tabla = piezas_en_tabla(tabla, prep.get("piezas") or {})   # pedidos-de-extensiones D15
    estatico = {"avisos": list(snap.avisos)}
    _sumar_visual(estatico, prep["vis"], {"cuerpos": snap.dinamica.cuerpos, "juntas": {}})
    plcs = variables_plc(getattr(snap, "programas", ()))   # pedidos-de-extensiones D12
    return {"tipo": "inicio", "version": 1, "proyecto": prep["proyecto"], "escenario": prep["nombre"],
            "firma": prep["firma"], "ventana_s": 1.0 / 30.0, "max_s": config["max_s"],
            "ritmo": config["ritmo"], "pid": pid,
            **{k: v for k, v in tabla.items() if k != "tipo"},
            "fajas": estatico["fajas"], "cadenas": estatico["cadenas"], "avisos": estatico["avisos"],
            "hipotesis": list(snap.hipotesis),
            **({"plcs": plcs} if plcs else {}),
            **({"plc_externo": prep["externo"], "determinista": False} if prep.get("externo") else {})}


def _fin(prep: dict, msg: dict, motivo: str | None) -> dict:
    """El `fin` con lo que hace falta para volver la sesión un escenario (F4): queda en
    `SESIONES_GRABADAS` con su `sesion` y viaja entero (base, firma, hash_base), y `escenario`
    es el que se guardaría (`services/sesion_viva.py`, con la cola de cajas fijada)."""
    from apolo.services.sesion_viva import escenario_de_sesion

    out = {**msg, "motivo": motivo or msg.get("motivo")}
    t = round(float(msg.get("t") or 0.0), 6)
    if t <= 0.0:
        return out
    grabacion = msg.get("grabacion") or []
    sesion = "v" + uuid.uuid4().hex[:8]
    datos = {"base": prep["nombre"], "firma": prep["firma"], "hash_base": prep["hash_base"],
             "duracion_s": t}
    SESIONES_GRABADAS.guardar({"id": sesion, "proyecto": prep["proyecto"], "grabacion": grabacion,
                               "hora": time.strftime("%H:%M:%S"), **datos})
    out.update(sesion=sesion, **datos)
    try:
        out["escenario"] = escenario_de_sesion(prep["esc"], grabacion, t, base=prep["nombre"])["escenario"]
    except ServiceError as exc:
        out["aviso_escenario"] = exc.detail
    return out


async def _rechazar(ws: WebSocket, codigo: int, clave: str, motivo: str) -> None:
    await ws.send_json({"tipo": "error", "codigo": clave, "motivo": motivo})
    await ws.close(code=codigo, reason=clave)


def _config(q) -> dict:
    tope = max_s_vivo()
    try:
        ritmo = min(MAX_RITMO, max(0.0, float(q.get("ritmo", 1.0))))
        max_s = min(tope, max(0.1, float(q.get("max_s", tope))))
    except ValueError:
        ritmo, max_s = 1.0, tope
    return {"ritmo": ritmo, "max_s": max_s}


@router.websocket("/api/cosim/vivo")
async def cosim_vivo(ws: WebSocket) -> None:
    from apolo.cosim.proceso import CosimError
    from apolo.cosim.proceso_vivo import ProcesoVivo

    if not origen_permitido(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=4403)  # sin aceptar: una página ajena no recibe ni el motivo
        return
    await ws.accept()
    q = ws.query_params
    ses = SesionViva(asyncio.get_running_loop(), S.project_id)
    otra = SESIONES.tomar(ses, q.get("reemplazar") in ("1", "true", "si", "sí"))
    if otra is not None:
        await _rechazar(ws, 4423, "sesion_ocupada", (
            f"Ya hay una sesión en vivo abierta (desde las {otra['desde']}, proyecto {otra['proyecto']}): "
            "ciérrala antes de abrir otra, o abre con ?reemplazar=1 para cerrarla."))
        return
    try:
        try:
            prep = await run_in_threadpool(_preparar, q.get("documento"), q.get("escenario"),
                                           q.get("plc_externo"), q.get("ritmo"))
        except _Rechazo as r:
            await _rechazar(ws, r.codigo, r.clave, r.motivo)
            return
        config = _config(q)
        if prep["externo"]:  # D9: al ritmo de la pared (otro ritmo ya fue 4400)
            config["ritmo"] = 1.0
        ses.prep, ses.config = prep, config   # antes del worker: `_poner` los usa con la tabla
        try:
            ses.proc = await run_in_threadpool(ProcesoVivo, prep["snap"], config, ses.al_mensaje)
        except CosimError as exc:
            await _rechazar(ws, 4500, "worker", str(exc))
            return
        if ses.motivo == "reemplazada":
            ses.proc.matar()
        VIVO_BUS.abrir(ses)   # D11: desde aquí `enviar_vivo` llega a este worker
        await _sesion(ws, ses, prep)
    finally:  # sin await: si el loop canceló la tarea, un await aquí no correría
        VIVO_BUS.cerrar(ses)
        SESIONES.soltar(ses)
        if ses.proc is not None:
            ses.proc.cerrar_en_hilo()


async def _sesion(ws: WebSocket, ses: SesionViva, prep: dict) -> None:
    async def reenviar() -> None:
        while True:
            etiqueta, cuerpo = await ses.cola.get()
            if etiqueta is None:  # el worker terminó (su `fin` ya salió)
                return
            if etiqueta == b"F":
                ses._fotogramas -= 1
                await ws.send_bytes(cuerpo)
            else:
                await ws.send_text(cuerpo)

    async def recibir() -> None:
        while True:
            m = await ws.receive()
            if m["type"] == "websocket.disconnect":
                return
            texto = m.get("text")
            if texto is None:
                ses.json({"tipo": "rechazo", "id": None, "motivo": "las acciones van como texto JSON"})
                continue
            msg, motivo = validar_mensaje_vivo(texto)
            if motivo is not None:
                ses.json({"tipo": "rechazo", "id": None, "motivo": motivo})
                continue
            if not ses.proc.enviar(msg):
                return

    async def vigilar() -> None:
        vieja = False
        while True:
            await asyncio.sleep(VIGILAR_FIRMA_S)
            firma = await run_in_threadpool(_firma_ahora, prep["doc"])
            ahora = firma != prep["firma"]
            if ahora != vieja:
                vieja = ahora
                ses.json({"tipo": "sesion_vieja", "vieja": vieja, **({"mensaje": (
                    "El modelo cambió desde que abriste la sesión: lo que ves es el modelo de entonces. "
                    "Reinicia la sesión para simular el de ahora.") if firma is not None else (
                    "Se abrió otro proyecto: esta sesión simula el anterior. Reiníciala.")} if vieja else {})})

    termino: list[str] = []

    async def hasta_que(nombre: str, f, tg) -> None:
        await f()
        termino.append(nombre)
        tg.cancel_scope.cancel()  # el primero que termina (worker o cliente) cierra la sesión

    async with anyio.create_task_group() as tg:
        tg.start_soon(hasta_que, "worker", reenviar, tg)
        tg.start_soon(hasta_que, "cliente", recibir, tg)
        tg.start_soon(vigilar)
    if termino[:1] == ["worker"]:
        try:
            await ws.close(code=ses.codigo)
        except RuntimeError:
            pass
