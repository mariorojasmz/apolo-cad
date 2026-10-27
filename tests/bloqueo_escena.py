"""Banco del bloqueo de vástago en la co-simulación (plan bloqueo-de-vastago F1).

`desviador(bloqueo)`: un Ø63 × 400 de `create_pneumatic_cylinder` (vástago Ø20) con una placa de
empujador pesada, sobre una base anclada por sus pies; una 5/3 de centro a ESCAPE (-QM2) con
reguladores de caudal por el escape en las dos cámaras, el de la A más cerrado que el de la B
(-RZ1 C 0,15 contra -RZ2 C 0,6): el caso de la faja con desviador, donde al pulsar la seta a media
carrera la A escapa más lento y el aire que queda empuja el vástago hasta el tope.

El mando, de 24 VDC: la seta -S0 (NC 11-12) alimenta los pulsadores de avance -S2 (bobina 14 de
-QM2) y de retroceso -S3 (bobina 12) y, con `bloqueo`, la bobina de la 3/2 NC -QM3 que libera el
bloqueo -RL1 (`ref`): su vía 2 al puerto 1 del bloqueo, su vía 1 aguas abajo del corte con escape.
`mando` dice de dónde le llega la tensión a esa bobina: «seta» (del NC de la seta), «rele» (del NA
de un relé -K1 cuya bobina alimenta la seta) o «directo» (de la fuente, sin pasar por la seta: el
ERC lo avisa). Con `sin_valvula` el bloqueo se libera directo de la línea del corte (sin 3/2).

`escenario(cid, seta_s=…)`: -S3 llena la cámara B (de 0,05 a 0,3 s: la 5/3 arranca al centro, con
las dos cámaras vacías), -S2 avanza desde `AVANCE_S` y la seta se presiona a `seta_s`.
"""

from __future__ import annotations

from neumatica_escena import dev, tubo, wire

from apolo.doc.document import Document

CARRERA = 400
C_A, C_B = 0.15, 0.6     # C regulado del escape de la A (-RZ1) y de la B (-RZ2), dm³/(s·bar)


