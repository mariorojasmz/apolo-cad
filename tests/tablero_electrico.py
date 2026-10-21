"""El tablero de arranque directo de `test_electrico_erc.py` como COMANDOS del carril (V8.1 F3).

Lo comparten los tests de los comandos, del `insert_project` y de los servicios eléctricos. Es
el mismo cableado que el ERC de F2 da verde, escrito como lo declararía el agente por
`run_batch`: red → seccionador → guardamotor → contactor → motor por el cable -W1, con mando de
24 VDC (fuente, seta, paro, marcha con enclavamiento, bobina) y piloto.
"""

from __future__ import annotations


def dev(ref: str, des: str = "", ubicacion: str = "+TAB1", **extra) -> dict:
    return {"type": "add_device", "params": {"ref": ref, "designacion": des,
                                             "ubicacion": ubicacion, **extra}}


def wire(*puntos: str, **extra) -> dict:
    return {"type": "add_wire", "params": {"puntos": list(puntos), **extra}}


def dispositivos_directo(pieza_motor: str | None = None) -> list[dict]:
    motor = {"ajustes": {"conexion": "triangulo"}}
    if pieza_motor:
        motor["pieza"] = pieza_motor
    return [
        dev("RED-3F-220V-60HZ", "-G1", "+RED"),
        dev("SECC-25A-3P", "-Q1"),
        dev("GM-2.5-4A", "-Q2", ajustes={"Ir_A": 3.2}),
        dev("CONT-9A-24VDC", "-Q3"),
        dev("CONT-AUX-1NA1NC", "-Q3A"),
        dev("MOTOR-075", "-M1", "+CAMPO", **motor),
        dev("ITM-C2-2P", "-F1"),
        dev("FUENTE-24VDC-2.5A", "-T1"),
        dev("ESTOP-40", "-S0"),
        dev("PULS-22-ROJO-NC", "-S1"),
        dev("PULS-22-VERDE-NA", "-S2"),
        dev("PILOTO-24V-VERDE", "-P1"),
        dev("BORNE-PE-4", "-X0", cantidad=2),
        dev("GAB-6040", "-U1"),
    ]


def conductores_directo(seccion_mando="0.75", largo: float | None = 1.0) -> list[dict]:
    """`seccion_mando` acepta «=expr»; `largo` = largo_m de cada conductor suelto (None = sin
    declarar)."""
    pot = {"color": "BK", "tipo": "COND-H07VK-2.5"}
    mando = {"color": "BU", "seccion_mm2": seccion_mando}
    if largo is not None:
        pot["largo_m"] = largo
        mando["largo_m"] = largo
    pe = {"color": "GNYE"}
    return [
        wire("-G1:L1", "-Q1:1", **pot), wire("-G1:L2", "-Q1:3", **pot),
        wire("-G1:L3", "-Q1:5", **pot),
        wire("-Q1:2", "-Q2:1", **pot), wire("-Q1:4", "-Q2:3", **pot), wire("-Q1:6", "-Q2:5", **pot),
        wire("-Q2:2", "-Q3:1", **pot), wire("-Q2:4", "-Q3:3", **pot), wire("-Q2:6", "-Q3:5", **pot),
        wire("-Q3:2", "-M1:U1", cable="-W1", hilo="1"),
        wire("-Q3:4", "-M1:V1", cable="-W1", hilo="2"),
        wire("-Q3:6", "-M1:W1", cable="-W1", hilo="3"),
        wire("-X0:2", "-M1:PE", cable="-W1", hilo="PE"),
        wire("-G1:PE", "-X0:1", seccion_mm2=4, **pe), wire("-X0:1", "-X0:2", **pe),
        wire("-X0:1", "-T1:PE", **pe), wire("-X0:1", "-U1:PE", **pe),
        wire("-Q1:2", "-F1:1", **pot), wire("-Q1:4", "-F1:3", **pot),
        wire("-F1:2", "-T1:L", color="BK"), wire("-F1:4", "-T1:N", color="BK"),
        wire("-T1:M", "-X0:1", **pe),
        wire("-T1:L+", "-S0:11", "-Q3A:53", **mando),
        wire("-S0:12", "-S1:11", **mando),
        wire("-S1:12", "-S2:13", "-Q3:13", **mando),
        wire("-S2:14", "-Q3:14", "-Q3:A1", **mando),
        wire("-Q3:A2", "-T1:M", **mando),
        wire("-Q3A:54", "-P1:X1", **mando),
        wire("-P1:X2", "-T1:M", **mando),
    ]


def arranque_directo(pieza_motor: str | None = None, largo_cable: float | None = 6.0,
                     **kw) -> list[dict]:
    cable = {"type": "add_cable", "params": {"designacion": "-W1", "ref": "CABLE-4G1.5",
                                             "desde": "+TAB1", "hasta": "-M1"}}
    if largo_cable is not None:
        cable["params"]["largo_m"] = largo_cable
    return dispositivos_directo(pieza_motor) + [cable] + conductores_directo(**kw)


