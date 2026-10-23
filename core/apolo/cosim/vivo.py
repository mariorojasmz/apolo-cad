"""La sesión EN VIVO de la co-simulación (plan V8.4 D1): el mismo paso del lote, con las
acciones del operador SIN hora.

`Vivo(snap)` es la corrida sin reloj de pared: el worker (`worker_vivo.py`) la avanza al ritmo
de la pared; los tests, de golpe. Lo que la hace determinista:
  - cada intercambio es `Corrida.intercambio`, el MISMO del lote (`planificador.correr`);
  - una acción que llega se agenda para el PRÓXIMO intercambio (t = k·Δt) con
    `Agenda.inyectar`, y si el modelo la acepta queda en `grabacion` con esa hora;
  - la grabación vuelta escenario (`escenario_grabado`) da por lote las mismas trazas
    (`tests/test_cosim_vivo.py`).
Sin historia en memoria: `podar` olvida fotogramas y trazas por junta del `Integrador` (F0: el
bucle del lote acumula ~13 MB/min); lo único que crece es la grabación (clics de una persona).

Mensajes que entran (JSON, uno por acción; `id` opcional, vuelve en su respuesta):
  {"pulsar": "-S1"} · {"accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha",
  "durante_s": 0.2} · {"soltar": "-S1"} · {"presionar": "-S0"} · {"liberar": "-S0"}
  · {"girar": "-S5", "valor": "I"} · {"evento": {"tipo": "atasco", "junta": "j", "par_Nm": 400,
  "duracion_s": 2}} · {"control": "pausa" | "reanudar" | "parar"}
Respuestas: {"tipo": "ack", id, t, …} cuando se aplicó, o {"tipo": "rechazo", id, motivo}.
Puro: `cosim`, `plc` y la física sin OCCT (corre en el worker).
"""

from __future__ import annotations

import copy

from .corrida import Corrida
from .escenario import ACCIONES, EscenarioInvalido, leer_accion_viva, leer_evento_vivo
from .trazas import Trazas, huella
from .vivo_fotograma import Fotograma

VENTANA_S = 1.0 / 30.0          # un fotograma cada 33 ms (D2)
VIVO_MAX_S = 1800.0             # tope de seguridad de una sesión (30 min virtuales)
CONTROLES = ("pausa", "reanudar", "parar")


def escenario_vivo(base: dict) -> dict:
    """El escenario de la sesión desde uno de base (dict D12): condiciones, acoples, mecánica,
    trazas y la cola de productos se quedan; las acciones, los eventos del mundo y las
    aserciones se van (en vivo los da la persona y no hay veredicto). La duración del de base
    fija la cola de productos (MuJoCo no crea cuerpos en marcha)."""
    esc = copy.deepcopy(base)
    esc["acciones"] = []
    esc["eventos"] = [e for e in esc.get("eventos") or [] if isinstance(e, dict) and e.get("tipo") == "producto"]
    esc.pop("aserciones", None)
    esc["descripcion"] = f"sesión en vivo · {esc.get('descripcion') or 'sin descripción'}"
    return esc


def escenario_grabado(vivo_esc: dict, grabacion: list[dict], duracion_s: float) -> dict:
    """La sesión como escenario por lote (D10, F4): el escenario en vivo + lo grabado con su
    hora. Da las mismas trazas si su duración es la del escenario de base (la cola de productos
    sale de ella); con otra, la cola puede cambiar."""
    esc = copy.deepcopy(vivo_esc)
    esc["acciones"] = [g for g in grabacion if "accion" in g]
    esc["eventos"] = list(esc.get("eventos") or []) + [g for g in grabacion if "tipo" in g]
    esc["duracion_s"] = duracion_s
    esc["descripcion"] = "grabación de una sesión en vivo"
    return esc


