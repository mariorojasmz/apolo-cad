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


def no_ok(reglas: list[dict]) -> list[str]:
    return [f"{r['regla']}: {r['detalle']}" for r in reglas if r["estado"] != "ok"]
