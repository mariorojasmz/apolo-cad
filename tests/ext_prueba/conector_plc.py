"""El conector a un PLC de afuera de la extensión falsa (D4, D5 y D15 de plc-en-el-lazo): habla
JSON por línea sobre TCP con `plc_falso.py` (un `apolo.plc.PLC` con reloj de pared en otro
proceso). Un pedido por miembro que cambia el PLC; `paso` lleva las entradas y trae todo lo que
la corrida lee después (salidas, estado, falla, scans, variables), así el intercambio es UNA ida y
vuelta. La red se importa al conectar (`red_plc`), no al importarse este módulo. Para la sesión
en vivo (F1b2) trae los opcionales `pausar`/`reanudar` (el PLC falso los anota) y `reconectar`.

Además, las variantes que el núcleo debe RECHAZAR al cargar la extensión (sin un miembro, sin
`validar_config`, un opcional que no es llamable).
"""

from __future__ import annotations

from apolo.extensiones_api import LazoCortado


class ConectorTCP:
    """`config`: {"host": "127.0.0.1", "puerto": N, "timeout_s": 2.0 (opcional)}."""

    compilado: object
    estado: str
    salidas: dict
    falla: dict | None
    fallas: list
    scans: int

    @staticmethod
    def validar_config(config: dict) -> list[str]:
        out = [f"clave «{k}» desconocida (host, puerto, timeout_s)"
               for k in sorted(set(config) - {"host", "puerto", "timeout_s"})]
        if not isinstance(config.get("host"), str) or not config.get("host"):
            out.append("falta «host» (texto: la IP o el nombre del PLC)")
        p = config.get("puerto")
        if isinstance(p, bool) or not isinstance(p, int) or not 0 < p < 65536:
            out.append("«puerto» es un entero de 1 a 65535")
        t = config.get("timeout_s", 2.0)
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not t > 0:
            out.append("«timeout_s» es un número > 0 (s)")
        return out

    def __init__(self, programa, config: dict):
        self.compilado = programa.compilado
        self.estado, self.salidas, self.falla, self.fallas, self.scans = "SIN_TENSION", {}, None, [], 0
        self._vars: dict = {}
        self._entradas: dict = {}
        self._config = dict(config)
        self._red = None
        self._abrir()

    def _abrir(self) -> None:
        from . import red_plc  # la «librería de red», al conectar (D5)

        c = self._config
        try:
            self._red = red_plc.abrir(c["host"], c["puerto"], float(c.get("timeout_s", 2.0)))
        except OSError as exc:
            raise LazoCortado(f"{c['host']}:{c['puerto']} no contesta ({type(exc).__name__})") from exc
        self._pedir({"op": "hola"})

    def _pedir(self, msg: dict) -> dict:
        try:
            r = self._red.pedir(msg)
        except (OSError, ValueError) as exc:
            raise LazoCortado(f"{type(exc).__name__}: {exc}") from exc
        if r is None:
            raise LazoCortado("el PLC cerró la conexión")
        self.estado, self.salidas, self.falla = r["estado"], r["salidas"], r["falla"]
        self.fallas, self.scans, self._vars = r["fallas"], r["scans"], r["variables"]
        return r

    def escribir_entrada(self, borne: str, valor) -> None:
        self._entradas[borne] = int(valor) if borne.startswith("AI") else bool(valor)

    def paso(self, t_ms: int) -> dict:
        self._pedir({"op": "paso", "t_ms": t_ms, "entradas": self._entradas})
        return self.salidas

    def cortar(self) -> None:
        self._pedir({"op": "cortar"})

    def reponer(self, t_ms: int) -> None:
        self._pedir({"op": "reponer"})

    def stop(self) -> None:
        self._pedir({"op": "stop"})

    def run(self, t_ms: int) -> None:
        self._pedir({"op": "run"})

    def variables(self) -> dict:
        return dict(self._vars)

    # opcionales de la sesión en vivo (D8): el PLC falso anota la pausa en su salida
    def pausar(self) -> None:
        self._pedir({"op": "pausar"})

    def reanudar(self) -> None:
        self._pedir({"op": "reanudar"})

    def reconectar(self) -> None:
        """Tras un corte: la conexión de nuevo, al mismo PLC (`LazoCortado` si no contesta)."""
        if self._red is not None:
            self._red.cerrar()
        self._abrir()

    def cerrar(self) -> None:
        if self._red is not None:
            self._red.cerrar()


# ── lo que el núcleo rechaza al cargar ───────────────────────────────────────────────────────

class SinPaso:
    """Le falta `paso` y no declara `scans`."""

    compilado: object
    estado: str
    salidas: dict
    falla: dict | None
    fallas: list

    @staticmethod
    def validar_config(config):
        return []

    def escribir_entrada(self, borne, valor): ...
    def cortar(self): ...
    def reponer(self, t_ms): ...
    def stop(self): ...
    def run(self, t_ms): ...
    def variables(self): return {}


class SinValidar(ConectorTCP):
    validar_config = None


class CerrarNoLlamable(ConectorTCP):
    cerrar = "no"
