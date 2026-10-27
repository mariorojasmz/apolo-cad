"""ERC estático del modelo eléctrico (plan V8.1 F2, D7).

Dos tableros BIEN cableados con refs del catálogo eléctrico dan cero errores (y cero avisos):
  (a) arranque directo: red → seccionador → guardamotor → contactor → motor + PE, con mando de
      24 VDC (fuente, seta NC, paro NC, marcha NA, enclavamiento por el auxiliar 13-14, bobina);
  (b) arranque por variador: red → ITM → VFD-2K2-220 → NMRV-090, PLC que manda la DI1 del
      variador por su salida, seta en el lazo STO, fotocelda a una entrada del PLC.
Y cada regla de D7 se dispara con su error/aviso sobre una variante mínima de esos tableros.
"""

from __future__ import annotations

import dataclasses

import pytest

from apolo.library.catalog import CATALOG
from apolo.library.electrico.acoples import cerrar_acoples
from apolo.library.electrico.erc import erc, resumen
from apolo.library.electrico.modelo import (
    Cable,
    Conductor,
    ModeloElectrico,
    dispositivo_desde_ficha,
)
from apolo.library.electrico.redes import analizar


def disp(des: str, ref: str, **kw):
    return dispositivo_desde_ficha(des, ref, CATALOG[ref].electrico, ubicacion=kw.pop("ubicacion", "+TAB1"), **kw)


def w(*puntos: str, color: str | None = None, seccion: float = 1.0, cable: str | None = None,
      hilo: str | None = None) -> Conductor:
    return Conductor(tuple(puntos), seccion_mm2=seccion, color=color, cable=cable, hilo=hilo)


def cable(des: str, ref: str) -> Cable:
    ficha = CATALOG[ref].electrico.conductor
    return Cable(des, ref, hilos=ficha.hilos, seccion_mm2=ficha.seccion_mm2)


def errores(reglas: list[dict], regla: str | None = None) -> list[dict]:
    return [r for r in reglas if r["estado"] == "error" and (regla is None or r["regla"] == regla)]


def avisos(reglas: list[dict], regla: str | None = None) -> list[dict]:
    return [r for r in reglas if r["estado"] == "aviso" and (regla is None or r["regla"] == regla)]


# ── (a) arranque directo ──────────────────────────────────────────────────────────────────


