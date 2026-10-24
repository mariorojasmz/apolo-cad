"""Mandos de seguridad de dos canales (plan mandos-de-seguridad D2, D3).

Interruptor de resguardo con actuador separado (ISO 14119 tipo 2), `resguardo`:
  - `cerrado` es el resguardo (la lengüeta adentro); `abrir` y `cerrar` lo mueven y arranca
    CERRADO (la máquina en servicio, como el seccionador; el escenario lo cambia);
  - sus contactos son NC de apertura positiva movidos por el actuador «<des>.abierto»: el
    interruptor se ACCIONA al sacar la lengüeta (IEC 60947-5-1 Anexo K), así que los NC están
    cerrados con el resguardo cerrado. Cada NC es una rama propia de la red: la falla `pegado`
    pega uno solo (cosim-fallas D3);
  - falla `trabado` (la de todo mando): el mecanismo no sigue a la lengüeta; el resguardo se
    abre igual (`cerrado` lo dice) y los contactos quedan donde estaban, o como diga el valor
    (true = cerrados). Reparado, el mecanismo vuelve a seguir a la lengüeta.

Relé de seguridad de dos canales con rearme vigilado, `rele_seguridad` (lo que publica la línea
de referencia, nada más):
  - lee de la red las entradas `BORNES_ENTRADA` (S12 y S22 los canales, S34 el rearme) y su
    alimentación A1-A2, con los umbrales de IEC 61131-2 tipo 1 (criterio de diseño: la ficha no
    da otros); sin `U_min_pct` de Un en A1-A2 abre y, al volver, arranca de cero;
  - las salidas (`salidas` de la ficha: los NA de seguridad) cierran sólo con los DOS canales
    cerrados y el flanco de BAJADA del rearme (actúa al SOLTAR el pulsador), tras
    `t_conexion_ms`; abren en cuanto abre CUALQUIER canal, tras `t_desconexion_ms`;
  - no rearman hasta que los DOS canales hayan abierto y cerrado otra vez: un canal pegado se
    nota en el ciclo siguiente (`espera_ciclo`). La simultaneidad con tiempo (discrepancia en
    ms) NO se modela (cosim-fallas D10): va como hipótesis del resultado;
  - el contacto auxiliar «aux» (NC de señal, de guía forzada con los de seguridad) abre mientras
    algún NA de seguridad está cerrado;
  - fallas: `salida_pegada` {salida} (ese NA queda soldado; los relés de guía forzada lo ven y
    el relé NO rearma mientras dure, EN 50205) y `detenido` (salidas a 0, no rearma; reparado,
    pide el rearme).

Señales (D10): `-B2.cerrado`; `-K2.salidas`, `-K2.canal1`, `-K2.canal2`, `-K2.espera_ciclo`,
`-K2.estado`.
"""

from __future__ import annotations

from .base import EPS_T, Modelo, Parametros, entrada_tipo1, magnitud
from .mandos import _Mando


class Resguardo(_Mando):
    tipo = "resguardo"
    ACCIONES = ("abrir", "cerrar")

    def __init__(self, p: Parametros):
        super().__init__(p)
        p.texto("actuador", "el actuador del interruptor", ("separado",))
        self.cerrado = True     # el resguardo (la lengüeta adentro)
        self.contactos = True   # el mecanismo: sus NC cerrados

    def accionar(self, accion: str, valor=None) -> None:
        Modelo.accionar(self, accion, valor)  # trabado: el resguardo se mueve igual (ver abajo)

    def _mover(self, cerrado: bool) -> None:
        self.cerrado = cerrado
        if not self.trabado:
            self.contactos = cerrado

    def _accion_abrir(self, _v=None) -> None:
        self._mover(False)

    def _accion_cerrar(self, _v=None) -> None:
        self._mover(True)

    def _quedar(self, valor) -> None:
        self.contactos = self._bool(valor, f"{self.designacion}: el interruptor trabado (true = contactos cerrados)")

    def _reparar_trabado(self, _v=None) -> None:
        self.trabado = False
        self.contactos = self.cerrado

    def actuadores(self) -> dict[str, bool]:
        return {"abierto": not self.contactos}

    def salidas(self) -> dict:
        return {"cerrado": self.cerrado}


