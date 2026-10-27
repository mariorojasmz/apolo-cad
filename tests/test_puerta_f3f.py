"""F3f de puerta-sin-sobrediseno: tres defectos de la puerta que halló el modelador del elevador
vertical de cajas (la máquina estaba bien; la puerta fallaba por defectos propios).

1. El piso de una máquina ANCLADA es un sólido para las sondas ISO 13857: ninguna nace ni pasa
   por debajo de la losa. El hueco entre el piso y el borde de un panel sí se sondea y lo decide
   la tabla 4 (el dedo por 10 mm). Sobre ruedas, el brazo sigue llegando por debajo.
2. Un remache ciego declara su Ø («Ø4.8», DIN 7337) en el `fasten` y la unión remachada se
   dimensiona a cortante como la de pernos.
3. `estructura.pandeo` evalúa las columnas verticales de perfil de catálogo (Euler/Johnson, K
   de AISC) y lo que no puede evaluar se justifica por escrito.
"""

from __future__ import annotations

import math

import pytest
from build123d import Box, Pos

from apolo.commands.registry import CommandError
from apolo.doc import Document
from apolo.library.calidad.item import OK, SIN_EVALUAR
from apolo.library.calidad.vida_util import controlar_vida_util
from apolo.library.engineering import remaches
from apolo.library.engineering.columna import K_EMPOTRADA_LIBRE, carga_critica_n
from apolo.library.seguridad.sondas import cruce_piso, origen
from apolo.services.calidad_codo import campo_alcance
from apolo.services.calidad_seguridad import datos_calidad
from apolo.services.calidad_sondas import Trazador, evaluar_peligro
from apolo.services.columnas_rules import columna_rules, detectar_columnas
from apolo.services.engineering_rules import structure_rules

G = 9.81


# ------------------------------------------------------------------ 1. el piso
def test_origen_con_piso_solido_no_nace_bajo_la_losa():
    caja = ((-100.0, -100.0, 10.0), (100.0, 100.0, 400.0))
    p, arriba = (0.0, 0.0, 100.0), (0.0, 0.0, 1.0)  # el rayo SUBE: viene de abajo
    assert "origen" in origen(p, arriba, caja, 0.0)  # sobre ruedas: nace en el piso
    assert origen(p, arriba, caja, 0.0, piso_solido=True) == {"bajo_piso": True}
    lateral = (1.0, 0.0, 0.0)  # por el costado, a 100 mm del piso: igual que antes
    assert origen(p, lateral, caja, 0.0, piso_solido=True) == origen(p, lateral, caja, 0.0)


def test_el_piso_estrecha_el_haz_como_una_pared():
    assert cruce_piso((0, 0, 5), (1, 0, 0), 100.0, 0.0) is None          # sobre el piso
    assert cruce_piso((0, 0, 5), (0.6, 0, -0.8), 100.0, 0.0) == pytest.approx(6.25)  # baja: entra
    assert cruce_piso((0, 0, -1), (0.8, 0, 0.6), 100.0, 0.0) == pytest.approx(1 / 0.6)  # sale
    assert cruce_piso((0, 0, -1), (1, 0, 0), 50.0, 0.0) == 50.0          # va bajo el piso entero


def _cerramiento(hueco: float = 10.0, peligro=(0.0, 0.0, 100.0), lado: float = 20.0):
    """Cuatro paneles de 2 mm hasta `hueco` del piso (z = 0) y un techo: la caja 400 × 400 de una
    máquina con un peligro (un cubo de `lado`) adentro."""
    alto = 400.0
    zc = hueco + alto / 2.0
    s = {
        "panel_x0": Pos(-201, 0, zc) * Box(2, 404, alto),
        "panel_x1": Pos(201, 0, zc) * Box(2, 404, alto),
        "panel_y0": Pos(0, -201, zc) * Box(400, 2, alto),
        "panel_y1": Pos(0, 201, zc) * Box(400, 2, alto),
        "techo": Pos(0, 0, hueco + alto + 1) * Box(404, 404, 2),
        "peligro": Pos(*peligro) * Box(lado, lado, lado),
    }
    solidos = {k: list(v.solids()) for k, v in s.items()}
    caja = ((-202.0, -202.0, hueco), (202.0, 202.0, hueco + alto + 2.0))
    return solidos, caja