def arranque_directo() -> ModeloElectrico:
    dispositivos = (
        disp("-G1", "RED-3F-220V-60HZ", ubicacion="+RED"),
        disp("-Q1", "SECC-25A-3P"),
        disp("-Q2", "GM-2.5-4A"),
        disp("-Q3", "CONT-9A-24VDC"),
        disp("-Q3A", "CONT-AUX-1NA1NC"),
        disp("-M1", "MOTOR-075", ubicacion="+CAMPO", ajustes={"conexion": "triangulo"}),
        disp("-F1", "ITM-C2-2P"),
        disp("-T1", "FUENTE-24VDC-2.5A"),
        disp("-S0", "ESTOP-40"),
        disp("-S1", "PULS-22-ROJO-NC"),
        disp("-S2", "PULS-22-VERDE-NA"),
        disp("-P1", "PILOTO-24V-VERDE"),
        disp("-X0", "BORNE-PE-4", cantidad=2),
        disp("-U1", "GAB-6040"),
    )
    pot = dict(color="BK", seccion=2.5)
    conductores = (
        # potencia: red → seccionador → guardamotor → contactor
        w("-G1:L1", "-Q1:1", **pot), w("-G1:L2", "-Q1:3", **pot), w("-G1:L3", "-Q1:5", **pot),
        w("-Q1:2", "-Q2:1", **pot), w("-Q1:4", "-Q2:3", **pot), w("-Q1:6", "-Q2:5", **pot),
        w("-Q2:2", "-Q3:1", **pot), w("-Q2:4", "-Q3:3", **pot), w("-Q2:6", "-Q3:5", **pot),
        # contactor → motor por el cable -W1 (4G1,5)
        w("-Q3:2", "-M1:U1", cable="-W1", hilo="1"), w("-Q3:4", "-M1:V1", cable="-W1", hilo="2"),
        w("-Q3:6", "-M1:W1", cable="-W1", hilo="3"), w("-X0:2", "-M1:PE", cable="-W1", hilo="PE"),
        # tierra
        w("-G1:PE", "-X0:1", color="GNYE", seccion=4), w("-X0:1", "-X0:2", color="GNYE"),
        w("-X0:1", "-T1:PE", color="GNYE"), w("-X0:1", "-U1:PE", color="GNYE"),
        # fuente de 24 VDC: entre dos fases, por un ITM 2P aguas abajo del seccionador
        w("-Q1:2", "-F1:1", **pot), w("-Q1:4", "-F1:3", **pot),
        w("-F1:2", "-T1:L", color="BK"), w("-F1:4", "-T1:N", color="BK"),
        w("-T1:M", "-X0:1", color="GNYE"),  # 0 V del mando unido al PE
        # mando: +24 → seta → paro → marcha ∥ enclavamiento → bobina → 0 V
        w("-T1:L+", "-S0:11", "-Q3A:53", color="BU", seccion=0.75),
        w("-S0:12", "-S1:11", color="BU", seccion=0.75),
        w("-S1:12", "-S2:13", "-Q3:13", color="BU", seccion=0.75),
        w("-S2:14", "-Q3:14", "-Q3:A1", color="BU", seccion=0.75),
        w("-Q3:A2", "-T1:M", color="BU", seccion=0.75),
        # piloto de marcha por el bloque auxiliar
        w("-Q3A:54", "-P1:X1", color="BU", seccion=0.75),
        w("-P1:X2", "-T1:M", color="BU", seccion=0.75),
    )
    # como el carril al cerrar el modelo: -Q3A dice que lo mueve -Q3 (pedidos-de-extensiones D4)
    return ModeloElectrico(cerrar_acoples(dispositivos), conductores, (cable("-W1", "CABLE-4G1.5"),))


# ── (b) arranque por variador con PLC ─────────────────────────────────────────────────────


