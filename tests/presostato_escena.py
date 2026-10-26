"""Banco del presostato en la co-simulación (plan V8.9 F8).

`empujador_con_presostato(linea)`: el empujador de `neumatica_escena.py` (un Ø32 de
`create_pneumatic_cylinder` con su circuito de aire) mandado por un PLC: la marcha -S2 en I0.2,
la bobina de la 5/2 -QM2 en Q0.0 y el presostato -BP1 (PRESOSTATO-1-10BAR, conmuta a 4 bar) en
I0.0, alimentado desde los 24 V por su común 11 y leído por su NA 14. `linea` dice qué vigila
(`LINEAS`): «alimentacion» (en T con la vía 1 de la válvula, aguas abajo del corte con escape: «hay
aire en la máquina»), «toma» (la entrada del FRL) o la cámara «A» o «B» del cilindro. El programa (`PROGRAMA`) arranca con la
marcha si hay aire; en marcha, si el presostato abre, para (suelta la válvula) y enclava
`falla_aire` (no se re-arranca sin aire).
"""

from __future__ import annotations

from neumatica_escena import CARRERA, dev, tubo, wire

from apolo.doc.document import Document

PROGRAMA = """
VAR_GLOBAL
  aire_ok AT %IX0.0 : BOOL;   (* NA del presostato -BP1: TRUE = hay aire *)
  marcha AT %IX0.2 : BOOL;
  empujar AT %QX0.0 : BOOL;   (* bobina 14 de -QM2 *)
END_VAR
PROGRAM Main
VAR
  en_marcha : BOOL;
  falla_aire : BOOL;
END_VAR
IF en_marcha AND NOT aire_ok THEN   (* en marcha y se fue el aire: para y lo enclava *)
  falla_aire := TRUE;
  en_marcha := FALSE;
END_IF;
IF marcha AND aire_ok AND NOT falla_aire THEN
  en_marcha := TRUE;
END_IF;
empujar := en_marcha;
END_PROGRAM
"""

P_CONMUTA = 4.0
#: dónde se pone el presostato: el puerto con el que comparte línea
LINEAS = {"alimentacion": "-QM2:1", "toma": "-AZ1:1", "A": "-MM1:A", "B": "-MM1:B"}


def empujador_con_presostato(linea: str = "alimentacion", p_conmuta: float | None = P_CONMUTA,
                             cableado: bool = True) -> tuple[Document, str]:
    d = Document("empujador-presostato")
    cid = d.execute("create_pneumatic_cylinder", {
        "ref": "CIL-ISO15552-32", "carrera": CARRERA, "montaje": "pies", "eje": "+X", "puertos": "+Z",
        "empujador": {"ancho": 120, "alto": 70, "espesor": 8}})
    base = d.execute("create_box", {"name": "Base del cilindro", "width": 170 + CARRERA, "depth": 300,
                                    "height": 20, "position": {"x": -(65 + CARRERA) / 2 - 20, "y": 0, "z": -42}})
    d.execute("fasten", {"name": "pies_base", "a": f"{cid}_pie_delantero", "b": base, "kind": "perno",
                         "size": "M6", "qty": 2})
    d.execute("fasten", {"name": "pies_base2", "a": f"{cid}_pie_trasero", "b": base, "kind": "perno",
                         "size": "M6", "qty": 2})
    d.execute("ground", {"name": "piso", "feature": base})
    en = LINEAS[linea]
    aj = {"ajustes": {"p_conmuta_bar": p_conmuta}} if p_conmuta is not None else {}
    cmds = [
        dev("FR-G14", ajustes={"p_regulada_bar": 6}),
        dev("CORTE-ESC-G14"),
        dev("VAL-52-MONO-G18"),
        dev("CIL-ISO15552-32", pieza=f"{cid}_cuerpo"),
        dev("PRESOSTATO-1-10BAR", "-BP1", **aj),
        tubo("-AZ1:2", "-QM1:1", "TUBO-PU-8", largo_m=0.5),
        tubo("-QM1:2", "-QM2:1", "TUBO-PU-8", largo_m=1.0),
        tubo("-QM2:4", "-MM1:A", largo_m=1.0),
        tubo("-QM2:2", "-MM1:B", largo_m=1.0),
        tubo(en, "-BP1:1", "TUBO-PU-4", largo_m=0.3),
        dev("RED-3F-220V-60HZ", "-G1", ubicacion="+RED"),
        dev("ITM-C2-2P", "-F1", ubicacion="+TAB1"),
        dev("FUENTE-24VDC-2.5A", "-T1", ubicacion="+TAB1"),
        dev("PLC-14DI-10DO-24VDC", "-K1", ubicacion="+TAB1"),
        dev("PULS-22-VERDE-NA", "-S2", ubicacion="+TAB1"),
        dev("BORNE-PE-4", "-X0", ubicacion="+TAB1", cantidad=2),
        wire("-G1:L1", "-F1:1"), wire("-G1:L2", "-F1:3"),
        wire("-F1:2", "-T1:L"), wire("-F1:4", "-T1:N"),
        wire("-G1:PE", "-X0:1"), wire("-X0:1", "-T1:PE"), wire("-X0:1", "-K1:PE"), wire("-T1:M", "-X0:1"),
        wire("-T1:L+", "-K1:L+", "-K1:3L+"), wire("-T1:M", "-K1:M", "-K1:3M", "-K1:1M"),
        wire("-T1:L+", "-S2:13"), wire("-S2:14", "-K1:I0.2"),
        wire("-K1:Q0.0", "-QM2:A1"), wire("-QM2:A2", "-T1:M"),
    ]
    if cableado:
        cmds += [wire("-T1:L+", "-BP1:11"), wire("-BP1:14", "-K1:I0.0")]
    d.execute_many(cmds)
    d.execute("add_program", {"plc": "-K1", "nombre": "Main", "fuente": PROGRAMA, "ciclo_ms": 10})
    return d, cid


def escenario(cid: str, duracion: float = 1.6, *, corte_s: float | None = 1.0, presion: float = 6.0,
              **extra) -> dict:
    """Marcha por -S2 a 0,2 s; el corte de aire a `corte_s`."""
    ev = [{"t": corte_s, "tipo": "corte_de_aire"}] if corte_s is not None else []
    return {"duracion_s": duracion, "condiciones": {"presion_red_bar": presion},
            "acoples": {"cilindros": {"-MM1": {"junta": f"{cid}_vastago"}}},
            "acciones": [{"t": 0.2, "accion": "pulsar", "dispositivo": "-S2", "durante_s": 0.2}],
            "eventos": ev, **extra}
