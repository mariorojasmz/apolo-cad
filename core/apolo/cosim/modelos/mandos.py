"""Mandos, señalización y sensores (plan V8.3 D1, D7, D12).

Los mandos no tienen física propia: guardan qué actuador está accionado, y la red de mando
(F3) abre o cierra sus contactos NA/NC según `Camino.actuador` (el `grupo` del camino o su
acción, «mano»). Lo que sí modelan es CÓMO vuelven:
  - pulsador con `retorno: resorte`: accionado mientras se lo pulsa (`pulsar` con `durante_s`
    lo suelta solo); `mantenido` alterna con cada pulsación;
  - seta (`retenido`): `presionar` la deja RETENIDA hasta `liberar` (ISO 13850);
  - selector (`mantenido`): `girar` a una de sus `posiciones`; `cierra_en` dice en qué
    posición está accionado cada actuador;
  - seccionador: `abrir`/`cerrar` (manija mantenida), accionado = cerrado.
Piloto: enciende desde `U_encendido_pct` de Un y consume `I_mA`. Sensor PNP: la detección
(rayo de MuJoCo en F4, o `forzar` para `sensor_pegado`) llega a la salida tras `t_respuesta_ms`
en cada flanco, si está alimentado.

Señales (D10): `-S1.accionado` (o una por actuador: `-S9.marcha`), `-S5.posicion`,
`-Q1.cerrado`, `-H1.encendido`, `-B1.activo`.
"""

from __future__ import annotations

from .base import EPS_T, Modelo, ModeloIncompleto, Parametros, magnitud


class _Mando(Modelo):
    def actuadores(self) -> dict[str, bool]:
        """{actuador: accionado} para la red de mando (F3)."""
        raise NotImplementedError

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        return self.salidas()

    def salidas(self) -> dict:
        act = self.actuadores()
        if list(act) == ["mano"]:
            return {"accionado": act["mano"]}
        return dict(act)


class Pulsador(_Mando):
    tipo = "pulsador"
    ACCIONES = ("pulsar", "soltar", "girar")

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.retorno = p.texto("retorno", "cómo vuelve el pulsador", ("resorte", "mantenido"))
        self.nombres = p.lista("actuadores", "actuadores (grupo de sus caminos)", defecto=["mano"])
        self.estado = {a: False for a in self.nombres}
        self.resta = {a: None for a in self.nombres}
        self.potenciometro = 0.0 if p.tiene("potenciometro_ohm") else None

    def _actuador(self, valor) -> tuple[str, float | None]:
        if isinstance(valor, dict):
            a, durante = valor.get("actuador"), valor.get("durante_s")
        else:
            a, durante = None, valor
        a = a or self.nombres[0]
        if a not in self.estado:
            raise ValueError(f"{self.designacion}: no tiene el actuador «{a}»; tiene {', '.join(self.nombres)}")
        return a, (float(durante) if durante is not None else None)

    def _accion_pulsar(self, valor=None) -> None:
        a, durante = self._actuador(valor)
        if self.retorno == "mantenido":
            self.estado[a] = not self.estado[a]
            return
        self.estado[a] = True
        self.resta[a] = durante

    def _accion_soltar(self, valor=None) -> None:
        a, _ = self._actuador(valor)
        if self.retorno == "resorte":
            self.estado[a], self.resta[a] = False, None

    def _accion_girar(self, valor) -> None:
        if self.potenciometro is None:
            raise ValueError(f"{self.designacion}: no tiene potenciómetro")
        self.potenciometro = min(1.0, max(0.0, float(valor)))

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        for a, resta in self.resta.items():
            if resta is not None:
                resta -= dt
                if resta <= EPS_T:
                    self.estado[a], resta = False, None  # vuelve por resorte
                self.resta[a] = resta
        return self.salidas()

    def actuadores(self) -> dict[str, bool]:
        return dict(self.estado)

    def salidas(self) -> dict:
        out = super().salidas()
        if self.potenciometro is not None:
            out["potenciometro"] = self.potenciometro
        return out


class Seta(_Mando):
    tipo = "seta"
    ACCIONES = ("presionar", "liberar")

    def __init__(self, p: Parametros):
        super().__init__(p)
        p.texto("retorno", "la seta queda retenida", ("retenido",))
        self.retenida = False

    def _accion_presionar(self, _v=None) -> None:
        self.retenida = True

    def _accion_liberar(self, _v=None) -> None:
        self.retenida = False

    def actuadores(self) -> dict[str, bool]:
        return {"mano": self.retenida}