def arranque_variador() -> ModeloElectrico:
    dispositivos = (
        disp("-G1", "RED-3F-220V-60HZ", ubicacion="+RED"),
        disp("-Q1", "SECC-25A-3P"),
        disp("-F1", "ITM-C16-3P"),
        disp("-T2", "VFD-2K2-220", ajustes={"STO_categoria": 1}),  # la seta de un NC: categoría 1
        disp("-M1", "NMRV-090", ubicacion="+CAMPO", ajustes={"conexion": "triangulo"}),
        disp("-F2", "ITM-C2-2P"),
        disp("-T1", "FUENTE-24VDC-5A"),
        disp("-K1", "PLC-14DI-10DO-24VDC"),
        disp("-S0", "ESTOP-40"),
        disp("-S1", "BOTONERA-2", ubicacion="+CAMPO"),
        disp("-B1", "FOTO-M18", ubicacion="+CAMPO"),
        disp("-P1", "PILOTO-24V-VERDE"),
        disp("-X0", "BORNE-PE-4"),
        disp("-U1", "GAB-8060"),
    )
    pot = dict(color="BK", seccion=2.5)
    bu = dict(color="BU", seccion=0.75)
    conductores = (
        # potencia
        w("-G1:L1", "-Q1:1", **pot), w("-G1:L2", "-Q1:3", **pot), w("-G1:L3", "-Q1:5", **pot),
        w("-Q1:2", "-F1:1", **pot), w("-Q1:4", "-F1:3", **pot), w("-Q1:6", "-F1:5", **pot),
        w("-F1:2", "-T2:L1", **pot), w("-F1:4", "-T2:L2", **pot), w("-F1:6", "-T2:L3", **pot),
        # variador → motor por el cable -W1
        w("-T2:U", "-M1:U1", cable="-W1", hilo="1"), w("-T2:V", "-M1:V1", cable="-W1", hilo="2"),
        w("-T2:W", "-M1:W1", cable="-W1", hilo="3"), w("-T2:PE", "-M1:PE", cable="-W1", hilo="PE"),
        # tierra
        w("-G1:PE", "-X0:1", color="GNYE", seccion=4),
        # en estrella: cada aparato con su conductor PE hasta la bornera (IEC 60204-1 §8.2.3)
        w("-X0:1", "-T2:PE", color="GNYE"), w("-X0:1", "-T1:PE", color="GNYE"),
        w("-X0:1", "-K1:PE", color="GNYE"), w("-X0:1", "-U1:PE", color="GNYE"),
        # fuente de 24 VDC por el ITM 2P
        w("-Q1:2", "-F2:1", **pot), w("-Q1:4", "-F2:3", **pot),
        w("-F2:2", "-T1:L", color="BK"), w("-F2:4", "-T1:N", color="BK"),
        w("-T1:M", "-X0:1", color="GNYE"),
        # alimentación del PLC (CPU + salidas) y comunes
        w("-T1:L+", "-K1:L+", "-K1:3L+", **bu),
        w("-T1:M", "-K1:M", "-K1:3M", "-K1:1M", "-T2:COM", "-T2:SCM", **bu),
        # salida Q0.0 → marcha del variador; Q0.1 → piloto
        w("-K1:Q0.0", "-T2:DI1", **bu),
        w("-K1:Q0.1", "-P1:X1", **bu), w("-P1:X2", "-T1:M", **bu),
        # seta en el lazo STO (S1, S2) y leída por el PLC (I0.1)
        w("-T1:L+", "-S0:11", **bu),
        w("-S0:12", "-T2:S1", "-T2:S2", "-K1:I0.1", **bu),
        # botonera: marcha → I0.2, paro → I0.3, potenciómetro → AI1 del variador
        w("-T1:L+", "-S1:13", "-S1:21", **bu),
        w("-S1:14", "-K1:I0.2", **bu), w("-S1:22", "-K1:I0.3", **bu),
        w("-T2:+10V", "-S1:P1", **bu), w("-T2:GND", "-S1:P3", **bu), w("-S1:P2", "-T2:AI1", **bu),
        # relé de falla del variador → I0.4
        w("-T1:L+", "-T2:RC", **bu), w("-T2:RA", "-K1:I0.4", **bu),
        # fotocelda por el cable de sensor -W2 → I0.0
        w("-T1:L+", "-B1:BN", cable="-W2", hilo="BN"), w("-B1:BU", "-T1:M", cable="-W2", hilo="BU"),
        w("-B1:BK", "-K1:I0.0", cable="-W2", hilo="BK"),
    )
    cables = (cable("-W1", "CABLE-4G1.5"), cable("-W2", "CABLE-3X0.75"))
    return ModeloElectrico(dispositivos, conductores, cables)


@pytest.mark.parametrize("armar, sto", [(arranque_directo, []), (arranque_variador, ["canales del STO"])])
def test_tableros_bien_cableados_quedan_verdes(armar, sto):
    reglas = erc(armar())
    malas = [r for r in reglas if r["estado"] != "ok"]
    assert not malas, "\n".join(f"{r['regla']}: {r['detalle']}" for r in malas)
    assert resumen(reglas) == {"estado": "ok", "errores": 0, "avisos": 0}
    # una entrada por regla de D7, cada una con su norma o «criterio de diseño»; la del STO,
    # sólo con un variador que lo tiene; la del hilo PE, sólo con un cable que lo lleva
    assert [r["regla"] for r in reglas] == [
        "referencias", "designación duplicada", "cortocircuito", "tensión cruzada",
        "protección del motor", "puesta a tierra", "PE en cadena", "hilo de protección sin conectar",
        "borne suelto",
        "color del conductor", "parada de emergencia", *sto]
    assert all(r["norma"] for r in reglas)