def arranque_variador_plc(pieza_motor: str | None = None, *, ajustes_motor: dict | None = None,
                          ajustes_variador: dict | None = None) -> list[dict]:
    """El tablero (b) del ERC (`test_electrico_erc.arranque_variador`) como comandos: red →
    seccionador → ITM → VFD-2K2-220 → NMRV-090 por el cable -W1; PLC -K1 con la fotocelda en
    I0.0, la seta en I0.1 (y en el STO del variador), la botonera marcha/paro en I0.2/I0.3, el
    relé de falla en I0.4, la marcha del variador por Q0.0 y el piloto por Q0.1; el potenciómetro
    de la botonera a la AI1 del variador (V8.3 F4)."""
    motor = {"ajustes": {"conexion": "triangulo", "i": 30, "eta_reductor": 0.75, **(ajustes_motor or {})}}
    if pieza_motor:
        motor["pieza"] = pieza_motor
    vfd = {"ajustes": ajustes_variador} if ajustes_variador else {}
    pot = {"color": "BK", "seccion_mm2": 2.5}
    bu = {"color": "BU", "seccion_mm2": 0.75}
    pe = {"color": "GNYE"}
    return [
        dev("RED-3F-220V-60HZ", "-G1", "+RED"), dev("SECC-25A-3P", "-Q1"), dev("ITM-C16-3P", "-F1"),
        dev("VFD-2K2-220", "-T2", **vfd), dev("NMRV-090", "-M1", "+CAMPO", **motor),
        dev("ITM-C2-2P", "-F2"), dev("FUENTE-24VDC-5A", "-T1"), dev("PLC-14DI-10DO-24VDC", "-K1"),
        dev("ESTOP-40", "-S0"), dev("BOTONERA-2", "-S1", "+CAMPO"), dev("FOTO-M18", "-B1", "+CAMPO"),
        dev("PILOTO-24V-VERDE", "-P1"), dev("BORNE-PE-4", "-X0"), dev("GAB-8060", "-U1"),
        {"type": "add_cable", "params": {"designacion": "-W1", "ref": "CABLE-4G1.5", "desde": "+TAB1",
                                         "hasta": "-M1"}},
        {"type": "add_cable", "params": {"designacion": "-W2", "ref": "CABLE-3X0.75", "desde": "+TAB1",
                                         "hasta": "-B1"}},
        wire("-G1:L1", "-Q1:1", **pot), wire("-G1:L2", "-Q1:3", **pot), wire("-G1:L3", "-Q1:5", **pot),
        wire("-Q1:2", "-F1:1", **pot), wire("-Q1:4", "-F1:3", **pot), wire("-Q1:6", "-F1:5", **pot),
        wire("-F1:2", "-T2:L1", **pot), wire("-F1:4", "-T2:L2", **pot), wire("-F1:6", "-T2:L3", **pot),
        wire("-T2:U", "-M1:U1", cable="-W1", hilo="1"), wire("-T2:V", "-M1:V1", cable="-W1", hilo="2"),
        wire("-T2:W", "-M1:W1", cable="-W1", hilo="3"), wire("-T2:PE", "-M1:PE", cable="-W1", hilo="PE"),
        wire("-G1:PE", "-X0:1", seccion_mm2=4, **pe),
        wire("-X0:1", "-T2:PE", "-T1:PE", "-K1:PE", "-U1:PE", **pe),
        wire("-Q1:2", "-F2:1", **pot), wire("-Q1:4", "-F2:3", **pot),
        wire("-F2:2", "-T1:L", color="BK"), wire("-F2:4", "-T1:N", color="BK"),
        wire("-T1:M", "-X0:1", **pe),
        wire("-T1:L+", "-K1:L+", "-K1:3L+", **bu),
        wire("-T1:M", "-K1:M", "-K1:3M", "-K1:1M", "-T2:COM", "-T2:SCM", **bu),
        wire("-K1:Q0.0", "-T2:DI1", **bu),
        wire("-K1:Q0.1", "-P1:X1", **bu), wire("-P1:X2", "-T1:M", **bu),
        wire("-T1:L+", "-S0:11", **bu),
        wire("-S0:12", "-T2:S1", "-T2:S2", "-K1:I0.1", **bu),
        wire("-T1:L+", "-S1:13", "-S1:21", **bu),
        wire("-S1:14", "-K1:I0.2", **bu), wire("-S1:22", "-K1:I0.3", **bu),
        # el potenciómetro con P3 a +10 V: «girar» a 1 (cursor del lado de P3) = 10 V = f máxima
        wire("-T2:+10V", "-S1:P3", **bu), wire("-T2:GND", "-S1:P1", **bu), wire("-S1:P2", "-T2:AI1", **bu),
        wire("-T1:L+", "-T2:RC", **bu), wire("-T2:RA", "-K1:I0.4", **bu),
        wire("-T1:L+", "-B1:BN", cable="-W2", hilo="BN"), wire("-B1:BU", "-T1:M", cable="-W2", hilo="BU"),
        wire("-B1:BK", "-K1:I0.0", cable="-W2", hilo="BK"),
    ]


def no_ok(reglas: list[dict]) -> list[str]:
    return [f"{r['regla']}: {r['detalle']}" for r in reglas if r["estado"] != "ok"]