def _sondas(solidos, caja, objetivo, piso_solido):
    peligro = {"id": "giro:peligro", "piezas": ["peligro"], "objetivos": [objetivo],
               "tipo": "enganche"}
    s, _ms = evaluar_peligro(Trazador(solidos), peligro, caja, 0.0, 64, piso_solido=piso_solido)
    return s


def test_anclada_ninguna_sonda_entra_por_debajo_de_la_losa():
    """El peligro a 100 mm del piso, dentro de paneles que llegan a 10 mm: sobre ruedas el brazo
    llega por debajo (FALLA); anclada, la losa es sólida y por un hueco de 10 mm sólo pasa el
    dedo, a más de su sr de la tabla 4: nada llega."""
    solidos, caja = _cerramiento()
    antes = _sondas(solidos, caja, (0.0, 0.0, 100.0), piso_solido=False)
    assert any(x["alcanza"] and x["entrada"][2] == pytest.approx(0.0) for x in antes)
    ahora = _sondas(solidos, caja, (0.0, 0.0, 100.0), piso_solido=True)
    assert not any(x["alcanza"] for x in ahora)
    assert any(x.get("motivo") == "el piso" for x in ahora)


def test_el_hueco_piso_panel_lo_decide_la_tabla_del_dedo():
    """El mismo hueco de 10 mm con un peligro a 3 mm detrás del panel, a la altura del hueco: el
    dedo pasa (abertura < 10–12 mm, sr de 80–100 mm de la tabla 4) y llega. Con el piso sólido
    se sondea igual desde el lado accesible."""
    solidos, caja = _cerramiento(peligro=(0.0, 195.0, 5.0), lado=4.0)
    s = _sondas(solidos, caja, (0.0, 195.0, 5.0), piso_solido=True)
    llegan = [x for x in s if x["alcanza"]]
    assert llegan, [x.get("motivo") for x in s]
    # un dedo por la rendija (de frente, < 10 mm; en diagonal la ve más angosta), nunca el brazo
    assert any(x["abertura_mm"] == "< 10" and x["sr_requerida_mm"] == 80.0 for x in llegan)
    assert all(x["abertura_mm"] in ("< 6", "< 8", "< 10", "< 12") for x in llegan)
    assert all(x["sr_mm"] < x["sr_requerida_mm"] for x in llegan)


def test_el_brazo_doblado_no_atraviesa_la_losa():
    """El campo de la muñeca: dentro del cerramiento cerrado, a 25 mm del piso, sobre ruedas se
    llega por el piso (semilla bajo la máquina); anclada, por el hueco de 10 mm no cabe el brazo."""
    solidos, caja = _cerramiento()
    solidos = {k: v for k, v in solidos.items() if k != "peligro"}
    p = (0.0, 0.0, 25.0)
    assert campo_alcance(solidos, caja, 0.0).profundidad(p) is not None
    assert campo_alcance(solidos, caja, 0.0, piso_solido=True).profundidad(p) is None


def _maquina(anclada: bool, colgada: bool = False):
    d = Document("piso")
    base = d.execute("create_box", {"name": "Placa base", "width": 300, "depth": 300,
                                    "height": 10, "position": {"z": 5}})
    d.execute("create_box", {"name": "Panel lateral", "width": 2, "depth": 300, "height": 400,
                             "position": {"x": 150, "z": 220}})
    if colgada:  # algo por debajo de lo anclado: no es el piso (una máquina en la pared)
        d.execute("create_box", {"name": "Bandeja inferior", "width": 100, "depth": 100,
                                 "height": 10, "position": {"z": -200}})
    if anclada:
        d.execute("ground", {"name": "g_base", "feature": base})
    return d


@pytest.mark.parametrize("anclada,colgada,solido", [(True, False, True), (False, False, False),
                                                     (True, True, False)])
