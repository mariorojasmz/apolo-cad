"""El amortiguador hidráulico EXTERNO de fin de carrera (plan amortiguador-externo D1–D7).

- la ficha del catálogo (SMC RB, con su fuente) y su builder;
- cómo se declara en el `servicio` del cilindro (y un log viejo da lo mismo);
- la regla de energía por ciclo (E = ½·m·v² + F·S, la fórmula de la ficha) y por hora, en el
  límite verde y por encima rojo; sin ritmo, sin evaluar;
- de punta a punta: `electrical_check`, la memoria y el panel del aire de un documento.
"""

from __future__ import annotations

import pytest

from apolo.doc.document import Document, DocumentError
from apolo.library.catalog import CATALOG
from apolo.library.neumatica import amortiguador as A
from apolo.library.neumatica.erc import erc
from apolo.library.neumatica.lineas import analizar
from apolo.library.neumatica.memoria import reglas as memoria
from apolo.services import neumatica as SN
from test_neumatica_erc import SERVICIO, disp, malas, por_regla, verde

REFS = ["AMORT-HID-M14-12", "AMORT-HID-M14-12-T", "AMORT-HID-M20-15", "AMORT-HID-M20-15-T",
        "AMORT-HID-M27-25", "AMORT-HID-M27-25-T"]
FICHAS = SN.amortiguadores()
#: (ref, carrera, E/ciclo, E/hora, n máx, F máx, rosca) de la tabla «Specifications» de SMC RB
SMC_RB = [("AMORT-HID-M14-12", 12, 19.6, 52920, 45, 814, "M14x1.5"),
          ("AMORT-HID-M20-15", 15, 58.8, 88200, 25, 1961, "M20x1.5"),
          ("AMORT-HID-M27-25", 25, 147, 88200, 10, 2942, "M27x1.5")]


# ── la ficha y el builder ──────────────────────────────────────────────────────────────


def test_las_refs_del_catalogo_son_las_de_la_familia():
    assert sorted(r for r, c in CATALOG.items() if c.familia == A.FAMILIA) == REFS
    assert sorted(FICHAS) == REFS


@pytest.mark.parametrize("ref, S, E, Eh, n, F, rosca", SMC_RB)
def test_cada_cifra_es_la_de_la_ficha_smc_rb(ref, S, E, Eh, n, F, rosca):
    for r in (ref, ref + "-T"):
        f = FICHAS[r]
        assert (f.carrera_mm, f.E_max_J, f.E_max_hora_J, f.n_max_ciclos_min, f.F_max_N, f.rosca) == (S, E, Eh, n, F, rosca)
        assert (f.v_min_m_s, f.v_max_m_s) == (0.05, 5.0)
        assert f.E_max_hora_J == pytest.approx(f.E_max_J * f.n_max_ciclos_min * 60)  # derivada, declarada
        assert "SMC RB" in f.fuente and "E_max_hora_J" in f.a_confirmar
        assert "SMC RB" in CATALOG[r].specs["linea_referencia"]


def test_la_ficha_incompleta_no_carga():
    specs = dict(CATALOG["AMORT-HID-M14-12"].specs)
    for falta in ("fuente", "E_max_hora_J", "F_max_N"):
        with pytest.raises(ValueError, match=rf"ficha incompleta, falta {falta}"):
            A.parse_ficha({k: v for k, v in specs.items() if k != falta}, "X")


@pytest.mark.parametrize("ref", REFS)
def test_el_builder_da_un_solido_del_largo_de_la_ficha(ref):
    c = CATALOG[ref]
    forma = c.builder(None)
    assert len(forma.solids()) == 1
    bb = forma.bounding_box()
    assert bb.size.X == pytest.approx(c.specs["LL"], abs=1e-6)  # largo total extendido
    assert bb.size.Y == pytest.approx(c.specs["B"], abs=1e-6)   # entrecaras de la tuerca
    assert c.anchors["extremo_vastago"]["origin"][0] == pytest.approx(c.specs["LL"] - c.specs["L"])
    assert ("tope" in c.anchors) == ref.endswith("-T")
    if ref.endswith("-T"):  # el vástago comprimido toda su carrera queda a ras del tope
        assert c.anchors["extremo_vastago"]["origin"][0] - c.anchors["tope"]["origin"][0] == c.specs["carrera_mm"]