def test_redes_e_inferencia_de_tension_del_arranque_directo():
    a = analizar(arranque_directo())
    red_motor = a.redes[a.red("-M1", "U1")]
    assert red_motor.potenciales == ("-G1:L1",)  # peor caso: seccionador, guardamotor y contactor cerrados
    assert red_motor.directos == ()  # sin cerrar nada, el motor no recibe nada
    assert "220 VAC 3F 60 Hz" in red_motor.tension
    red_bobina = a.redes[a.red("-Q3", "A1")]
    assert red_bobina.potenciales == ("-T1:+",)
    assert a.redes[a.red("-T1", "M")].directos == ("-G1:PE", "-T1:-")  # 0 V unido al PE
    # cada motor llega protegido (pasó por el guardamotor)
    assert all(ll.protegido for ll in a.llegadas[a.red("-M1", "V1")])


def test_variador_da_su_propio_sistema_al_motor():
    a = analizar(arranque_variador())
    # el variador tiene dos fuentes (salida y +10 V): sistemas -T2.1 y -T2.2
    assert a.redes[a.red("-M1", "U1")].potenciales == ("-T2.1:L1",)
    assert a.redes[a.red("-S1", "P1")].directos == ("-T2.2:+",)
    # la entrada DI1 recibe el +24 por la salida Q0.0 (camino 3L+ → Q0.0 cerrado)
    llegadas = a.llegadas[a.red("-T2", "DI1")]
    assert {ll.potencial.etiqueta for ll in llegadas} == {"-T1:+"}
    assert llegadas[0].via == ("-K1:3L+-Q0.0",)


# ── una regla de D7 por test ──────────────────────────────────────────────────────────────


def _con(modelo: ModeloElectrico, *, quitar: tuple[int, ...] = (), agregar=(), dispositivos=None,
         cambiar: dict[int, Conductor] | None = None) -> ModeloElectrico:
    conds = list(modelo.conductores)
    for i, c in (cambiar or {}).items():
        conds[i] = c
    conds = [c for i, c in enumerate(conds) if i not in quitar]
    return dataclasses.replace(modelo, conductores=tuple(conds) + tuple(agregar),
                               dispositivos=dispositivos or modelo.dispositivos)


def _idx(modelo: ModeloElectrico, *puntos: str) -> int:
    return next(i for i, c in enumerate(modelo.conductores) if c.puntos[: len(puntos)] == puntos)


def test_referencia_inexistente_con_sugerencia():
    m = arranque_directo()
    reglas = erc(_con(m, agregar=(w("-Q3:A1", "-K9:A2"), w("-Q3:A1", "-Q3:A3"), w("Q3:A1", "-T1:M"))))
    det = " | ".join(r["detalle"] for r in errores(reglas, "referencias"))
    assert "-K9 no existe" in det
    assert "no tiene el borne A3" in det and "¿Quisiste decir: A1, A2" in det
    assert "le falta el dispositivo" in det and "«-Q3:A1»" in det


def test_aspectos_de_funcion_y_de_lugar_en_las_referencias():
    k1 = disp("=Faja1-K1", "RELE-INT-24VDC")
    k2 = disp("=Faja2-K1", "RELE-INT-24VDC")
    fuente = disp("-T1", "FUENTE-24VDC-2.5A")
    solo = ModeloElectrico((k1, fuente), (w("-T1:L+", "-K1:A1", "+TAB1-K1:A2"),))
    assert not errores(erc(solo), "referencias")  # «-K1» basta si hay un solo -K1
    dos = ModeloElectrico((k1, k2, fuente), (w("-T1:L+", "-K1:A1"), w("-T1:M", "=Faja2-K1:A2"),
                                             w("-T1:M", "+CAMPO-T1:M")))
    det = " | ".join(r["detalle"] for r in errores(erc(dos), "referencias"))
    assert "es ambiguo" in det and "=Faja1-K1, =Faja2-K1" in det
    assert "-T1 está en +TAB1, no en +CAMPO" in det
    assert "=Faja2-K1:A2" not in det  # con su aspecto de función resuelve


