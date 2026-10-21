"""Cadenas y piñones de catálogo (plan `docs/plans/cadenas-pinones.md`, F1).

44 refs reales (ASA 40 = ANSI B29.1, e ISO 606 serie B: 08B/10B/12B) con los builders `sprocket`
y `roller_chain` de `library/builders_transmision.py` y la matemática pura de
`library/transmision.py`. Lo que se prueba es lo que usarán el comando de cadena y la regla
(F2): las cotas reales del piñón medidas en el SÓLIDO, el marco canónico y sus anclas (eje +Z,
hilera 1 en z = 0, asiento en +X), eslabones ↔ centros, la tabla ACA y la posición de los
rodillos de un lazo (sentados en los asientos, sin entrar al piñón, con cualquier fase).
"""

from __future__ import annotations

import math
import random
from functools import lru_cache

import pytest
from build123d import Cylinder, Pos, Rotation, extrude

from apolo.doc import Document
from apolo.library.bom import bom_from_scene
from apolo.library.builders_transmision import perfil_dentado, sprocket
from apolo.library.catalog import CATALOG, build_component, component_anchors, refs_in_category
from apolo.library.checks import FEA_HARDWARE_CATS, HARDWARE_CATS
from apolo.library.loader import ANCLAS, BUILDERS, merge_anclas, merge_builders
from apolo.library.transmision import (
    abrazamiento_deg, camino_paso, capas_cadena, centros_para_eslabones, diametro_exterior_ansi,
    diametro_exterior_bs, diametro_primitivo, eslabones_para_centros, eslabones_pares,
    factor_hileras, factor_servicio, potencia_nominal_asa40_1_hp, rodillos_del_lazo,
    velocidad_cadena,
)

CADENAS = ["CADENA-ASA40-1", "CADENA-ASA40-2", "CADENA-08B-1", "CADENA-08B-2", "CADENA-10B-1",
           "CADENA-12B-1"]
ASA_1 = [f"PINON-ASA40-1-Z{z}" for z in (12, 14, 15, 16, 17, 18, 19, 20, 30, 45, 60)]
ASA_2 = ["PINON-ASA40-2-Z14", "PINON-ASA40-2-Z15"]
BS_08B_1 = [f"PINON-08B-1-Z{z}" for z in (9, 12, 14, 15, 16, 17, 18, 19, 20, 25, 28, 30, 38)]
BS_08B_2 = [f"PINON-08B-2-Z{z}" for z in (14, 15, 17, 19, 21, 25, 38)]
OTROS = ["PINON-ASA40-DS-Z15", "PINON-08B-DS-Z14", "PINON-10B-1-Z15", "PINON-10B-1-Z19",
         "PINON-12B-1-Z15"]
PINONES = ASA_1 + ASA_2 + BS_08B_1 + BS_08B_2 + OTROS
TODAS = CADENAS + PINONES
DOS_HILERAS = [r for r in PINONES if CATALOG[r].specs["tipo"] != "simple"]


@lru_cache(maxsize=None)
def _shape(ref: str):
    shape, _ = build_component(ref)
    return shape


def _s(ref: str) -> dict:
    return CATALOG[ref].specs


# ------------------------------------------------------------------ carga del catálogo
def test_las_44_refs_cargan_en_transmision():
    nuevas = [r for r in refs_in_category("transmision") if r.startswith(("PINON-", "CADENA-"))]
    assert sorted(nuevas) == sorted(TODAS) and len(TODAS) == 44
    assert len(PINONES) == 38 and len(DOS_HILERAS) == 11  # 2 + 1 + 7 + 1 (D2)
    for ref in TODAS:
        comp = CATALOG[ref]
        assert comp.category == "transmision", ref
        assert comp.weight > 0, ref
        assert "cost" not in comp.specs, f"{ref}: sin precio del MISMO modelo (D4)"
        assert comp.specs["no_publicado"].strip(), ref
        assert "intercambiable" in comp.description, f"{ref}: ASA 40 y 08B no son intercambiables (D1)"
        assert comp.specs["norma"] in ("ANSI B29.1", "ISO 606"), ref