# ── la cuenta (fórmula de la ficha) ────────────────────────────────────────────────────


def test_el_ejemplo_de_seleccion_de_la_ficha():
    """SMC RB, «Selection Example» 2: 50 kg a 0,3 m/s con un Ø40 a 0,5 MPa sobre un RB2015:
    E1 = 2,3 J, E2 = 9,4 J, E = 11,7 J, Me ≈ 260 kg."""
    F = 0.5 * 3.14159265 * 40 ** 2 / 4
    r = A.choque(50, 0.3, F, FICHAS["AMORT-HID-M20-15"], extremo="avance")
    v = r["valor"]
    assert (round(v["E1_J"], 1), round(v["E2_J"], 1), round(v["E_J"], 1)) == (2.2, 9.4, 11.7)
    assert v["Me_kg"] == pytest.approx(260, rel=0.01) and r["estado"] == "ok"


def test_en_el_limite_es_verde_y_encima_rojo():
    f = FICHAS["AMORT-HID-M14-12"]
    assert A.choque(20.0, 1.4, 0.0, f, extremo="avance")["estado"] == "ok"      # E = 19,6 J = la máxima
    r = A.choque(20.2, 1.4, 0.0, f, extremo="avance")
    assert r["estado"] == "error" and "19.6 J por ciclo" in r["valor"]["motivos"][0]
    assert A.choque(1.0, 1.0, 814.0, f, extremo="avance")["estado"] == "ok"     # F en la máxima
    assert A.choque(1.0, 1.0, 815.0, f, extremo="avance")["estado"] == "error"  # F sobre la máxima
    assert A.choque(0.1, 5.5, 0.0, f, extremo="avance")["estado"] == "error"    # v sobre el rango
    chico = A.choque(0.1, 1.0, 0.0, f, extremo="avance")                        # 0,05 J < 5 %: un tamaño menor
    assert chico["estado"] == "aviso" and "tamaño menor" in chico["valor"]["motivos"][0]


def test_la_energia_por_hora():
    f = FICHAS["AMORT-HID-M14-12"]
    assert A.por_hora(19.6, 45, f, extremo="avance")["estado"] == "ok"   # 52 920 J/h: la máxima
    r = A.por_hora(19.6, 46, f, extremo="avance")
    assert r["estado"] == "error" and r["calc"]["sustitucion"] == "E_h = 19.60·46·60 = 54096 J/h"
    assert A.por_hora(5.0, 150, f, extremo="avance")["estado"] == "ok"   # menos energía, más ciclos
    assert A.por_hora(19.6, None, f, extremo="avance")["estado"] == "sin_evaluar"


# ── el ERC del cilindro ────────────────────────────────────────────────────────────────


def _cil(**servicio):
    return verde(_MM1=disp("-MM1", "CIL-ISO15552-63", servicio={**SERVICIO, **servicio}))


def test_sin_amortiguador_el_erc_es_el_de_antes():
    for m in (verde(), _cil(velocidad_m_s=2, masa_kg=10)):
        assert erc(m) == erc(m, amortiguadores=FICHAS, paquetes_min=15, refs_escena=frozenset({"X"}))
        assert not por_regla(erc(m, amortiguadores=FICHAS), "amortiguador externo")
        c = analizar(m)
        assert memoria(c) == memoria(c, amortiguadores=FICHAS, paquetes_min=15)


def test_el_extremo_con_amortiguador_deja_la_amortiguacion_del_cilindro():
    # 10 kg a 2 m/s: 21 J contra los 11,4 J de la amortiguación del Ø63 → rojo sin amortiguador
    sin = _cil(velocidad_m_s=2, masa_kg=10)
    assert [r["estado"] for r in malas(erc(sin), "energía al fin de carrera")] == ["error"]
    uno = _cil(velocidad_m_s=2, masa_kg=10, amortiguador_avance="AMORT-HID-M27-25")
    (r,) = malas(erc(uno, amortiguadores=FICHAS), "energía al fin de carrera")
    assert "llega al retroceso con" in r["detalle"]  # el otro extremo sigue con la del cilindro
    dos = _cil(velocidad_m_s=2, masa_kg=10, amortiguador_avance="AMORT-HID-M27-25",
               amortiguador_retroceso="AMORT-HID-M27-25")
    (r,) = por_regla(erc(dos, amortiguadores=FICHAS, paquetes_min=6), "energía al fin de carrera")
    assert r["estado"] == "ok" and "amortiguadores externos" in r["detalle"]


