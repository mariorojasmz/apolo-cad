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
        "servicio del cilindro", "caudal de la válvula", "pandeo del vástago", "energía al fin de carrera",
        "relación de carga"]
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


# ── F4: relación de carga, silenciador, regulación de velocidad ──────────────────────────


def test_la_relacion_de_carga():
    def con(fuerza):
        return verde(_MM1=disp("-MM1", "CIL-ISO15552-32", servicio={**SERVICIO, "fuerza_N": fuerza}))

    assert not malas(erc(con(100)), "relación de carga")  # η = 0,21
    (r,) = malas(erc(con(400)), "relación de carga")  # η = 0,83 > 0,7 (criterio de diseño)
    assert r["estado"] == "aviso" and r["calc"]["sustitucion"] == "η = 400 / 483 = 0.83"
    (r,) = malas(erc(con(450)), "relación de carga")  # pasa los 434 N efectivos (10 % de fricción)
    assert r["estado"] == "error" and "no la mueve" in r["detalle"]


def _ficha(tipo_: str):
    from apolo.library.neumatica.ficha import parse_ficha_neumatica

    if tipo_ == "regulador_caudal":
        return parse_ficha_neumatica({
            "funcion": "RZ", "simbolo": "regulador_caudal", "fuente": "sintética (test)",
            "puertos": [{"id": "1", "rol": "entrada", "rosca": "G1/8"}, {"id": "2", "rol": "salida", "rosca": "G1/8"}],
            "modelo": {"tipo": "regulador_caudal", "caudal": {"C": 1.0, "b": 0.3}, "C_regulado": [0.02, 1.0],
                       "p_max_bar": 10}}, "RZ-TEST")
    return parse_ficha_neumatica({
        "funcion": "RZ", "simbolo": "silenciador", "fuente": "sintética (test)",
        "puertos": [{"id": "1", "rol": "entrada", "rosca": "G1/8"}],
        "modelo": {"tipo": "silenciador", "caudal": {"C": 3.0, "b": 0.3}}}, "SIL-TEST")


def _sint(des: str, tipo_: str, ajustes=None) -> Dispositivo:
    f = _ficha(tipo_)
    return Dispositivo(designacion=des, ref=f"{tipo_}-test", funcion=f.funcion, bornes=(), puertos=f.puertos,
                       neumatico=f, ajustes=dict(ajustes or {}))


TODO = frozenset({"silenciador", "regulador_caudal"})


def test_sin_refs_en_el_catalogo_no_hay_avisos_de_silenciador_ni_regulacion():
    from apolo.services.neumatica import disponibles

    reglas = erc(verde())  # `disponibles` vacío: un catálogo sin silenciadores ni reguladores
    assert not por_regla(reglas, "escape sin silenciador") and not por_regla(reglas, "regulación de velocidad")
    # desde V8.9 F7b el catálogo los trae (D16): las dos reglas corren en todo circuito
    assert {"silenciador", "regulador_caudal"} <= disponibles()


def test_escape_sin_silenciador_avisa_si_el_catalogo_los_trae():
    avisos = malas(erc(verde(), disponibles=TODO), "escape sin silenciador")
    assert sorted(r["elementos"][0] for r in avisos) == ["-QM1:3", "-QM2:3", "-QM2:5"]
    assert {r["estado"] for r in avisos} == {"aviso"}
    sil = {f"_RZ{k}": _sint(f"-RZ{k}", "silenciador") for k in (1, 2, 3)}
    ts = list(verde().tubos) + [tubo("-QM1:3", "-RZ1:1"), tubo("-QM2:3", "-RZ2:1"), tubo("-QM2:5", "-RZ3:1")]
    assert not malas(erc(verde(**sil, tubos=ts), disponibles=TODO), "escape sin silenciador")


def _con_reg(lado_cil: str, ajuste=None):
    """El verde con un regulador en línea en cada puerto del cilindro; `lado_cil`, el puerto del
    regulador que da al cilindro («2»: regula el escape)."""
    otro = "1" if lado_cil == "2" else "2"
    regs = {"_RZ1": _sint("-RZ1", "regulador_caudal", ajuste), "_RZ2": _sint("-RZ2", "regulador_caudal", ajuste)}
    ts = [tubo("-AZ1:2", "-QM1:1", "TUBO-PU-8"), tubo("-QM1:2", "-QM2:1", "TUBO-PU-8"),
          tubo("-QM2:4", f"-RZ1:{otro}"), tubo(f"-RZ1:{lado_cil}", "-MM1:A"),
          tubo("-QM2:2", f"-RZ2:{otro}"), tubo(f"-RZ2:{lado_cil}", "-MM1:B")]
    return verde(**regs, tubos=ts)


def test_regulacion_de_velocidad_por_el_escape():
    (r,) = malas(erc(verde(), disponibles=TODO), "regulación de velocidad")
    assert r["estado"] == "aviso" and "sin regulador" in r["detalle"]
    ok = erc(_con_reg("2", {"C_regulado": 0.15}), disponibles=TODO)
    assert not malas(ok, "regulación de velocidad")
    (r,) = malas(erc(_con_reg("1", {"C_regulado": 0.15}), disponibles=TODO), "regulación de velocidad")
    assert "regula la ENTRADA" in r["detalle"]


def test_el_caudal_se_revisa_a_traves_del_regulador():
    """Antes de F4 un regulador en línea daba «ninguna válvula manda el puerto». Con el escape
    estrangulado (C 0,15 en serie con la G1/8: 1/C² = Σ 1/Cᵢ², declarado), la cota de régimen del
    avance es ≈ 0,15·1000/691 = 0,22 m/s: no llega a los 0,5 pedidos."""
    av, rt = malas(erc(_con_reg("2", {"C_regulado": 0.15})), "caudal de la válvula")  # los dos sentidos
    assert "en el avance" in av["detalle"] and "en el retroceso" in rt["detalle"]
    r = av
    assert r["estado"] == "error" and "C = 0.15" in r["detalle"] and "0.22 m/s" in r["detalle"]
    assert any("1/C² = Σ 1/Cᵢ²" in h for h in r["calc"]["hipotesis"])
    # sin el ajuste: la máxima apertura (C 1,0), declarada como hipótesis; la cota pasa los 0,5 m/s
    assert not malas(erc(_con_reg("2")), "caudal de la válvula")