def test_designacion_duplicada():
    m = arranque_directo()
    otro = disp("-Q3", "CONT-9A-220VAC")
    reglas = erc(_con(m, dispositivos=m.dispositivos + (otro,)))
    [e] = errores(reglas, "designación duplicada")
    assert "-Q3" in e["detalle"] and "CONT-9A-220VAC" in e["detalle"]


def test_cortocircuito_directo_entre_fases():
    m = arranque_directo()
    reglas = erc(_con(m, agregar=(w("-G1:L1", "-G1:L2", color="BK"),)))
    det = [r["detalle"] for r in errores(reglas, "cortocircuito")]
    assert any("-G1:L1 y -G1:L2" in d and "directo" in d for d in det), det


def test_cortocircuito_al_cerrar_un_pulsador():
    # un pulsador NA cableado de +24 a 0 V: al pulsarlo, la fuente queda en corto
    m = arranque_directo()
    extra = disp("-S9", "PULS-22-AZUL-NA")
    reglas = erc(_con(m, dispositivos=m.dispositivos + (extra,),
                      agregar=(w("-T1:L+", "-S9:13", color="BU"), w("-S9:14", "-T1:M", color="BU"))))
    det = [r["detalle"] for r in errores(reglas, "cortocircuito")]
    assert any("-T1:+" in d and "-T1:-" in d and "al cerrar -S9:13-14" in d for d in det), det


def test_conmutado_na_y_nc_del_mismo_rele_no_es_cortocircuito():
    # 12 (NC) a +24 y 14 (NA) a 0 V: el común nunca ve las dos a la vez (un actuador). El
    # piloto del común se apaga con el relé (0 V en ese estado): no es un cruce de tensión.
    m = arranque_directo()
    extra = (disp("-K5", "RELE-INT-24VDC"), disp("-P2", "PILOTO-24V-AMBAR"))
    agregar = (w("-T1:L+", "-K5:12", color="BU"), w("-K5:14", "-T1:M", color="BU"),
               w("-K5:11", "-P2:X1", color="BU"), w("-P2:X2", "-T1:M", color="BU"))
    reglas = erc(_con(m, dispositivos=m.dispositivos + extra, agregar=agregar))
    assert not errores(reglas, "cortocircuito")
    assert not errores(reglas, "tensión cruzada")


def test_carga_con_los_dos_bornes_al_mismo_potencial_nunca_recibe_tension():
    m = arranque_directo()
    i = _idx(m, "-P1:X2")
    reglas = erc(_con(m, cambiar={i: w("-P1:X2", "-Q3A:54", color="BU")}))
    [e] = errores(reglas, "tensión cruzada")
    assert "-P1 (PILOTO-24V-VERDE)" in e["detalle"] and "nunca recibe tensión" in e["detalle"]


def test_neutro_unido_al_pe_cita_iec_60204_5_1():
    red = disp("-G1", "RED-3F-380-220V-60HZ")
    pe = disp("-X0", "BORNE-PE-2.5")
    m = ModeloElectrico((red, pe), (w("-G1:PE", "-X0:1", color="GNYE"), w("-G1:N", "-X0:1", color="LBU")))
    [e] = errores(erc(m), "cortocircuito")
    assert "-G1:N" in e["detalle"] and "§5.1" in e["norma"]