@pytest.mark.parametrize("ref", PINONES)
def test_pinon_construye_un_solido_y_no_es_cortable(ref):
    comp = CATALOG[ref]
    assert not comp.cuttable
    shape = _shape(ref)
    assert shape.volume > 0 and len(shape.solids()) == 1
    s = _s(ref)
    assert s["mecanizado"].startswith("agujero piloto")
    if "estimado" in s["no_publicado"] or "peso por volumen" in s["no_publicado"]:
        # [E]: el peso declarado sale del volumen del 3D en acero
        assert math.isclose(comp.weight, shape.volume * 7.85e-6, abs_tol=0.01), ref
    else:
        # [L]: el 3D reproduce el peso publicado (cotas reales + flancos representativos)
        assert math.isclose(comp.weight, shape.volume * 7.85e-6, rel_tol=0.12), ref


@pytest.mark.parametrize("ref", CADENAS)
def test_cadena_cortable_construye_un_solido_a_lo_largo_de_x(ref):
    comp = CATALOG[ref]
    s = _s(ref)
    assert comp.cuttable and comp.weight == s["kg_m"]
    assert math.isclose(comp.default_length / s["paso"], 40, abs_tol=1e-6)  # 40 eslabones
    shape, cut = build_component(ref, 10 * s["paso"])
    assert cut == pytest.approx(10 * s["paso"])
    assert shape.volume > 0 and len(shape.solids()) == 1
    bb = shape.bounding_box()
    # 10 rodillos a un paso: 9 pasos entre centros + medio alto de placa a cada lado
    assert math.isclose(bb.max.X - bb.min.X, 9 * s["paso"] + s["alto_placa"], abs_tol=0.05)
    assert math.isclose((bb.max.X + bb.min.X) / 2, 0.0, abs_tol=1e-6)
    assert math.isclose(bb.max.Y - bb.min.Y, s["alto_placa"], abs_tol=0.05)
    assert math.isclose(bb.max.Z - bb.min.Z, s["ancho_sobre_perno"], abs_tol=0.05)
    # el plano medio de la cadena: hilera 1 en z = 0, la 2 en z = −pt (marco del piñón)
    zc = -(s["hileras"] - 1) * s.get("pt", 0.0) / 2
    assert math.isclose((bb.max.Z + bb.min.Z) / 2, zc, abs_tol=0.01)


def test_cadena_en_la_bom_pesa_kg_por_metro_por_el_largo():
    doc = Document()
    doc.execute("insert_component", {"component": "CADENA-ASA40-1", "length": 127.0})
    filas = bom_from_scene(doc.scene)
    assert len(filas) == 1
    assert filas[0]["longitud_mm"] == pytest.approx(127.0)
    assert filas[0]["peso_unitario_kg"] == pytest.approx(0.62 * 0.127, abs=1e-3)
    assert filas[0]["norma"] == "ANSI B29.1"


# ------------------------------------------------------------------ cotas del piñón en el sólido
@pytest.mark.parametrize("ref", PINONES)
def test_d0_de_y_fondo_medidos_en_el_solido(ref):
    s = _s(ref)
    shape = _shape(ref)
    p, z, d1 = s["paso"], s["z"], s["rodillo"]
    d0 = diametro_primitivo(p, z)
    assert math.isclose(d0, s["d0"], abs_tol=0.02), ref  # la ficha y la fórmula coinciden
    # d0: los arcos de asiento (radio 0.505·d1) están centrados sobre el círculo primitivo
    centros = [e.arc_center for e in shape.edges()
               if e.geom_type.name == "CIRCLE" and math.isclose(e.radius, 0.505 * d1, abs_tol=1e-4)]
    assert len(centros) >= 2 * z
    for c in centros:
        assert math.isclose(math.hypot(c.X, c.Y), d0 / 2, abs_tol=0.25), ref
    # de: con la cresta de un diente sobre +X, la caja llega a de/2
    girado = Rotation(0, 0, -180.0 / z) * shape
    assert math.isclose(2 * girado.bounding_box().max.X, s["de"], abs_tol=0.5), ref
    # fondo df = d0 − d1 (nominal; el asiento de radio 0.505·d1 lo baja 0.01·d1): en +X hay hueco
    fondo = d0 / 2 - d1 / 2
    assert shape.is_inside((fondo - 0.5, 0, 0)), ref
    assert not shape.is_inside((fondo + 0.5, 0, 0)), ref
    assert not shape.is_inside((d0 / 2, 0, 0)), ref  # el centro del asiento: ahí va el rodillo