def leer_mensaje(msg) -> tuple[str, object]:
    """("accion", dict) | ("evento", dict) | ("control", nombre). `EscenarioInvalido` si no va."""
    if not isinstance(msg, dict):
        raise EscenarioInvalido("se espera un objeto JSON: {\"pulsar\": \"-S1\"}")
    cuerpo = {k: v for k, v in msg.items() if k != "id"}
    if "control" in cuerpo:
        if cuerpo["control"] not in CONTROLES or len(cuerpo) != 1:
            raise EscenarioInvalido(f"control: {', '.join(CONTROLES)}")
        return "control", cuerpo["control"]
    if "evento" in cuerpo:
        if len(cuerpo) != 1:
            raise EscenarioInvalido("evento: {\"evento\": {\"tipo\": …}} sin otras claves")
        return "evento", cuerpo["evento"]
    if "accion" not in cuerpo:
        cortas = [k for k in cuerpo if k in ACCIONES]
        if len(cortas) != 1:
            raise EscenarioInvalido(f"una acción por mensaje: {{\"pulsar\": \"-S1\"}} o {{\"accion\": …, "
                                    f"\"dispositivo\": …}}; acciones: {', '.join(ACCIONES)}")
        cuerpo = {"accion": cortas[0], "dispositivo": cuerpo.pop(cortas[0]), **cuerpo}
    return "accion", cuerpo


class Vivo:
    def __init__(self, snap, *, max_s: float = VIVO_MAX_S, trazas: bool = False):
        self.c = Corrida(snap)
        self.dt = self.c.dt
        self.k = 0
        self.max_s = float(max_s)
        self.fot = Fotograma(self.c)
        #: sólo para el test de determinismo: las trazas del lote, con historia
        self.trazas = Trazas(snap.escenario.analogicas_hz, self.dt) if trazas else None
        self.grabacion: list[dict] = []
        self._pendientes: dict[int, tuple] = {}
        self._n = 0

    @property
    def t(self) -> float:
        return self.k * self.dt

    @property
    def agotada(self) -> bool:
        return self.t >= self.max_s - 1e-9

    def recibir(self, msg) -> dict | None:
        """Una acción o un evento para el PRÓXIMO intercambio. None si quedó agendado (su ack
        sale de `respuestas` después de aplicarse) o el rechazo, si no se puede leer."""
        ident = msg.get("id") if isinstance(msg, dict) else None
        try:
            clase, cuerpo = leer_mensaje(msg)
            if clase == "control":
                raise EscenarioInvalido("un control no es una acción")
            t = round(self.t, 6)
            x = leer_accion_viva(cuerpo, t) if clase == "accion" else leer_evento_vivo(cuerpo, t)
        except EscenarioInvalido as exc:
            return {"tipo": "rechazo", "id": ident, "motivo": str(exc)}
        self._n += 1
        self._pendientes[self._n] = (ident, clase, cuerpo)
        self.c.agenda.inyectar(x, t, self._n)
        return None

    def avanzar(self, n: int) -> None:
        """n intercambios (2 ms cada uno), sin pasar del tope."""
        for _ in range(n):
            if self.agotada:
                return
            self.c.intercambio(self.k, self.trazas)
            self.k += 1

    def respuestas(self) -> list[dict]:
        """Los acks y rechazos de lo aplicado desde la última llamada; lo aceptado entra a la
        grabación con su hora virtual."""
        out = []
        ag = self.c.agenda
        for r in ag.respuestas:
            ident, clase, cuerpo = self._pendientes.pop(r["id"])
            if not r["ok"]:
                out.append({"tipo": "rechazo", "id": ident, "motivo": r["motivo"]})
                continue
            if clase == "accion":
                g = {"t": r["t"], **{k: v for k, v in cuerpo.items() if v is not None}}
            else:
                g = {"t": r["t"], **cuerpo}
            self.grabacion.append(g)
            out.append({"tipo": "ack", "id": ident, "t": r["t"], clase: cuerpo})
        ag.respuestas.clear()
        return out

    def podar(self) -> None:
        if self.trazas is None:
            self.c.integ.podar()

    def cerrar_lote(self) -> str:
        """(test) El cierre del lote en este k: la muestra forzada sin física y la huella."""
        assert self.trazas is not None, "cerrar_lote es del test de determinismo (trazas=True)"
        self.c.intercambio(self.k, self.trazas, ultimo=True)
        final = self.trazas.cerrar()
        return huella(self.trazas.salida(), self.c.agenda.eventos, final)