def test_bobina_de_24vdc_colgada_de_220vac_es_tension_cruzada():
    # el caso del F4: la bobina de 24 VDC alimentada entre dos fases
    m = arranque_directo()
    i_a1, i_a2 = _idx(m, "-S2:14"), _idx(m, "-Q3:A2")
    reglas = erc(_con(m, cambiar={i_a1: w("-S2:14", "-Q3:14", color="BU"), i_a2: w("-Q3:A2", "-Q1:4", color="BK")},
                      agregar=(w("-Q1:2", "-Q3:A1", color="BK"),)))
    det = [r["detalle"] for r in errores(reglas, "tensión cruzada")]
    assert any("-Q3 (CONT-9A-24VDC)" in d and "220 VAC" in d and "24 VDC" in d for d in det), det


def test_sensor_pnp_alimentado_al_reves_es_polaridad_invertida():
    m = arranque_variador()
    cambios = {_idx(m, "-T1:L+", "-B1:BN"): w("-T1:M", "-B1:BN", cable="-W2", hilo="BN"),
               _idx(m, "-B1:BU"): w("-B1:BU", "-T1:L+", cable="-W2", hilo="BU")}
    det = [r["detalle"] for r in errores(erc(_con(m, cambiar=cambios)), "tensión cruzada")]
    assert any("-B1 (FOTO-M18)" in d and "polaridad invertida" in d for d in det), det


def test_motor_de_400v_en_red_de_220v():
    m = arranque_directo()
    dispositivos = tuple(disp("-M1", "MOTOR-150", ubicacion="+CAMPO") if d.designacion == "-M1" else d
                         for d in m.dispositivos)
    det = [r["detalle"] for r in errores(erc(_con(m, dispositivos=dispositivos)), "tensión cruzada")]
    assert any("-M1 (MOTOR-150)" in d and "220 VAC 3F" in d and "400 VAC 3F" in d for d in det), det


def test_motor_en_estrella_no_admite_la_red_de_220v():
    m = arranque_directo()
    dispositivos = tuple(disp("-M1", "MOTOR-075", ubicacion="+CAMPO", ajustes={"conexion": "estrella"})
                         if d.designacion == "-M1" else d for d in m.dispositivos)
    assert errores(erc(_con(m, dispositivos=dispositivos)), "tensión cruzada")


def test_motor_alimentado_por_itm_sin_proteccion_de_motor():
    # el error clásico: ITM + contactor, sin guardamotor ni relé térmico
    m = arranque_directo()
    dispositivos = tuple(disp("-Q2", "ITM-C6-3P") if d.designacion == "-Q2" else d for d in m.dispositivos)
    [e] = errores(erc(_con(m, dispositivos=dispositivos)), "protección del motor")
    assert "-M1 (MOTOR-075)" in e["detalle"] and "-Q2:1-2" in e["detalle"]
    assert "§7.3" in e["norma"]


def test_contactor_con_rele_termico_protege_al_motor():
    m = arranque_directo()
    dispositivos = tuple(disp("-Q2", "ITM-C6-3P") if d.designacion == "-Q2" else d for d in m.dispositivos)
    rt = disp("-F3", "RT-2.5-4A")
    cambios = {_idx(m, "-Q3:2"): w("-Q3:2", "-F3:1", color="BK"), _idx(m, "-Q3:4"): w("-Q3:4", "-F3:3", color="BK"),
               _idx(m, "-Q3:6"): w("-Q3:6", "-F3:5", color="BK")}
    agregar = (w("-F3:2", "-M1:U1", cable="-W1", hilo="1"), w("-F3:4", "-M1:V1", cable="-W1", hilo="2"),
               w("-F3:6", "-M1:W1", cable="-W1", hilo="3"))
    reglas = erc(_con(m, dispositivos=dispositivos + (rt,), cambiar=cambios, agregar=agregar))
    assert not errores(reglas, "protección del motor")


