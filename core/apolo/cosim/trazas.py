"""Las trazas de una co-simulación (plan V8.3 D9, D10).

  - DISCRETAS (bool, entero, texto: «-K1.cerrado», «-T1.estado», «-A1.%IX0.0», un INT del PLC):
    por CAMBIO, `[[t, valor], …]` desde su valor en t = 0;
  - ANALÓGICAS (float: «-M1.rpm», «-W1.1.I_A», «<pieza>.v_m_s»): muestreadas a `analogicas_hz`
    (50 Hz por defecto), redondeadas a 6 decimales, en columnas alineadas con `t` (None donde
    la señal todavía no existe: un producto que aún no entró).
`huella()` es el sha256 del JSON canónico de las trazas, los eventos y los valores finales: el
mismo escenario sobre el mismo snapshot da la MISMA huella, bit a bit (D9).
"""

from __future__ import annotations

import hashlib
import json

_NADA = object()


def _es_discreta(v) -> bool:
    """bool, entero, texto o lista (un ARRAY del PLC): por cambio. Un float es analógica."""
    return isinstance(v, (bool, int, str, list)) and not isinstance(v, float)


class Trazas:
    def __init__(self, analogicas_hz: float, dt: float):
        self.cada = max(1, int(round(1.0 / (analogicas_hz * dt))))
        self.discretas: dict[str, list] = {}
        self._ultimo: dict = {}
        self.t: list[float] = []
        self.analogicas: dict[str, list] = {}
        self.final: dict = {}
        self._clases: dict = {}

    def registrar(self, k: int, t: float, fuentes: list, analogicas_extra=None, *,
                  forzar: bool = False) -> None:
        """`fuentes` = [(prefijo, {nombre corto: valor})] de este intercambio (las salidas de cada
        modelo y de cada PLC); `analogicas_extra()` (redes y mecánica, caras) se llama sólo cuando
        toca muestrear (o con `forzar`: el último intercambio). La clase de cada señal (discreta o
        analógica) se fija la primera vez que se ve su fuente."""
        tt = round(t, 6)
        muestra = forzar or k % self.cada == 0
        fila: dict = {}
        ultimo, discretas, clases = self._ultimo, self.discretas, self._clases
        for pref, s in fuentes:
            clase = clases.get(pref)
            if clase is None or clase[0] != len(s):
                clase = clases[pref] = (len(s), [(c, pref + c) for c, v in s.items() if _es_discreta(v)],
                                        [(c, pref + c) for c, v in s.items() if isinstance(v, float)])
            for c, n in clase[1]:
                v = s[c]
                if ultimo.get(n, _NADA) != v:
                    ultimo[n] = v
                    discretas.setdefault(n, []).append([tt, v])
            if muestra:
                for c, n in clase[2]:
                    fila[n] = round(s[c], 6)
        if not muestra:
            return
        if analogicas_extra is not None:
            fila.update({n: round(float(v), 6) for n, v in analogicas_extra().items()})
        j = len(self.t)
        self.t.append(tt)
        for n, v in fila.items():
            col = self.analogicas.get(n)
            if col is None:
                col = self.analogicas[n] = [None] * j
            col.append(v)
        for col in self.analogicas.values():
            if len(col) <= j:
                col.append(None)

    def cerrar(self) -> dict:
        """Los valores al final: la última muestra de cada analógica y el último de cada discreta."""
        self.final = {**{n: col[-1] for n, col in self.analogicas.items()}, **self._ultimo}
        return self.final

    def salida(self) -> dict:
        return {"discretas": self.discretas, "analogicas": {"t": self.t, "senales": self.analogicas}}


def huella(trazas: dict, eventos: list, final: dict) -> str:
    """sha256 del JSON canónico (claves ordenadas, floats por `repr`): D9."""
    texto = json.dumps({"trazas": trazas, "eventos": eventos, "final": final}, sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