def test_el_piso_es_solido_solo_si_la_maquina_esta_anclada_a_el(anclada, colgada, solido):
    dc = datos_calidad(_maquina(anclada, colgada))
    assert dc["piso_solido"] is solido
    if solido:
        assert dc["z_piso"] == pytest.approx(0.0)


# ------------------------------------------------------------------ 2. remaches
def test_el_remache_declara_su_diametro_y_tiene_capacidad():
    assert remaches.diametro("Ø4.8") == 4.8 and remaches.diametro("M6") is None
    assert remaches.designacion(4.8) == "Ø4.8" and remaches.designacion(4.0) == "Ø4"
    # 0,6 · 500 · π/4·(4,8² − 2,88²) / 1,25
    esperado = 0.6 * 500.0 * math.pi / 4.0 * (4.8 ** 2 - (0.6 * 4.8) ** 2) / 1.25
    assert remaches.capacidad_corte_n("Ø4.8") == pytest.approx(esperado)
    assert remaches.capacidad_corte_n("Ø5") is None  # fuera de catálogo


def _colgada(size: str, qty: int = 2):
    d = Document("remache")
    base = d.execute("create_box", {"name": "Bastidor", "width": 400, "depth": 400,
                                    "height": 20, "position": {"z": 10}})
    d.execute("ground", {"name": "g", "feature": base})
    d.execute("create_box", {"name": "Bandeja colgada", "width": 400, "depth": 400,
                             "height": 50, "position": {"z": -25}})
    cola = d.commands[-1]["id"]
    d.execute("fasten", {"name": "u_bandeja", "a": base, "b": cola, "kind": "perno",
                         "size": size, "qty": qty})
    return d, cola


def test_el_fasten_acepta_el_diametro_del_remache_y_rechaza_otra_cosa():
    d, _ = _colgada("Ø4.8")
    assert d.fasteners["u_bandeja"]["size"] == "Ø4.8"
    with pytest.raises(CommandError):
        _colgada("4.8x10")


def test_la_union_remachada_se_dimensiona_a_cortante():
    d, cola = _colgada("Ø4.8")
    reglas = structure_rules(d, 0.0, None)
    assert not any(r["regla"] == "uniones apernadas sin dimensionar" for r in reglas)
    (r,) = [r for r in reglas if r["regla"].startswith("unión remachada")]
    masa = d.scene[cola].shape.volume * 7.85e-6
    util = masa * G / (2 * remaches.capacidad_corte_n("Ø4.8"))
    assert r["calc"]["fs"] == pytest.approx(1 / util, rel=0.02)
    assert "EN 1993-1-8" in r["calc"]["norma"] and r["hipotesis"]
    items = {i.id: i for i in controlar_vida_util(reglas, hay_uniones=True)}
    assert items["vida.dimensionadas"].estado == OK
    assert items["vida.uniones"].estado == OK


# ------------------------------------------------------------------ 3. columnas
L_COL = 2000.0


def _columna(base="soldadura", carga_kg=200.0, rol="Columna izquierda", cuelga=False):
    """Un TUBO-4X4 vertical de 2 m sobre una placa anclada (unida por `base`) y una carga arriba
    atornillada (o, con `cuelga`, la columna colgada de la carga anclada)."""
    d = Document("col")
    placa = d.execute("create_box", {"name": "Placa base", "width": 250, "depth": 250,
                                     "height": 12, "position": {"z": 6}})
    col = d.execute("insert_component", {"name": rol, "component": "TUBO-4X4", "length": L_COL,
                                         "position": {"z": 12 + L_COL / 2.0}})
    lado = (carga_kg / 7.85e-6 / 50.0) ** 0.5  # una losa de acero de 50 mm con esa masa
    arriba = d.execute("create_box", {"name": "Carga superior", "width": lado, "depth": lado,
                                      "height": 50, "position": {"z": 12 + L_COL + 25}})
    d.execute("ground", {"name": "g", "feature": arriba if cuelga else placa})
    d.execute("fasten", {"name": "u_base", "a": placa, "b": col, "kind": base,
                         **({"size": "M12", "qty": 4} if base == "perno" else {})})
    d.execute("fasten", {"name": "u_cabeza", "a": col, "b": arriba, "kind": "perno",
                         "size": "M12", "qty": 4})
    return d, col, arriba