def desviador(bloqueo: bool = True, ref: str = "BLOQ-VAST-20-S", *, mando: str = "seta",
              presion_frl: float = 6.0, declarar: bool = True, sin_valvula: bool = False,
              cilindro: str = "CIL-ISO15552-63") -> tuple[Document, str]:
    d = Document("desviador-bloqueo")
    cid = d.execute("create_pneumatic_cylinder", {
        "ref": cilindro, "carrera": CARRERA, "montaje": "pies", "eje": "+X", "puertos": "+Z",
        "empujador": {"ancho": 250, "alto": 150, "espesor": 40}})
    bb = d.scene[f"{cid}_cuerpo"].shape.bounding_box()
    base = d.execute("create_box", {"name": "Base del cilindro", "width": bb.max.X - bb.min.X + 60, "depth": 300,
                                    "height": 20, "position": {"x": (bb.min.X + bb.max.X) / 2, "y": 0,
                                                               "z": bb.min.Z - 10.0}})
    for pie in ("delantero", "trasero"):
        d.execute("fasten", {"name": f"pie_{pie}", "a": f"{cid}_pie_{pie}", "b": base, "kind": "perno",
                             "size": "M8", "qty": 2})
    d.execute("ground", {"name": "piso", "feature": base})
    servicio = {"carrera_mm": CARRERA, **({"bloqueo": "-RL1"} if bloqueo and declarar else {})}
    cmds = [
        dev("FR-G14", "-AZ1", ajustes={"p_regulada_bar": presion_frl}),
        dev("CORTE-ESC-G14", "-QM1"),
        dev("VAL-53-CE-G14", "-QM2"),
        dev(cilindro, "-MM1", pieza=f"{cid}_cuerpo", servicio=servicio),
        dev("REG-CAUDAL-L-8", "-RZ1", ajustes={"C_regulado": C_A}),
        dev("REG-CAUDAL-L-8", "-RZ2", ajustes={"C_regulado": C_B}),
        tubo("-AZ1:2", "-QM1:1", "TUBO-PU-10", largo_m=0.5),
        tubo("-QM1:2", "-QM2:1", "TUBO-PU-10", largo_m=1.0),
        tubo("-QM2:4", "-RZ1:1", "TUBO-PU-8", largo_m=1.0),
        tubo("-RZ1:2", "-MM1:A", "TUBO-PU-8", largo_m=0.3),
        tubo("-QM2:2", "-RZ2:1", "TUBO-PU-8", largo_m=1.0),
        tubo("-RZ2:2", "-MM1:B", "TUBO-PU-8", largo_m=0.3),
        dev("RED-3F-220V-60HZ", "-G1", ubicacion="+RED"),
        dev("ITM-C2-2P", "-F1", ubicacion="+TAB1"),
        dev("FUENTE-24VDC-2.5A", "-T1", ubicacion="+TAB1"),
        dev("ESTOP-40", "-S0", ubicacion="+TAB1"),
        dev("PULS-22-VERDE-NA", "-S2", ubicacion="+TAB1"),
        dev("PULS-22-VERDE-NA", "-S3", ubicacion="+TAB1"),
        dev("BORNE-PE-4", "-X0", ubicacion="+TAB1", cantidad=2),
        wire("-G1:L1", "-F1:1"), wire("-G1:L2", "-F1:3"),
        wire("-F1:2", "-T1:L"), wire("-F1:4", "-T1:N"),
        wire("-G1:PE", "-X0:1"), wire("-X0:1", "-T1:PE"), wire("-T1:M", "-X0:1"),
        wire("-T1:L+", "-S0:11"), wire("-S0:12", "-S2:13", "-S3:13"),
        wire("-S2:14", "-QM2:14A1"), wire("-QM2:14A2", "-T1:M"),
        wire("-S3:14", "-QM2:12A1"), wire("-QM2:12A2", "-T1:M"),
    ]
    if bloqueo and sin_valvula:
        cmds += [dev(ref, "-RL1"), tubo("-QM1:2", "-RL1:1", "TUBO-PU-6", largo_m=1.0)]
    elif bloqueo:
        cmds += [
            dev(ref, "-RL1"),
            dev("VAL-32-NC-G18", "-QM3"),
            tubo("-QM1:2", "-QM3:1", "TUBO-PU-6", largo_m=1.0),
            tubo("-QM3:2", "-RL1:1", "TUBO-PU-6", largo_m=0.5),
            wire("-QM3:A2", "-T1:M"),
        ]
        if mando == "rele":
            cmds += [dev("RELE-INT-24VDC", "-K1", ubicacion="+TAB1"), wire("-S0:12", "-K1:A1"),
                     wire("-K1:A2", "-T1:M"), wire("-T1:L+", "-K1:11"), wire("-K1:14", "-QM3:A1")]
        else:
            cmds.append(wire("-S0:12" if mando == "seta" else "-T1:L+", "-QM3:A1"))
    d.execute_many(cmds)
    return d, cid


AVANCE_S = 0.4


def escenario(cid: str, duracion: float = 2.5, *, seta_s: float | None = 0.8, presion: float = 6.0,
              **extra) -> dict:
    acc = [{"t": 0.05, "accion": "pulsar", "dispositivo": "-S3", "durante_s": 0.25},
           {"t": AVANCE_S, "accion": "pulsar", "dispositivo": "-S2", "durante_s": duracion}]
    if seta_s is not None:
        acc.append({"t": seta_s, "accion": "presionar", "dispositivo": "-S0"})
    return {"duracion_s": duracion, "condiciones": {"presion_red_bar": presion},
            "acoples": {"cilindros": {"-MM1": {"junta": f"{cid}_vastago"}}}, "acciones": acc, **extra}