def test_el_erc_usa_la_formula_de_la_ficha():
    m = _cil(velocidad_m_s=0.7, masa_kg=23, amortiguador_avance="AMORT-HID-M27-25",
             amortiguador_retroceso="AMORT-HID-M20-15")
    av, rt = por_regla(erc(m, amortiguadores=FICHAS, paquetes_min=10), "amortiguador externo")
    masa = 0.430 + 0.0025 * 200 + 23          # masa móvil de la ficha del Ø63 + la carga
    F_av = 6 * 0.1 * 3.14159265 * 63 ** 2 / 4  # p·A a 6 bar
    E = 0.5 * masa * 1.4 ** 2 + F_av * 0.025   # v de choque = 2·0,7 (la ficha: 2·v̄)
    assert av["calc"]["sustitucion"].endswith(f"= {E:.2f} J") and av["estado"] == "ok"
    assert "al avance" in av["detalle"] and "al retroceso" in rt["detalle"] and rt["estado"] == "ok"
    assert any("2·v̄" in h for h in av["calc"]["hipotesis"])
    assert f"10 de 10 ciclos/min; {E * 10 * 60:.0f} J/h de 88200 J/h" in av["detalle"]


def test_por_encima_de_la_ficha_es_rojo():
    caro = _cil(velocidad_m_s=1.5, masa_kg=23, amortiguador_avance="AMORT-HID-M20-15")
    (r,) = malas(erc(caro, amortiguadores=FICHAS, paquetes_min=15), "amortiguador externo")
    assert r["estado"] == "error" and "58.8 J" in r["detalle"] and r["recomendacion"]
    # la fuerza del Ø63 a 6 bar (1870 N) pasa la del M14 (814 N) aunque la energía alcanzara
    (r,) = malas(erc(_cil(velocidad_m_s=0.1, masa_kg=0, amortiguador_avance="AMORT-HID-M14-12"),
                     amortiguadores=FICHAS, paquetes_min=1), "amortiguador externo")
    assert r["estado"] == "error" and "814 N admisibles" in r["detalle"]


def test_la_frecuencia_en_el_erc():
    """El RB2015 admite 25 ciclos/min (la ficha): en el límite verde, encima rojo con la ref que
    entra; la cadencia del cilindro manda sobre la capacidad nominal (D5)."""
    base = dict(velocidad_m_s=0.5, masa_kg=5, amortiguador_retroceso="AMORT-HID-M20-15")
    assert not malas(erc(_cil(**base), amortiguadores=FICHAS, paquetes_min=25), "amortiguador externo")
    (r,) = malas(erc(_cil(**base), amortiguadores=FICHAS, paquetes_min=26), "amortiguador externo")
    assert r["estado"] == "error" and r["calc"]["titulo"].endswith("frecuencia")
    assert "26 ciclos/min pasan la frecuencia máxima de la ficha (25)" in r["detalle"]
    # ninguno del catálogo entra: el M14 no aguanta el empuje y el M27 admite 10 ciclos/min
    assert r["recomendacion"].endswith("Ningún amortiguador del catálogo entra con estas cifras.")
    assert not malas(erc(_cil(**base, ciclos_min=25), amortiguadores=FICHAS, paquetes_min=50),
                     "amortiguador externo")
    # sin ninguna de las dos: frecuencia y energía por hora SIN EVALUAR (el ciclo sí se revisa)
    (r,) = por_regla(erc(_cil(**base), amortiguadores=FICHAS), "amortiguador externo")
    assert r["estado"] == "ok" and "frecuencia y la energía por hora quedan SIN EVALUAR" in r["detalle"]


def test_el_m27_a_15_ciclos_sale_de_ficha_y_sugiere_el_que_entra():
    """La faja a 15 cajas/min: el M27 al avance pasa la energía pero no la frecuencia (10/min); el
    que entra con estas cifras es el M20 (sin repetir su variante con tope)."""
    m = _cil(velocidad_m_s=0.7, masa_kg=23, carrera_mm=800, amortiguador_avance="AMORT-HID-M27-25")
    (r,) = malas(erc(m, amortiguadores=FICHAS, paquetes_min=15), "amortiguador externo")
    assert r["estado"] == "error" and "15 ciclos/min pasan la frecuencia máxima de la ficha (10)" in r["detalle"]
    assert r["recomendacion"].endswith("Entra con estas cifras: AMORT-HID-M20-15.")
    assert not malas(erc(m, amortiguadores=FICHAS, paquetes_min=10), "amortiguador externo")