class ReleSeguridad(Modelo):
    tipo = "rele_seguridad"
    FALLAS = {"salida_pegada": "salida", "detenido": ""}
    #: Lo que lee de la red: cargas `entrada` de cada borne a A2 (las arma `services/cosim_red`).
    BORNES_ENTRADA = ("S12", "S22", "S34")
    detenido = False

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.Un = p.num("Un_V", "tensión asignada de alimentación", positivo=True)
        self.U_min = p.num("U_min_pct", "alimentación mínima en % de Un", positivo=True) / 100 * self.Un
        p.texto("rearme", "el rearme del relé", ("vigilado",))
        self.ids_salida = p.lista("salidas", "los NA de seguridad (sus bornes, «13-14»)")
        self.t_con = p.de_banda("t_conexion_ms", "tiempo de conexión tras el rearme") / 1000
        self.t_desc = p.de_banda("t_desconexion_ms", "tiempo de desconexión al abrir un canal") / 1000
        self.hipotesis.append("el relé de seguridad no modela la discrepancia en ms entre sus dos "
                              "canales (cosim-fallas D10): sólo exige que los dos abran y cierren "
                              "antes de rearmar")
        self.estado = "abierto"   # abierto | conectando | cerrado | desconectando
        self.t = 0.0
        self.canal = [False, False]
        self.rearme = False
        self.alimentado = False
        self.espera_ciclo = False
        self._abrio = [False, False]
        self.pegadas: set[str] = set()

    @property
    def cerradas(self) -> bool:
        return self.estado in ("cerrado", "desconectando")

    def _abre_un_canal(self) -> None:
        """Hasta un rearme nuevo, los dos canales tienen que abrir y cerrar (se cuenta desde aquí)."""
        self.espera_ciclo = True
        self._abrio = [not c for c in self.canal]

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        e = entradas or {}
        alimentado = magnitud(e.get("U_alim_V", 0.0)) >= self.U_min - 1e-9
        self.canal = [entrada_tipo1(float(e.get(b, 0.0)), prev) for b, prev in zip(("S12", "S22"), self.canal)]
        rearme = entrada_tipo1(float(e.get("S34", 0.0)), self.rearme)
        soltado = self.rearme and not rearme
        self.rearme = rearme
        if not alimentado:
            self.estado, self.t, self.espera_ciclo = "abierto", 0.0, False  # al volver, de cero
            self.canal = [False, False]
            self.rearme = False
        self.alimentado = alimentado
        if self.espera_ciclo:
            self._abrio = [a or not c for a, c in zip(self._abrio, self.canal)]
            if all(self._abrio) and all(self.canal):
                self.espera_ciclo = False
        ambos = all(self.canal)
        if self.detenido and self.estado != "abierto":
            self.estado, self.t = "abierto", 0.0
        if self.estado == "abierto":
            if (soltado and ambos and alimentado and not self.espera_ciclo and not self.detenido
                    and not self.pegadas):
                self.estado, self.t = "conectando", 0.0
        elif self.estado == "conectando":
            if not ambos:
                self._abre_un_canal()
                self.estado, self.t = "abierto", 0.0
            else:
                self.t += dt
                if self.t >= self.t_con - EPS_T:
                    self.estado = "cerrado"
        elif self.estado == "cerrado":
            if not ambos:
                self._abre_un_canal()
                self.estado, self.t = "desconectando", 0.0
        if self.estado == "desconectando":
            self.t += dt
            if self.t >= self.t_desc - EPS_T:
                self.estado, self.t = "abierto", 0.0
        return self.salidas()

    def actuadores(self) -> dict[str, bool]:
        out = {f"salida_{s.split('-')[0]}": self.cerradas or s in self.pegadas for s in self.ids_salida}
        out["aux"] = any(out.values())
        return out

    def salidas(self) -> dict:
        return {"salidas": self.cerradas, "canal1": self.canal[0], "canal2": self.canal[1],
                "espera_ciclo": self.espera_ciclo, "estado": self.estado}

    # ── fallas ──────────────────────────────────────────────────────────────────────────────

    def _salida(self, valor) -> str:
        s = valor.get("salida") if isinstance(valor, dict) else valor
        if s not in self.ids_salida:
            raise ValueError(f"{self.designacion}: «salida_pegada» pide la salida de seguridad, una de "
                             f"{', '.join(self.ids_salida)} (llegó {valor!r})")
        return s

    def _falla_salida_pegada(self, valor) -> str:
        s = self._salida(valor)
        self.pegadas.add(s)
        return f"salida_pegada {s}"

    def _reparar_salida_pegada(self, valor=None) -> list[str]:
        ss = sorted(self.pegadas) if valor is None else [self._salida(valor)]
        self.pegadas.difference_update(ss)
        return [f"salida_pegada {s}" for s in ss]

    def _falla_detenido(self, _v=None) -> None:
        self.detenido = True
        if self.estado != "abierto":
            self.estado, self.t = "abierto", 0.0

    def _reparar_detenido(self, _v=None) -> None:
        self.detenido = False
