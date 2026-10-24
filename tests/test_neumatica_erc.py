"""ERC neumático sobre circuitos SINTÉTICOS (plan V8.9 D9, F1b): un caso verde y uno rojo por regla.

El circuito verde es el mínimo que un integrador arma: unidad de mantenimiento (FRL a 6 bar) →
válvula de corte con escape → electroválvula 5/2 → cilindro ISO 15552 Ø32 con su servicio
(200 mm, 0,5 m/s, 2 kg). Cada caso rojo es UNA mutación de ese circuito. Los modelos se arman
con las dataclasses del carril (`library/electrico/modelo.py`), sin documento.
"""

from __future__ import annotations

import pytest

from apolo.library.catalog import CATALOG
from apolo.library.electrico.modelo import Dispositivo, ModeloElectrico, Tubo
from apolo.library.neumatica import calculo as K
from apolo.library.neumatica.erc import erc, hay_aire
from apolo.library.neumatica.lineas import analizar

SERVICIO = {"carrera_mm": 200.0, "velocidad_m_s": 0.5, "masa_kg": 2.0}


def disp(des: str, ref: str, ajustes: dict | None = None, servicio: dict | None = None) -> Dispositivo:
    f = CATALOG[ref].neumatico
    ele = CATALOG[ref].electrico
    return Dispositivo(designacion=des, ref=ref, funcion=f.funcion, bornes=ele.bornes if ele else (),
                       cargas=ele.cargas if ele else (), puertos=f.puertos, neumatico=f,
                       ajustes=dict(ajustes or {}), servicio=dict(servicio or {}))


def tubo(a: str, b: str, ref: str = "TUBO-PU-6", largo: float | None = 1.0) -> Tubo:
    t = CATALOG[ref].neumatico.tubo
    return Tubo(a, b, ref, D_ext_mm=t.D_ext_mm, D_int_mm=t.D_int_mm, largo_m=largo, p_max_bar=t.p_max_bar)


def verde(**cambios):
    """(dispositivos, tubos) del circuito verde; `cambios` reemplaza dispositivos por designación
    (None lo quita) o, con `tubos=`, la lista de tubos."""
    ds = {
        "-AZ1": disp("-AZ1", "FR-G14", {"p_regulada_bar": 6}),
        "-QM1": disp("-QM1", "CORTE-ESC-G14"),
        "-QM2": disp("-QM2", "VAL-52-MONO-G18"),
        "-MM1": disp("-MM1", "CIL-ISO15552-32", servicio=SERVICIO),
    }
    ts = [tubo("-AZ1:2", "-QM1:1", "TUBO-PU-8"), tubo("-QM1:2", "-QM2:1", "TUBO-PU-8"),
          tubo("-QM2:4", "-MM1:A"), tubo("-QM2:2", "-MM1:B")]
    ts = cambios.pop("tubos", ts)
    for k, v in cambios.items():
        if v is None:
            ds.pop(k.replace("_", "-"), None)
        else:
            ds[v.designacion] = v
    return ModeloElectrico(tuple(ds.values()), tubos=tuple(ts))


def por_regla(reglas, nombre):
    return [r for r in reglas if r["regla"] == nombre]


def malas(reglas, nombre):
    return [r for r in por_regla(reglas, nombre) if r["estado"] != "ok"]


# ── el verde ─────────────────────────────────────────────────────────────────────────────


def test_el_circuito_verde_pasa_todas_las_reglas():
    reglas = erc(verde())
    assert [r["regla"] for r in reglas] == [
        "aislamiento del aire", "tubo sin puerto", "puerto libre", "presión de trabajo",
        "servicio del cilindro", "caudal de la válvula", "pandeo del vástago", "energía al fin de carrera"]
    assert all(r["estado"] == "ok" for r in reglas), [r["detalle"] for r in reglas if r["estado"] != "ok"]
    assert all(r["medio"] == "aire" and r["norma"] for r in reglas)


def test_sin_aire_no_hay_reglas():
    assert not hay_aire(ModeloElectrico()) and erc(ModeloElectrico()) == []


