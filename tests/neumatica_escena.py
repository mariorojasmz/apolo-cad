"""Banco de la co-simulación del aire en una escena física (plan V8.9 F3).

`empujador(valvula)`: un cilindro ISO 15552 Ø32 de `create_pneumatic_cylinder` sobre una base
anclada (por sus pies), con su empujador frente a una caja que descansa en una mesa; el circuito
de aire del carril (FRL → corte con escape → válvula → cilindro, como en `test_neumatica_carril`)
y las bobinas de la válvula mandadas por dos pulsadores (-S2 → bobina 14, -S3 → bobina 12) desde
una fuente de 24 VDC; un detector inductivo -B1 alimentado (para el acople a la junta, D8).
`escenario(cid, …)` lo prueba: -S2 se mantiene `pulsar_s` desde t = 0,2 s.
"""

from __future__ import annotations

from apolo.doc.document import Document

CARRERA = 200
CAJA_X = 125.0          # centro de la caja (mm): frente a la placa del empujador retraído


def dev(ref: str, des: str = "", **p) -> dict:
    return {"type": "add_device", "params": {"ref": ref, **({"designacion": des} if des else {}), **p}}


def tubo(desde: str, hasta: str, ref: str = "TUBO-PU-6", **p) -> dict:
    return {"type": "add_tubo", "params": {"desde": desde, "hasta": hasta, "ref": ref, **p}}


def wire(*puntos: str, **p) -> dict:
    return {"type": "add_wire", "params": {"puntos": list(puntos), **p}}


def empujador(valvula: str = "VAL-52-MONO-G18", carrera: int = CARRERA):
    """(documento, cid del cilindro)."""
    d = Document("empujador")
    cid = d.execute("create_pneumatic_cylinder", {
        "ref": "CIL-ISO15552-32", "carrera": carrera, "montaje": "pies", "eje": "+X", "puertos": "+Z",
        "empujador": {"ancho": 120, "alto": 70, "espesor": 8}})
    base = d.execute("create_box", {"name": "Base del cilindro", "width": 170 + carrera, "depth": 300,
                                    "height": 20, "position": {"x": -(65 + carrera) / 2 - 20, "y": 0, "z": -42}})
    d.execute("fasten", {"name": "pies_base", "a": f"{cid}_pie_delantero", "b": base, "kind": "perno",
                         "size": "M6", "qty": 2})
    d.execute("fasten", {"name": "pies_base2", "a": f"{cid}_pie_trasero", "b": base, "kind": "perno",
                         "size": "M6", "qty": 2})
    d.execute("ground", {"name": "piso", "feature": base})
    mesa = d.execute("create_box", {"name": "Mesa", "width": 700, "depth": 400, "height": 20,
                                    "position": {"x": 390, "y": 0, "z": -50}})
    d.execute("ground", {"name": "piso_mesa", "feature": mesa})
    dos = not valvula.startswith(("VAL-52-MONO", "VAL-32"))
    a14 = "14A" if dos else "A"
    d.execute_many([
        dev("FR-G14", ajustes={"p_regulada_bar": 6}),
        dev("CORTE-ESC-G14"),
        dev(valvula),
        dev("CIL-ISO15552-32", pieza=f"{cid}_cuerpo"),
        tubo("-AZ1:2", "-QM1:1", "TUBO-PU-8", largo_m=0.5),
        tubo("-QM1:2", "-QM2:1", "TUBO-PU-8", largo_m=1.0),
        tubo("-QM2:4", "-MM1:A", largo_m=1.0),
        tubo("-QM2:2", "-MM1:B", largo_m=1.0),
        dev("RED-3F-220V-60HZ", "-G1", ubicacion="+RED"),
        dev("ITM-C2-2P", "-F1", ubicacion="+TAB1"),
        dev("FUENTE-24VDC-2.5A", "-T1", ubicacion="+TAB1"),
        dev("PULS-22-VERDE-NA", "-S2", ubicacion="+TAB1"),
        dev("PULS-22-VERDE-NA", "-S3", ubicacion="+TAB1"),
        dev("SENS-IND-M18-PNP", "-B1", ubicacion="+CAMPO"),
        dev("BORNE-PE-4", "-X0", ubicacion="+TAB1", cantidad=2),
        wire("-G1:L1", "-F1:1"), wire("-G1:L2", "-F1:3"),
        wire("-F1:2", "-T1:L"), wire("-F1:4", "-T1:N"),
        wire("-G1:PE", "-X0:1"), wire("-X0:1", "-T1:PE"), wire("-T1:M", "-X0:1"),
        wire("-T1:L+", "-S2:13", "-S3:13", "-B1:BN"), wire("-B1:BU", "-T1:M"),
        wire("-S2:14", f"-QM2:{a14}1"), wire(f"-QM2:{a14}2", "-T1:M"),
    ])
    if dos:
        d.execute_many([wire("-S3:14", "-QM2:12A1"), wire("-QM2:12A2", "-T1:M")])
    return d, cid


def escenario(cid: str, duracion: float = 2.0, *, pulsar_s: float = 1.0, acciones=(), eventos=(),
              caja: bool = True, presion: float = 6.0, sensores: dict | None = None, **extra) -> dict:
    ev = list(eventos)
    if caja:
        ev.append({"t": 0.0, "tipo": "producto", "nombre": "caja", "dims_mm": [100, 100, 100], "masa_kg": 2.0,
                   "posicion_mm": [CAJA_X, 0, 10.5]})
    acc = [{"t": 0.2, "accion": "pulsar", "dispositivo": "-S2", "durante_s": pulsar_s}] if pulsar_s else []
    acoples = {"cilindros": {"-MM1": {"junta": f"{cid}_vastago"}},
               **({"sensores": sensores} if sensores else {})}
    condiciones = {} if presion is None else {"presion_red_bar": presion}
    return {"duracion_s": duracion, "condiciones": condiciones, "acoples": acoples,
            "acciones": acc + list(acciones), "eventos": ev, **extra}