def test_la_columna_soldada_se_evalua_con_euler_johnson_y_k_de_aisc():
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.secciones import seccion_catalogo
    from apolo.library.materials import resolve_material, yield_strength, young_modulus

    d, col, arriba = _columna()
    (r,) = [r for r in structure_rules(d, 0.0, None) if r["regla"].startswith("pandeo de columna")]
    comp = CATALOG["TUBO-4X4"]
    sec = seccion_catalogo(comp.familia, comp.params)
    mat = resolve_material(d.scene[col], CATALOG)
    n = (comp.weight * L_COL / 1000.0 + d.scene[arriba].shape.volume * 7.85e-6) * G
    c = carga_critica_n(young_modulus(mat), yield_strength(mat), sec.area_mm2, sec.i_min_mm4,
                        L_COL, K_EMPOTRADA_LIBRE)
    assert r["estado"] == "ok" and r["piezas"] == [col]
    assert r["calc"]["fs"] == pytest.approx(c["pcr_n"] / n, rel=0.02)
    assert c["metodo"] == "Johnson"  # λ = 2,1·2000/38,6 ≈ 109 < λc ≈ 126
    assert "C-A-7.1" in r["calc"]["norma"] and "base soldada" in r["calc"]["entradas"]["K"]
    items = {i.id: i for i in controlar_vida_util(structure_rules(d, 0.0, None), hay_uniones=True)}
    assert items["vida.pandeo"].estado == OK


def test_la_columna_sobrecargada_falla():
    d, _col, _ = _columna(carga_kg=20000.0)
    (r,) = [r for r in structure_rules(d, 0.0, None) if r["regla"].startswith("pandeo de columna")]
    assert r["estado"] in ("aviso", "error") and r["calc"]["fs"] < 3.0


def test_la_base_atornillada_no_se_evalua_y_se_justifica_por_escrito():
    d, col, _ = _columna(base="perno")
    reglas = structure_rules(d, 0.0, None)
    (r,) = [r for r in reglas if r["regla"].startswith("pandeo de columna")]
    assert r["no_evaluada"] and r["piezas"] == [col] and "atornillada" in r["detalle"]
    it = {i.id: i for i in controlar_vida_util(reglas, hay_uniones=True)}["vida.pandeo"]
    assert it.estado == SIN_EVALUAR
    assert it.evidencia["casos"][0]["como_justificar"] == [{"regla": r["regla"], "piezas": [col]}]
    just = [{"regla": r["regla"], "porque": "placa base de 4 pernos M12 químicos: empotrada "
                                            "según el fabricante del anclaje"}]
    it = {i.id: i for i in controlar_vida_util(reglas, hay_uniones=True,
                                               justificadas=just)}["vida.pandeo"]
    assert it.estado == OK


def test_lo_que_cuelga_y_las_patas_no_son_columnas_de_esta_regla():
    d, _col, _ = _columna(cuelga=True)
    assert columna_rules(d) == []  # tracción: la sostiene lo de arriba
    d, _col, _ = _columna(rol="Pata (1)")
    assert columna_rules(d) == []  # la regla «pandeo de patas» es la suya
    assert detectar_columnas(d)["patas"] == 1


def test_el_detector_de_columnas_usa_el_criterio_de_la_regla():
    from apolo.services.puerta_hechos import _columnas

    d, _col, _ = _columna()
    assert _columnas(d) == {"columna": 1}
    d, _col, _ = _columna(base="perno")
    assert _columnas(d) == {"sin_evaluar": 1}
    d = Document("vacio")
    d.execute("create_box", {"name": "Poste de madera", "width": 50, "depth": 50, "height": 900,
                             "position": {"z": 450}})
    d.execute("ground", {"name": "g", "feature": d.commands[-1]["id"]})
    assert _columnas(d) == {"sin_evaluar": 1}  # rol «poste» sin sección: se justifica
