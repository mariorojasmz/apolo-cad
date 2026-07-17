"""Cola de trabajos (jobs) para las mutaciones largas — V6.5e.

Problema: una mutación por lote puede tardar más que el timeout del cliente MCP (120 s
de httpx) o del host (~180 s). Cuando eso pasa el servidor TERMINA bien pero el agente
queda CIEGO («¿aplicó?») — y ese modo de fallo lo empuja al camino inseguro (REST crudo,
sin PATCH ni contratos) justo en los modelos grandes. Subir los números no arregla nada:
siempre habrá un lote más lento. El fix estructural es que ninguna mutación larga viva
dentro de una request → se ENCOLA como job con recibo (`job_id`) y el resultado se
recoge después.

Responsabilidad única y testeable aislado: este módulo NO importa FastAPI ni conoce el
documento. Solo ejecuta closures en orden y guarda su resultado.

REGLA DE LOCKS: ``_cv`` es un lock HOJA — jamás se sostiene mientras se llama al closure
(que toma STATE_LOCK). El worker ejecuta ``fn()`` SIN lock propio y solo DESPUÉS escribe
el resultado. Orden imposible de invertir → sin deadlock contra STATE_LOCK/_flush_lock.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Callable

# Retención de TERMINADOS (los encolado/corriendo jamás se desalojan). Sin persistencia:
# un reload los pierde y está bien — son recibos, no datos (el autosave cubre el disco).
_RETENTION = 20
# Tope del long-poll de una llamada (el cliente hace varios polls hasta su presupuesto).
_MAX_WAIT_S = 30.0

_TERMINAL = ("ok", "error")


def _describe_error(exc: BaseException) -> tuple[str, int]:
    """(detail, http_status) de una excepción del closure. Duck-typing DELIBERADO sobre
    ``status_code``/``detail`` (la firma de HTTPException) para no importar FastAPI aquí:
    un ContractError diferido se ve IGUAL que el 400 de hoy, solo que fuera de la request.
    Cualquier otra excepción → 500 con su repr (nunca se traga en silencio)."""
    status = getattr(exc, "status_code", None)
    detail = getattr(exc, "detail", None)
    if isinstance(status, int) and detail is not None:
        return str(detail), status
    return repr(exc), 500


class JobStore:
    """Cola FIFO con UN worker daemon. No hay paralelismo que ganar (STATE_LOCK serializa
    igual) y un solo worker da orden DETERMINISTA — coherente con «un lote = UN regenerate»."""

    def __init__(self, retention: int = _RETENTION) -> None:
        self._cv = threading.Condition()
        self._jobs: dict[str, dict] = {}
        self._order: list[str] = []  # orden de creación (eviction FIFO de los terminados)
        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self.retention = retention

    # ------------------------------------------------------------------ API pública
    def submit(self, tipo: str, fn: Callable[[], dict]) -> str:
        """Encola ``fn`` y devuelve el recibo (``job_id``) al instante."""
        job_id = uuid.uuid4().hex[:8]
        with self._cv:
            self._jobs[job_id] = {
                "id": job_id,
                "tipo": tipo,
                "estado": "encolado",
                "resultado": None,
                "error": None,
                "http_status": None,
                "creado": time.time(),
                "terminado": None,
            }
            self._order.append(job_id)
            self._ensure_worker()
        self._queue.put((job_id, fn))
        return job_id

    def get(self, job_id: str, wait_s: float = 0.0) -> dict | None:
        """Estado del job; None si es desconocido (nunca existió, reload o desalojado).
        ``wait_s`` > 0 = LONG-POLL: despierta en cuanto el job termina (no al vencer el
        plazo) — el camino feliz no paga latencia de sondeo."""
        budget = max(0.0, min(float(wait_s), _MAX_WAIT_S))
        deadline = time.monotonic() + budget
        with self._cv:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            while job["estado"] not in _TERMINAL:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cv.wait(remaining)
                job = self._jobs.get(job_id)
                if job is None:  # imposible hoy (solo se desaloja lo terminado), pero honesto
                    return None
            return dict(job)

    def briefs(self) -> list[dict]:
        """Los jobs retenidos, sin `resultado` (el payload de escena es grande)."""
        with self._cv:
            return [
                {k: v for k, v in self._jobs[j].items() if k != "resultado"}
                for j in self._order
            ]

    # ------------------------------------------------------------------ interno
    def _ensure_worker(self) -> None:
        """Arranca el worker perezosamente (asume ``_cv`` sostenido): un proceso que nunca
        encola un job tampoco paga un hilo. Daemon: muere con el proceso."""
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(
                target=self._run, name="apolo-jobs", daemon=True
            )
            self._worker.start()

    def _run(self) -> None:
        while True:
            job_id, fn = self._queue.get()
            self._mark_running(job_id)
            try:
                resultado = fn()  # SIN lock propio: el closure toma STATE_LOCK (lock hoja)
            except BaseException as exc:  # noqa: BLE001 — el error viaja al job, no mata el worker
                detail, status = _describe_error(exc)
                self._finish(job_id, estado="error", error=detail, http_status=status)
            else:
                self._finish(job_id, estado="ok", resultado=resultado)

    def _mark_running(self, job_id: str) -> None:
        with self._cv:
            job = self._jobs.get(job_id)
            if job is not None:
                job["estado"] = "corriendo"
            self._cv.notify_all()

    def _finish(
        self,
        job_id: str,
        *,
        estado: str,
        resultado: dict | None = None,
        error: str | None = None,
        http_status: int | None = None,
    ) -> None:
        with self._cv:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(
                    estado=estado,
                    resultado=resultado,
                    error=error,
                    http_status=http_status,
                    terminado=time.time(),
                )
                self._evict()
            self._cv.notify_all()

    def _evict(self) -> None:
        """FIFO sobre los TERMINADOS (asume ``_cv`` sostenido). Un job encolado/corriendo
        jamás se desaloja: su dueño todavía espera el resultado."""
        done = [j for j in self._order if self._jobs[j]["estado"] in _TERMINAL]
        excess = len(done) - self.retention
        for jid in done[:excess] if excess > 0 else []:
            self._jobs.pop(jid, None)
            self._order.remove(jid)


# Mensaje del 404 (§3 del plan): HONESTO — el peor caso es el statu quo de hoy, nunca peor.
JOB_UNKNOWN = (
    "Job desconocido '{job_id}': nunca existió, el servidor se reinició (los jobs viven "
    "en MEMORIA) o ya fue desalojado (se retienen los últimos {retention} terminados). "
    "El lote PUDO haber aplicado —el autosave lo habría guardado en disco—: verifícalo "
    "con get_scene/health ANTES de reintentar. NUNCA reintentes el lote a ciegas."
)