@pytest.mark.parametrize("ref", PINONES)
def test_ancho_de_diente_cubo_largo_y_piloto(ref):
    s = _s(ref)
    shape = _shape(ref)
    bf, d = s["ancho_diente"], s.get("distancia_hileras", 0.0)
    fondo = s["d0"] / 2 - 0.505 * s["rodillo"]
    # la corona dentada: lo que queda fuera del cubo (un anillo por hilera)
    corona = shape - Cylinder((s["cubo"] / 2 + fondo) / 2, 500)
    filas = sorted(corona.solids(), key=lambda x: -x.bounding_box().max.Z)
    assert len(filas) == (1 if s["tipo"] == "simple" else 2), ref
    for k, fila in enumerate(filas):
        bb = fila.bounding_box()
        assert math.isclose(bb.max.Z - bb.min.Z, bf, abs_tol=0.01), ref
        assert math.isclose((bb.max.Z + bb.min.Z) / 2, -k * d, abs_tol=0.01), ref
    bb = shape.bounding_box()
    assert math.isclose(bb.max.Z, bf / 2, abs_tol=0.01)
    assert math.isclose(bb.min.Z, min(bf / 2 - s["largo"], -d - bf / 2), abs_tol=0.01)
    # cubo: una tajada fuera de las placas (bajo la placa en el simple; entre hileras si hay dos)
    z0, z1 = (bf / 2 - s["largo"] + 0.5, -bf / 2 - 0.5) if d == 0 else (-d + bf / 2 + 0.5, -bf / 2 - 0.5)
    tajada = shape & (Pos(0, 0, (z0 + z1) / 2) * Cylinder(500, z1 - z0))
    tb = tajada.bounding_box()
    assert math.isclose(tb.max.X - tb.min.X, s["cubo"], abs_tol=0.05), ref
    # agujero piloto pasante
    r = s["piloto_mm"] / 2
    assert not shape.is_inside((0, 0, 0)) and not shape.is_inside((r - 0.3, 0, 0))
    assert shape.is_inside((r + 0.3, 0, 0)), ref


@pytest.mark.parametrize("ref", DOS_HILERAS)
def test_dos_hileras_a_su_distancia(ref):
    s = _s(ref)
    if s["tipo"] == "duplex":
        assert s["distancia_hileras"] == s["pt"]
        cadena = _s(s["cadena"])
        assert cadena["hileras"] == 2 and cadena["pt"] == s["pt"]  # el dúplex lleva SU cadena doble
    else:
        assert _s(s["cadena"])["hileras"] == 1  # doble-simple: dos cadenas simples
    a = component_anchors(CATALOG[ref])
    assert a["hilera_2"] == {"origin": [0.0, 0.0, -s["distancia_hileras"]], "axis": [0.0, 0.0, 1.0]}


def test_el_cubo_deja_pasar_las_placas_de_la_cadena():
    """La placa en estadio pasa más cerca del eje a mitad de paso: R·cos(180°/z) − h2/2. El cubo
    (y el cubo entre hileras) queda por dentro en todo el catálogo salvo las dos refs cuyo cubo
    PUBLICADO es mayor (40B12 Tsubaki, 08B z9 TYMA): declaradas en su `no_publicado`."""
    choca = set()
    for ref in PINONES:
        s = _s(ref)
        placa = s["d0"] / 2 * math.cos(math.pi / s["z"]) - _s(s["cadena"])["alto_placa"] / 2
        if s["cubo"] / 2 >= placa:
            choca.add(ref)
            assert "solapa" in s["no_publicado"], ref
    assert choca == {"PINON-ASA40-1-Z12", "PINON-08B-1-Z9"}


def test_cada_pinon_nombra_una_cadena_de_su_misma_serie():
    for ref in PINONES:
        s = _s(ref)
        c = _s(s["cadena"])
        assert (c["serie"], c["paso"], c["rodillo"]) == (s["serie"], s["paso"], s["rodillo"]), ref
    assert _s("CADENA-ASA40-1")["rodillo"] != _s("CADENA-08B-1")["rodillo"]  # no intercambiables