def test_puente_que_saltea_el_guardamotor():
    m = arranque_directo()
    reglas = erc(_con(m, agregar=(w("-Q1:2", "-Q3:1", color="BK"),)))
    [e] = errores(reglas, "protección del motor")
    assert "-M1" in e["detalle"]


def test_masa_sin_unir_a_la_red_pe():
    m = arranque_directo()
    reglas = erc(_con(m, quitar=(_idx(m, "-X0:1", "-U1:PE"),)))
    [e] = errores(reglas, "puesta a tierra")
    assert "-U1 (GAB-6040)" in e["detalle"] and "PE" in e["detalle"]
    assert "IEC 60364-4-41" in e["norma"] and "IEC 60364-5-54" in e["norma"]


def test_bobina_sin_a2_es_borne_suelto():
    m = arranque_directo()
    reglas = erc(_con(m, quitar=(_idx(m, "-Q3:A2"),)))
    [e] = errores(reglas, "borne suelto")
    assert "-Q3 (CONT-9A-24VDC)" in e["detalle"] and "A2" in e["detalle"]


def test_entrada_cableada_sin_su_comun_es_borne_suelto():
    m = arranque_variador()
    i_comun = _idx(m, "-T1:M", "-K1:M")
    reglas = erc(_con(m, cambiar={i_comun: w("-T1:M", "-K1:M", "-K1:3M", "-T2:COM", "-T2:SCM", color="BU")}))
    det = [r["detalle"] for r in errores(reglas, "borne suelto")]
    assert any("I0.0–1M" in d and "1M" in d for d in det), det


def test_entradas_libres_con_comun_cableado_no_son_sueltas():
    reglas = erc(arranque_variador())  # I0.5…I1.5 libres, 1M cableado
    assert not errores(reglas, "borne suelto")


@pytest.mark.parametrize("i_color,esperado", [
    (("-T1:L+", "-S0:11"), "RD"),  # mando DC en rojo
    (("-Q1:2", "-Q2:1"), "BU"),  # potencia en azul
    (("-X0:1", "-T1:PE"), "BK"),  # PE en negro
    (("-G1:L1", "-Q1:1"), "GNYE"),  # verde-amarillo en una fase
])
def test_color_que_contradice_iec_60204(i_color, esperado):
    m = arranque_directo()
    i = _idx(m, *i_color)
    viejo = m.conductores[i]
    reglas = erc(_con(m, cambiar={i: dataclasses.replace(viejo, color=esperado)}))
    [a] = avisos(reglas, "color del conductor")
    assert esperado in a["detalle"] and "§13.2" in a["norma"]
    assert not errores(reglas)


def test_hilo_de_cable_verde_amarillo_en_una_fase():
    m = arranque_directo()
    i = _idx(m, "-Q3:2", "-M1:U1")
    reglas = erc(_con(m, cambiar={i: w("-Q3:2", "-M1:U1", cable="-W1", hilo="PE")}))
    [a] = avisos(reglas, "color del conductor")
    assert "EXCLUSIVO" in a["detalle"]


def test_motores_sin_seta_dan_aviso():
    m = arranque_directo()
    dispositivos = tuple(d for d in m.dispositivos if d.designacion != "-S0")
    sin_seta = w("-T1:L+", "-S1:11", "-Q3A:53", color="BU", seccion=0.75)
    reglas = erc(_con(m, dispositivos=dispositivos, quitar=(_idx(m, "-S0:12"),),
                      cambiar={_idx(m, "-T1:L+", "-S0:11"): sin_seta}))
    [a] = avisos(reglas, "parada de emergencia")
    assert "ISO 13850" in a["norma"] and "-M1" in a["elementos"]
    assert resumen(reglas)["estado"] == "aviso"


def test_resumen_con_error():
    m = arranque_directo()
    reglas = erc(_con(m, quitar=(_idx(m, "-Q3:A2"),)))
    assert resumen(reglas) == {"estado": "error", "errores": 1, "avisos": 0}