def test_con_frecuencia_y_ciclo_en_ficha_la_hora_tambien():
    """E_h,máx = E máx · n máx · 60 (derivada): con E ≤ E máx y n ≤ n máx la energía por hora
    nunca pasa; su fila queda como dato para cuando una ficha la publique aparte (F4)."""
    for f in FICHAS.values():
        assert A.por_hora(f.E_max_J, f.n_max_ciclos_min, f, extremo="avance")["estado"] == "ok"


def test_la_frecuencia():
    f = FICHAS["AMORT-HID-M27-25"]
    assert A.frecuencia(10, f, extremo="avance")["estado"] == "ok"
    r = A.frecuencia(10.5, f, extremo="avance")
    assert r["estado"] == "error" and r["calc"]["sustitucion"] == "n = 10.5 contra 10 ciclos/min"
    assert A.frecuencia(None, f, extremo="avance")["estado"] == "sin_evaluar"
    entran = A.entran(25.43, 1.4, 1870, 15, FICHAS, extremo="avance")
    assert [x.ref for x in entran] == ["AMORT-HID-M20-15"]


def test_sin_ficha_ni_pieza_avisa():
    m = _cil(amortiguador_avance="AMORT-HID-M20-15")
    (r,) = por_regla(erc(m), "amortiguador externo")
    assert r["estado"] == "aviso" and "sin la ficha" in r["detalle"]
    (r,) = por_regla(erc(m, amortiguadores=FICHAS, refs_escena=frozenset({"OTRA"})), "amortiguador sin pieza")
    assert r["estado"] == "aviso" and "no se compra ni se monta" in r["detalle"]
    assert not por_regla(erc(m, amortiguadores=FICHAS, refs_escena=frozenset({"AMORT-HID-M20-15"})),
                         "amortiguador sin pieza")


def test_la_memoria_usa_la_velocidad_medida():
    m = _cil(velocidad_m_s=0.7, masa_kg=23, amortiguador_avance="AMORT-HID-M27-25")
    c = analizar(m)
    sim = {"-MM1": {"escenario": "nominal", "pico": {"v_max_m_s": 1.1, "escenario": "nominal"}}}
    filas = [f for f in memoria(c, cosim=sim, amortiguadores=FICHAS, paquetes_min=10)
             if f["regla"] == "amortiguador externo"]
    t = "-MM1 · Amortiguador AMORT-HID-M27-25 al avance"
    assert [f["calc"]["titulo"] for f in filas] == [t, f"{t}: frecuencia", f"{t}: energía por hora"]
    assert filas[0]["valor"]["v_m_s"] == 1.1  # la medida, no 2·v̄
    assert [f["estado"] for f in filas] == ["ok", "ok", "ok"]  # 10 ciclos/min: el límite de la ficha
    rojo = [f for f in memoria(c, cosim=sim, amortiguadores=FICHAS, paquetes_min=11)
            if f["regla"] == "amortiguador externo"]
    assert [f["estado"] for f in rojo] == ["ok", "error", "ok"]
    assert rojo[1]["recomendacion"].endswith("Entra con estas cifras: AMORT-HID-M20-15.")
    sin = memoria(c, amortiguadores=FICHAS)
    (alc,) = [f for f in sin if f["regla"] == "alcance de la memoria del aire"]
    assert "su frecuencia y su energía por hora quedan sin evaluar" in alc["detalle"]
    # el retroceso, sin amortiguador, sigue con la amortiguación del cilindro
    (imp,) = [f for f in sin if f["regla"] == "energía al fin de carrera"]
    assert "llega al retroceso" in imp["detalle"]


# ── la declaración en el documento ─────────────────────────────────────────────────────


