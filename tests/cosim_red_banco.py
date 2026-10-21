"""Banco de prueba de las redes de F3: un tablero de V8.1 → formato plano → las dos redes, con los
modelos de F2 de sus dispositivos, acoplados a mano en cada intercambio de 2 ms.

NO es el planificador de F4 (que además mueve MuJoCo y el PLC): es lo mínimo para probar que las
redes reciben los estados de los modelos y les devuelven lo que consumen. El orden de un paso:
  1. potencia, con la red de su modelo y las cargas de potencia del paso anterior;
  2. la fuente de 24 V con la tensión de su entrada y la corriente que pidió el mando;
  3. mando, con la tensión de la fuente;
  4. cada modelo con sus tensiones y corrientes; sus estados mueven los contactos del paso que viene.
"""

from __future__ import annotations

from apolo.cosim.modelos import (
    Contactor,
    Fuente,
    Fusible,
    Guardamotor,
    Itm,
    Piloto,
    Red,
    ReleTermico,
    Seccionador,
    crear_modelo,
)
from apolo.cosim.modelos.mandos import _Mando
from apolo.cosim.red import armar
from apolo.services.cosim_red import entrada_red

DT = 0.002


class Banco:
    def __init__(self, modelo_electrico, *, ajustes: dict | None = None):
        self.entrada = entrada_red(modelo_electrico)
        self.redes = armar(self.entrada)
        self.modelos = {}
        for d in modelo_electrico.dispositivos:
            aj = {**d.ajustes, **(ajustes or {}).get(d.designacion, {})}
            m = crear_modelo(d.designacion, d.ref, d.modelo, aj, cantidad=d.cantidad)
            if m is not None:
                self.modelos[d.designacion] = m
        self.t = 0.0
        self.mando = self.potencia = None

    def estados(self) -> dict:
        out: dict = {}
        for des, m in self.modelos.items():
            if isinstance(m, Contactor):
                out[f"{des}.bobina"] = m.cerrado
            elif isinstance(m, (Itm, Guardamotor)):
                out[f"{des}.cerrado"] = m.cerrado
            elif isinstance(m, ReleTermico):
                out[f"{des}.disparo"] = m.disparado
            elif isinstance(m, Fusible):
                for k, f in enumerate(m.fundido):
                    out[f"{des}.{k + 1}.cerrado"] = not f
                out[f"{des}.cerrado"] = not any(m.fundido)
            elif isinstance(m, (Seccionador, _Mando)):
                for a, v in m.actuadores().items():
                    out[f"{des}.{a}"] = v
        return out

    def _corrientes(self, des: str) -> list[float]:
        out = []
        for red, res in ((self.redes.potencia, self.potencia), (self.redes.mando, self.mando)):
            if red is None or res is None:
                continue
            for r in red.dom.ramas:
                if r.dispositivo == des and r.tipo == "contacto" and r.contacto == "proteccion":
                    out.append(abs(res.corriente(r.id)))
        return out

    def _carga(self, cid: str) -> dict:
        for red, res in ((self.redes.mando, self.mando), (self.redes.potencia, self.potencia)):
            if red is not None and res is not None and (cid in red._carga_idx or cid in red.dom.sin_cablear):
                return res.carga(cid)
        raise KeyError(cid)

    def paso(self, dt: float = DT) -> None:
        est = self.estados()
        fuentes_ac, cargas_ac, fuentes_dc = {}, {}, {}
        for des, m in self.modelos.items():
            if isinstance(m, Red):
                fuentes_ac[des] = m.salidas()
            elif isinstance(m, Fuente):
                fuentes_dc[des] = m.U
                cid = next((c["id"] for c in self.entrada["cargas"] if c["dispositivo"] == des
                            and c["tipo"] == "alimentacion"), None)
                if cid:
                    cargas_ac[cid] = {"S": complex(m.salidas()["P_entrada_W"], 0.0)}
        if self.redes.potencia is not None:
            self.potencia = self.redes.potencia.paso(est, fuentes_ac, cargas_ac)
        pedidas = self.redes.mando.pedidas(est) if self.redes.mando is not None else {}
        for des, m in self.modelos.items():
            if isinstance(m, Fuente):
                u_in = self._carga(f"{des}:L-N")["U_V"]
                m.paso(dt, {"U_entrada_V": u_in, "I_carga_A": pedidas.get(des, 0.0)})
                fuentes_dc[des] = m.U
        if self.redes.mando is not None:
            self.mando = self.redes.mando.paso(est, fuentes_dc)
        for des, m in self.modelos.items():
            if isinstance(m, Contactor):
                m.paso(dt, {"U_bobina_V": abs(self._carga(f"{des}:A1-A2")["U_V"])})
            elif isinstance(m, Piloto):
                m.paso(dt, {"U_V": abs(self._carga(f"{des}:X1-X2")["U_V"])})
            elif isinstance(m, (Itm, Guardamotor, ReleTermico, Fusible)):
                m.paso(dt, {"I_A": self._corrientes(des)})
            elif isinstance(m, (Red, Fuente)):
                continue
            else:
                m.paso(dt, {})
        self.t += dt

    def correr(self, segundos: float) -> None:
        for _ in range(round(segundos / DT)):
            self.paso()