class Selector(_Mando):
    tipo = "selector"
    ACCIONES = ("girar",)

    def __init__(self, p: Parametros):
        super().__init__(p)
        p.texto("retorno", "el selector queda donde se lo deja", ("mantenido",))
        self.posiciones = p.lista("posiciones", "posiciones del selector")
        self.cierra_en = {a: str(pos) for a, pos in p.mapa("cierra_en", "posición en que cierra cada actuador").items()}
        for a, pos in self.cierra_en.items():
            if pos not in self.posiciones:
                raise ModeloIncompleto(f"{p.quien}: «{a}» cierra en «{pos}», que no es una posición "
                                       f"({', '.join(self.posiciones)})")
        # condición inicial: la posición de reposo «0» si la hay (el escenario la fija)
        self.posicion = "0" if "0" in self.posiciones else self.posiciones[0]

    def _accion_girar(self, posicion) -> None:
        posicion = str(posicion)
        if posicion not in self.posiciones:
            raise ValueError(f"{self.designacion}: «{posicion}» no es una posición ({', '.join(self.posiciones)})")
        self.posicion = posicion

    def actuadores(self) -> dict[str, bool]:
        return {a: self.posicion == pos for a, pos in self.cierra_en.items()}

    def salidas(self) -> dict:
        return {"posicion": self.posicion, **{a: v for a, v in self.actuadores().items() if a != "mano"}}


class Seccionador(_Mando):
    tipo = "seccionador"
    ACCIONES = ("abrir", "cerrar")

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.Ith = p.num("Ith_A", "corriente térmica convencional", positivo=True)
        self.cerrado = True  # condición inicial: la máquina en servicio (el escenario la cambia)

    def _accion_abrir(self, _v=None) -> None:
        self.cerrado = False

    def _accion_cerrar(self, _v=None) -> None:
        self.cerrado = True

    def actuadores(self) -> dict[str, bool]:
        return {"mano": self.cerrado}

    def salidas(self) -> dict:
        return {"cerrado": self.cerrado}


class Piloto(Modelo):
    tipo = "piloto"

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.Un = p.num("Un_V", "tensión asignada", positivo=True)
        self.I = p.num("I_mA", "consumo a Un", positivo=True) / 1000
        self.umbral = p.num("U_encendido_pct", "tensión de encendido en % de Un", positivo=True) / 100
        self.encendido = False
        self.I_A = 0.0

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        u = magnitud((entradas or {}).get("U_V", 0.0))
        self.encendido = u >= self.umbral * self.Un - 1e-9
        self.I_A = self.I * min(u / self.Un, 1.1) if self.encendido else 0.0
        return self.salidas()

    def salidas(self) -> dict:
        return {"encendido": self.encendido, "I_A": self.I_A}


class Sensor(Modelo):
    tipo = "sensor"
    ACCIONES = ("forzar",)

    def __init__(self, p: Parametros):
        super().__init__(p)
        p.texto("salida", "tipo de salida", ("PNP",))
        self.contacto = p.texto("contacto", "salida NA o NC", ("NA", "NC"))
        self.t_resp = p.num("t_respuesta_ms", "tiempo de respuesta", minimo=0) / 1000
        self.U_min = p.num("U_alim_min_V", "alimentación mínima", positivo=True)
        self.I_max = p.num("I_salida_mA", "corriente máxima de la salida", positivo=True) / 1000
        self.t = 0.0
        self.activo = False
        self.forzado: bool | None = None

    def _accion_forzar(self, valor) -> None:
        """`sensor_pegado` (D12): True/False fija la detección; None la devuelve al mundo."""
        self.forzado = None if valor is None else bool(valor)

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        e = entradas or {}
        detecta = bool(e.get("detecta", False)) if self.forzado is None else self.forzado
        objetivo = (detecta != (self.contacto == "NC")) and float(e.get("U_alim_V", 0.0)) >= self.U_min
        if objetivo != self.activo:
            self.t += dt
            if self.t >= self.t_resp - EPS_T:
                self.activo, self.t = objetivo, 0.0
        else:
            self.t = 0.0
        return self.salidas()

    def salidas(self) -> dict:
        return {"activo": self.activo}