# ------------------------------------------------------------------ anclas (D6)
def test_anclas_del_pinon_en_el_marco_canonico():
    s = _s("PINON-ASA40-1-Z15")
    a = component_anchors(CATALOG["PINON-ASA40-1-Z15"])
    z_ = [0.0, 0.0, 1.0]
    assert a == {
        "eje": {"origin": [0.0, 0.0, 0.0], "axis": z_},
        "hilera_1": {"origin": [0.0, 0.0, 0.0], "axis": z_},
        "fase": {"origin": [pytest.approx(s["d0"] / 2, abs=0.01), 0.0, 0.0], "axis": z_},
    }
    shape = _shape("PINON-ASA40-1-Z15")
    # la fase cae en un hueco; medio paso angular después, en un diente
    r = s["d0"] / 2
    assert not shape.is_inside(tuple(a["fase"]["origin"]))
    ang = math.pi / s["z"]
    assert shape.is_inside((r * math.cos(ang), r * math.sin(ang), 0))
    # copia fresca: mutar lo devuelto no toca el catálogo
    a["eje"]["origin"][0] = 99.0
    assert component_anchors(CATALOG["PINON-ASA40-1-Z15"])["eje"]["origin"][0] == 0.0
    assert component_anchors(CATALOG["CADENA-ASA40-1"]) is None
    # la de categoría sigue igual (garruchas: ancla `placa`)
    assert component_anchors(CATALOG["LH-ALTH-125K-3"]) == {
        "placa": {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0]}}


def test_insert_component_lleva_las_anclas_del_pinon_a_mundo():
    doc = Document()
    fid = doc.execute("insert_component", {
        "component": "PINON-ASA40-2-Z15", "position": {"x": 100, "y": 50, "z": 20},
        "rotation": {"x": 0, "y": 0, "z": 90},
    })
    an = doc.scene[fid].anchors
    r = _s("PINON-ASA40-2-Z15")["d0"] / 2
    esperado = {"eje": (100, 50, 20), "hilera_1": (100, 50, 20), "hilera_2": (100, 50, 20 - 14.38),
                "fase": (100, 50 + r, 20)}
    for nombre, o in esperado.items():
        assert all(math.isclose(u, v, abs_tol=0.02) for u, v in zip(an[nombre]["origin"], o)), nombre
        assert all(math.isclose(u, v, abs_tol=1e-9) for u, v in zip(an[nombre]["axis"], (0, 0, 1)))


def test_loader_une_builders_y_anclas_sin_repetir():
    assert {"sprocket", "roller_chain", "caster", "pulley"} <= set(BUILDERS)
    # + perfiles abiertos (D4) + la seta de emergencia (seta-de-emergencia D5)
    assert set(ANCLAS) == {"sprocket", "channel", "i_beam", "angle", "seta_emergencia"}
    with pytest.raises(ValueError, match="sprocket"):
        merge_builders(BUILDERS, {"sprocket": object()})
    with pytest.raises(ValueError, match="noexiste"):
        merge_anclas(BUILDERS, {"noexiste": object()})
    with pytest.raises(ValueError, match="sprocket"):
        merge_anclas(BUILDERS, {"sprocket": object()}, {"sprocket": object()})


def test_transmision_es_herraje_del_fea_pero_no_de_interferencia():
    assert "transmision" in FEA_HARDWARE_CATS
    assert "transmision" not in HARDWARE_CATS


# ------------------------------------------------------------------ el builder rechaza lo imposible
_BASE = dict(tipo="simple", paso=12.7, z=15, rodillo=7.92, de=67.3, ancho_diente=7.21, cubo=46.0,
             largo=22.2, piloto_mm=12.7)