def _doc(servicio: dict, requisitos: dict | None = None) -> Document:
    d = Document("amortiguador")
    d.execute_many([
        {"type": "add_device", "params": {"ref": "FR-G14", "ajustes": {"p_regulada_bar": 6}}},
        {"type": "add_device", "params": {"ref": "CORTE-ESC-G14"}},
        {"type": "add_device", "params": {"ref": "VAL-52-MONO-G18"}},
        {"type": "add_device", "params": {"ref": "CIL-ISO15552-63", "servicio": servicio}},
        {"type": "add_tubo", "params": {"desde": "-AZ1:2", "hasta": "-QM1:1", "ref": "TUBO-PU-8"}},
        {"type": "add_tubo", "params": {"desde": "-QM1:2", "hasta": "-QM2:1", "ref": "TUBO-PU-8"}},
        {"type": "add_tubo", "params": {"desde": "-QM2:4", "hasta": "-MM1:A", "ref": "TUBO-PU-6"}},
        {"type": "add_tubo", "params": {"desde": "-QM2:2", "hasta": "-MM1:B", "ref": "TUBO-PU-6"}},
    ])
    if requisitos:
        d.set_requirements(requisitos)
    return d


def test_un_servicio_sin_amortiguador_guarda_lo_mismo_que_antes():
    d = _doc({"carrera_mm": 800, "velocidad_m_s": 0.7, "masa_kg": 23})
    cil = next(x for x in d.electrico.dispositivos if x.designacion == "-MM1")
    assert cil.servicio == {"carrera_mm": 800.0, "velocidad_m_s": 0.7, "masa_kg": 23.0}


def test_la_ref_del_amortiguador_se_valida_al_entrar():
    with pytest.raises(DocumentError, match=r"amortiguador_avance: «AMORT-HID-M20-16» no es un amortiguador.*"
                                            r"¿Quisiste decir: AMORT-HID-M20-15"):
        _doc({"carrera_mm": 800, "amortiguador_avance": "AMORT-HID-M20-16"})


def test_de_punta_a_punta_con_editar_el_servicio():
    from apolo.services.electrico import reglas_erc
    from apolo.services.neumatica_panel import panel

    d = _doc({"carrera_mm": 800, "velocidad_m_s": 0.7, "masa_kg": 23}, {"paquetes_por_minuto": 15})
    assert not [r for r in reglas_erc(d) if r["regla"].startswith("amortiguador")]
    cid = next(c["id"] for c in d.commands if c["params"].get("ref") == "CIL-ISO15552-63")
    servicio = {**d.commands[[c["id"] for c in d.commands].index(cid)]["params"]["servicio"],
                "amortiguador_avance": "AMORT-HID-M20-15", "amortiguador_retroceso": "AMORT-HID-M20-15"}
    d.edit(cid, {"servicio": servicio}, merge=True)  # lo que hace edit_command (PATCH superficial)
    filas = [r for r in reglas_erc(d) if r["regla"] == "amortiguador externo"]
    assert [r["estado"] for r in filas] == ["ok", "ok"] and all("15 de 25 ciclos/min" in r["detalle"] for r in filas)
    mem = [f for f in SN.memoria(d) if f["regla"] == "amortiguador externo"]
    assert len(mem) == 6  # por ciclo, frecuencia y hora, en los dos extremos
    p = panel(d)
    assert not [i for i in p["items"] if i["clave"].startswith(("sin-velocidad", "sin-ritmo"))]
    sin_ritmo = _doc({**servicio, "carrera_mm": 800})  # sin capacidad nominal ni cadencia
    assert [i["severidad"] for i in panel(sin_ritmo)["items"] if i["clave"].startswith("sin-ritmo")] == [
        "sin_evaluar", "sin_evaluar"]


def test_el_panel_dice_la_frecuencia():
    from apolo.services.neumatica_panel import panel

    servicio = {"carrera_mm": 800, "velocidad_m_s": 0.7, "masa_kg": 23, "amortiguador_avance": "AMORT-HID-M27-25"}

    def golpes(ppm):
        return [i for i in panel(_doc(servicio, {"paquetes_por_minuto": ppm}))["items"] if "golpes por minuto" in i["frase"]]

    assert not golpes(10)  # en el límite de la ficha
    (i,) = golpes(15)
    assert i["severidad"] == "falla" and "recibe 15 golpes por minuto y admite 10" in i["frase"]
    assert i["detalle"] == "Entra uno de este tamaño: AMORT-HID-M20-15."