def test_las_lineas_y_la_presion_de_cada_una():
    c = analizar(verde())
    # el cilindro recibe los 6 bar del FRL por la válvula (peor caso: todas las posiciones)
    assert c.presion_de(c.dispositivos["-MM1"]) == (6.0, 6.0, ["-AZ1"])
    assert c.linea("-QM2", "4") == c.linea("-MM1", "A") != c.linea("-MM1", "B")
    assert ("-QM2", "3") not in c.conectados  # el escape queda libre: a la atmósfera


# ── aislamiento del aire (ISO 4414) ──────────────────────────────────────────────────────


def test_sin_valvula_de_corte_con_escape_es_rojo():
    m = verde(_QM1=None, tubos=[tubo("-AZ1:2", "-QM2:1"), tubo("-QM2:4", "-MM1:A"), tubo("-QM2:2", "-MM1:B")])
    (r,) = malas(erc(m), "aislamiento del aire")
    assert r["estado"] == "error" and "ISO 4414" in r["norma"] and "CORTE-ESC" in r["recomendacion"]


def test_una_valvula_fuera_del_corte_es_roja():
    m = verde(_QM3=disp("-QM3", "VAL-52-MONO-G18"),
              tubos=[tubo("-AZ1:2", "-QM1:1"), tubo("-QM1:2", "-QM2:1"), tubo("-AZ1:2", "-QM3:1"),
                     tubo("-QM2:4", "-MM1:A"), tubo("-QM2:2", "-MM1:B")])
    rojas = malas(erc(m), "aislamiento del aire")
    assert [r["elementos"] for r in rojas] == [["-QM3"]]


def test_el_corte_aguas_arriba_del_frl_es_rojo():
    m = verde(tubos=[tubo("-QM1:2", "-AZ1:1"), tubo("-AZ1:2", "-QM2:1"), tubo("-QM2:4", "-MM1:A"),
                     tubo("-QM2:2", "-MM1:B")])
    rojas = malas(erc(m), "aislamiento del aire")
    assert any("aguas abajo de la unidad de mantenimiento" in r["detalle"] for r in rojas)


# ── tubo sin puerto / medio distinto ─────────────────────────────────────────────────────


def test_un_tubo_a_un_borne_o_a_nada_es_rojo():
    m = verde(tubos=list(verde().tubos) + [tubo("-QM2:A1", "-MM1:A"), tubo("-QM9:1", "-MM1:B")])
    rojas = malas(erc(m), "tubo sin puerto")
    assert len(rojas) == 2
    assert "borne eléctrico" in rojas[0]["detalle"] and "medio distinto" in rojas[0]["detalle"]
    assert "-QM9 no existe" in rojas[1]["detalle"]


# ── puerto libre ─────────────────────────────────────────────────────────────────────────


def test_un_puerto_de_trabajo_sin_tubo_es_rojo():
    m = verde(tubos=list(verde().tubos)[:-1])  # sin el tubo -QM2:2 → -MM1:B
    rojas = malas(erc(m), "puerto libre")
    assert sorted(r["elementos"][0] for r in rojas) == ["-MM1:B", "-QM2:2"]
    assert all(r["estado"] == "error" for r in rojas)


# ── presión de trabajo ───────────────────────────────────────────────────────────────────


def test_la_presion_sobre_la_maxima_de_la_valvula_es_roja():
    m = verde(_AZ1=disp("-AZ1", "FR-G14", {"p_regulada_bar": 8.5}))  # la válvula admite 8
    rojas = malas(erc(m), "presión de trabajo")
    assert {r["estado"] for r in rojas} == {"error"}
    assert [r["elementos"][0] for r in rojas if "recibe" in r["detalle"]] == ["-QM2"]  # el corte y el cilindro, a 10
    assert sum("el tubo" in r["detalle"] for r in rojas) == 4  # el PU, a 8 bar


def test_la_presion_bajo_la_minima_de_pilotaje_es_roja():
    m = verde(_AZ1=disp("-AZ1", "FR-G14", {"p_regulada_bar": 1.0}))  # la G1/8 pilota desde 2,5
    rojas = malas(erc(m), "presión de trabajo")
    assert [r["elementos"][0] for r in rojas] == ["-QM2"] and "2.5–8" in rojas[0]["detalle"]