@pytest.mark.parametrize("cambio,mensaje", [
    ({"tipo": "triple"}, "tipo desconocido"),
    ({"de": 90.0}, "fuera de rango"),
    ({"de": 60.0}, "fuera de rango"),
    ({"de": 76.0}, "en punta"),
    ({"cubo": 60.0}, "taparía los dientes"),
    ({"piloto_mm": 45.0}, "pared"),
    ({"distancia_hileras": 14.38}, "simple con distancia"),
    ({"tipo": "duplex", "distancia_hileras": 6.0}, "distancia entre hileras"),
    ({"tipo": "doble_simple", "distancia_hileras": 28.6, "largo": 20.0}, "no une las dos hileras"),
    ({"rodillo": 13.0}, "rodillo"),
])
def test_sprocket_rechaza_lo_imposible(cambio, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        sprocket(**{**_BASE, **cambio})


# ------------------------------------------------------------------ matemática pura
def test_diametros():
    assert diametro_primitivo(12.7, 14) == pytest.approx(57.07, abs=0.005)
    assert diametro_primitivo(12.7, 57) == pytest.approx(230.54, abs=0.005)
    for z, de in ((12, 55.1), (14, 63.2), (60, 249.9)):  # Tsubaki 40B12/14/60
        assert diametro_exterior_ansi(12.7, z) == pytest.approx(de, abs=0.15)
    assert diametro_exterior_bs(12.7, 14, 8.51) == pytest.approx(64.439, abs=0.005)  # Martin D08B14
    assert _s("PINON-08B-2-Z21")["de"] == pytest.approx(diametro_exterior_bs(12.7, 21, 8.51), abs=0.01)
    with pytest.raises(ValueError):
        diametro_primitivo(12.7, 14.5)


@pytest.mark.parametrize("z1,z2,c", [(15, 15, 95.25), (14, 30, 400), (17, 45, 381), (9, 60, 700),
                                     (20, 19, 250.5)])
def test_eslabones_y_centros_ida_y_vuelta(z1, z2, c):
    largo = eslabones_para_centros(12.7, z1, z2, c)
    assert centros_para_eslabones(12.7, z1, z2, largo) == pytest.approx(c, abs=1e-9)
    n, cx = eslabones_pares(12.7, z1, z2, c)
    assert n % 2 == 0 and cx >= c - 1e-6
    assert centros_para_eslabones(12.7, z1, z2, n) == pytest.approx(cx)
    assert centros_para_eslabones(12.7, z1, z2, n - 2) < c  # es el MENOR par


@pytest.mark.parametrize("z,t,eslabones", [(14, 76.2, 26), (14, 101.6, 30), (15, 95.25, 30),
                                           (15, 107.95, 32)])
def test_lazo_1_a_1_del_rodillo_a_rodillo(z, t, eslabones):
    n, cx = eslabones_pares(12.7, z, z, t)
    assert n == eslabones and cx == pytest.approx(t, abs=1e-9)  # sin holgura de redondeo


def test_centros_para_pocos_eslabones_es_error():
    with pytest.raises(ValueError, match="no alcanzan"):
        centros_para_eslabones(12.7, 15, 30, 20)


def test_tabla_aca_interpola_y_fuera_de_rango_da_none():
    assert potencia_nominal_asa40_1_hp(14, 10) == pytest.approx(0.07)
    assert potencia_nominal_asa40_1_hp(19, 1000) == pytest.approx(8.12)
    assert potencia_nominal_asa40_1_hp(15, 300) == pytest.approx(2.02)
    assert potencia_nominal_asa40_1_hp(15, 200) == pytest.approx(0.70 + (2.02 - 0.70) * 0.5)
    assert potencia_nominal_asa40_1_hp(17, 37.5) == pytest.approx((0.21 + 0.41) / 2)
    for z, rpm in ((15, 9.9), (15, 1001), (13, 100), (20, 100), (15.5, 100)):
        assert potencia_nominal_asa40_1_hp(z, rpm) is None, (z, rpm)


def test_factores_y_velocidad():
    assert [factor_servicio(k) for k in ("suave", "moderado", "fuerte")] == [1.0, 1.3, 1.5]
    assert factor_hileras(1) == 1.0 and factor_hileras(2) == 1.7
    with pytest.raises(ValueError, match="Servicio"):
        factor_servicio("brutal")
    with pytest.raises(ValueError):
        factor_hileras(3)
    assert velocidad_cadena(12.7, 15, 100) == pytest.approx(0.3175)


def test_camino_de_paso_y_abrazamiento():
    cam = camino_paso(12.7, 15, 15, 95.25)
    assert cam.abrazamiento_a == pytest.approx(math.pi) and cam.abrazamiento_b == pytest.approx(math.pi)
    assert cam.largo_pasos == pytest.approx(30.0)  # 1:1: z + 2C/p
    cam = camino_paso(12.7, 15, 45, 400)
    dr = cam.radio_b - cam.radio_a
    assert math.degrees(cam.abrazamiento_a) == pytest.approx(180 - 2 * math.degrees(math.asin(dr / 400)))
    assert abrazamiento_deg(12.7, 45, 15, 400) == pytest.approx(math.degrees(cam.abrazamiento_a))
    assert cam.abrazamiento_a + cam.abrazamiento_b == pytest.approx(2 * math.pi)
    # el modelo de polígono y la fórmula de eslabones casi coinciden (≤ 0.05 eslabón)
    assert cam.largo_pasos == pytest.approx(eslabones_para_centros(12.7, 15, 45, 400), abs=0.05)
    with pytest.raises(ValueError, match="dentro"):
        camino_paso(12.7, 15, 60, 50)


def test_capas_de_la_cadena():
    c = capas_cadena(7.85, 1.5, 17.8)
    assert c["rodillos"] == [pytest.approx((-3.825, 3.825))]
    assert len(c["interiores"]) == 2 and len(c["exteriores"]) == 2
    assert c["perno"] == pytest.approx((-8.9, 8.9))
    c2 = capas_cadena(7.85, 1.5, 32.3, hileras=2, pt=14.38)
    assert [round((a + b) / 2, 6) for a, b in c2["rodillos"]] == [0.0, -14.38]
    assert len(c2["exteriores"]) == 3  # dos de afuera + la placa media
    media = c2["exteriores"][1]
    assert (media[0] + media[1]) / 2 == pytest.approx(-7.19)
    capas = sorted(c2["rodillos"] + c2["interiores"] + c2["exteriores"])
    assert all(a[1] < b[0] for a, b in zip(capas, capas[1:]))  # ninguna capa toca a otra
    with pytest.raises(ValueError, match="placa media"):
        capas_cadena(7.75, 1.6, 31.0, hileras=2, pt=12.0)


# ------------------------------------------------------------------ rodillos de un lazo
_LAZOS = [(15, 15, 95.25), (14, 14, 76.2), (15, 30, 300.0), (17, 45, 400.0), (12, 20, 150.0),
          (14, 60, 260.0), (9, 38, 250.0)]


@pytest.mark.parametrize("za,zb,c", _LAZOS)
def test_rodillos_sentados_en_los_asientos_con_cualquier_fase(za, zb, c):
    p = 12.7
    ra, rb = diametro_primitivo(p, za) / 2, diametro_primitivo(p, zb) / 2
    azar = random.Random(f"{za}-{zb}-{c}")
    for _ in range(12):
        fa, fb = azar.uniform(-math.pi, math.pi), azar.uniform(-math.pi, math.pi)
        n, _cx = eslabones_pares(p, za, zb, c)
        lazo = rodillos_del_lazo(p, za, zb, c, fa, fb, n)
        pts = lazo.puntos
        assert len(pts) == n  # un lazo cerrado tiene tantos rodillos como eslabones
        assert lazo.pasos_inferior + lazo.pasos_superior + len(lazo.asentados_a) + len(lazo.asentados_b) - 2 == n
        for idx, (cx, r, z, fase) in ((lazo.asentados_a, (0.0, ra, za, fa)), (lazo.asentados_b, (c, rb, zb, fb))):
            assert len(idx) >= 2
            for i in idx:  # cada rodillo sentado está en un asiento (ángulo = fase + k·360°/z)
                x, y = pts[i][0] - cx, pts[i][1]
                assert math.hypot(x, y) == pytest.approx(r, abs=1e-9)
                k = (math.atan2(y, x) - fase) / (2 * math.pi / z)
                assert k == pytest.approx(round(k), abs=1e-7)
        sentados = set(lazo.asentados_a) | set(lazo.asentados_b)
        for i in range(n):
            j = (i + 1) % n
            d = math.dist(pts[i], pts[j])
            if i in sentados or j in sentados:
                assert d == pytest.approx(p, abs=1e-6)  # en los arcos y al salir: un paso exacto
            else:
                assert d >= p - 1e-6  # en el tramo, nunca comprimido (la holgura hace flecha)
        # ningún rodillo entra al polígono de paso de un piñón (casco convexo)
        for x, y in pts:
            assert math.hypot(x, y) >= ra * math.cos(math.pi / za) - 1e-9
            assert math.hypot(x - c, y) >= rb * math.cos(math.pi / zb) - 1e-9
        assert lazo.separacion_min == pytest.approx(p, abs=1e-6)


def test_lazo_impar_o_corto_es_error():
    with pytest.raises(ValueError, match="no alcanzan"):
        rodillos_del_lazo(12.7, 15, 15, 95.25, 0.0, 0.0, 16)
    with pytest.raises(ValueError, match="Eslabones"):
        rodillos_del_lazo(12.7, 15, 15, 95.25, 0.0, 0.0, 30.5)


def _vol(s) -> float:
    if s is None:
        return 0.0
    return s.volume if hasattr(s, "volume") else sum(x.volume for x in s)


def test_lazo_completo_sobre_dos_pinones_doble_simple_sin_interferencia():
    """El caso del rodillo a rodillo: dos PINON-ASA40-DS-Z15 a 95.25 mm (1:1, 30 eslabones), fases
    al azar, la cadena 3D completa (rodillos, pernos, placas) en la hilera 1 y en la 2 contra los
    piñones 3D completos (dientes y cubo): un sólido por lazo y volumen común cero."""
    from apolo.library.builders_transmision import cadena_por_rodillos

    s, ch = _s("PINON-ASA40-DS-Z15"), _s("CADENA-ASA40-1")
    capas = capas_cadena(ch["ancho_interior"], ch["espesor_placa"], ch["ancho_sobre_perno"])
    n, _cx = eslabones_pares(ch["paso"], 15, 15, 95.25)
    fa, fb = 0.7, 2.9
    lazo = rodillos_del_lazo(ch["paso"], 15, 15, 95.25, fa, fb, n)
    cadena = cadena_por_rodillos(lazo.puntos, True, ch["rodillo"], ch["perno"], ch["alto_placa"], capas)
    assert len(cadena.solids()) == 1
    a = Rotation(0, 0, math.degrees(fa)) * _shape("PINON-ASA40-DS-Z15")
    b = Pos(95.25, 0, 0) * Rotation(0, 0, math.degrees(fb)) * _shape("PINON-ASA40-DS-Z15")
    for dz in (0.0, -s["distancia_hileras"]):
        lazo_3d = Pos(0, 0, dz) * cadena
        assert _vol(lazo_3d & a) < 1e-3 and _vol(lazo_3d & b) < 1e-3, dz
    with pytest.raises(ValueError, match="PAR"):
        cadena_por_rodillos(lazo.puntos[:-1], True, ch["rodillo"], ch["perno"], ch["alto_placa"], capas)


@pytest.mark.parametrize("za,zb,c,de_a,de_b", [(15, 15, 95.25, 67.3, 67.3), (14, 14, 76.2, 63.2, 63.2),
                                                (15, 30, 300.0, 67.3, 128.5)])
def test_los_rodillos_no_interfieren_con_los_dientes(za, zb, c, de_a, de_b):
    """Rodillos Ø d1 en las posiciones del lazo contra la corona dentada REAL de los dos piñones,
    con fases al azar: el volumen común es cero (el comando de cadena se apoya en esto)."""
    p, d1 = 12.7, 7.92
    a0 = extrude(perfil_dentado(p, za, d1, de_a), amount=6.0)
    b0 = extrude(perfil_dentado(p, zb, d1, de_b), amount=6.0)
    azar = random.Random(f"interf-{za}-{zb}")
    for _ in range(3):
        fa, fb = azar.uniform(0, 2 * math.pi), azar.uniform(0, 2 * math.pi)
        n, _cx = eslabones_pares(p, za, zb, c)
        lazo = rodillos_del_lazo(p, za, zb, c, fa, fb, n)
        a = Rotation(0, 0, math.degrees(fa)) * a0
        b = Pos(c, 0, 0) * Rotation(0, 0, math.degrees(fb)) * b0
        comun = 0.0
        for x, y in lazo.puntos:
            rod = Pos(x, y, 3.0) * Cylinder(d1 / 2, 4.0)
            if math.hypot(x, y) < (de_a + d1) / 2:  # sólo los que alcanzan la corona
                comun += (a & rod).volume
            if math.hypot(x - c, y) < (de_b + d1) / 2:
                comun += (b & rod).volume
        assert comun < 1e-3, (fa, fb, comun)