def test_sin_presion_declarada_avisa():
    m = verde(_AZ1=disp("-AZ1", "FR-G14"))
    avisos = malas(erc(m), "presión de trabajo")
    assert {r["estado"] for r in avisos} == {"aviso"} and "p_regulada_bar" in avisos[0]["recomendacion"]


# ── servicio, caudal, pandeo e impacto ───────────────────────────────────────────────────


def test_un_cilindro_sin_servicio_avisa():
    (r,) = malas(erc(verde(_MM1=disp("-MM1", "CIL-ISO15552-32"))), "servicio del cilindro")
    assert r["estado"] == "aviso" and r["elementos"] == ["-MM1"]


def test_la_velocidad_que_el_escape_no_da_es_roja():
    rojas = malas(erc(verde(_MM1=disp("-MM1", "CIL-ISO15552-32", servicio={**SERVICIO, "velocidad_m_s": 8}))),
                  "caudal de la válvula")
    assert rojas and rojas[0]["estado"] == "error" and "ISO 6358" in rojas[0]["norma"]
    calc = rojas[0]["calc"]
    assert calc["formula"].startswith("v = C·p_ANR / A_escape")
    assert any("C del escape = el de la alimentación" in h for h in calc["hipotesis"])


def test_la_cota_de_caudal_es_la_de_la_ficha():
    """El verde llega a su 0,5 m/s con holgura: la cota de régimen del escape de la G1/8."""
    v = CATALOG["VAL-52-MONO-G18"].neumatico.caudal
    _A, Ab, _a = K.areas(32, 12)
    assert K.regimen(v.C, Ab, 200, b=v.b)["valor"]["v_m_s"] > 2.0


def test_el_vastago_que_pandea_es_rojo():
    serv = {"carrera_mm": 300, "largo_libre_mm": 400}  # Ø16/6, caso 1 (sin montaje declarado)
    m = verde(_MM1=disp("-MM1", "CIL-ISO6432-16", servicio=serv))
    (r,) = malas(erc(m), "pandeo del vástago")
    assert r["estado"] == "error" and r["calc"]["fs"] < K.FS_PANDEO
    assert any("caso 1 de Euler" in h for h in r["calc"]["hipotesis"])
    # el mismo con el vástago articulado (caso 2) y 200 mm libres, pasa (λ = 133: Euler vale)
    ok = verde(_MM1=disp("-MM1", "CIL-ISO6432-16", servicio={"carrera_mm": 200, "caso_euler": 2}))
    assert not malas(erc(ok), "pandeo del vástago")
    # corto (λ < 100) sin fy del vástago: Euler puede no valer, aviso (no un verde falso)
    corto = verde(_MM1=disp("-MM1", "CIL-ISO6432-16", servicio={"carrera_mm": 100, "caso_euler": 2}))
    assert [r["estado"] for r in malas(erc(corto), "pandeo del vástago")] == ["aviso"]


def test_la_energia_al_fin_de_carrera_sobre_la_admisible_es_roja():
    m = verde(_MM1=disp("-MM1", "CIL-ISO15552-32", servicio={**SERVICIO, "velocidad_m_s": 2, "masa_kg": 10}))
    (r,) = malas(erc(m), "energía al fin de carrera")
    masa = 0.12 + 0.000888 * 200 + 10
    assert r["calc"]["sustitucion"] == f"E = ½·{masa:g}·2² = {0.5 * masa * 4:.3f} J"
    assert r["estado"] == "error" and "2.3 J" in r["detalle"]


@pytest.mark.parametrize("regla", ["caudal de la válvula", "pandeo del vástago", "energía al fin de carrera"])
def test_sin_servicio_las_reglas_de_calculo_no_inventan(regla):
    m = verde(_MM1=disp("-MM1", "CIL-ISO15552-32"))
    (r,) = por_regla(erc(m), regla)
    assert r["estado"] == "ok" and "declara" in r["detalle"]
