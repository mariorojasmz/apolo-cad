"""Puerta sin sobrediseño F1 — el tensor se mide en LAZO y los tensores de un lazo se SUMAN (plan
puerta-sin-sobrediseno D1, D2). Correr un tambor t alarga el lazo t·|Σ d·ê_k| sobre los ramales
libres de su tambor: 2·t en un tambor de cola con 180°, menos en un desvío. Lo requerido no cambia
(1 % del lazo + 20 mm)."""

import math

import numpy as np
import pytest

from apolo.doc import Document
from apolo.library.calidad.item import FALLA, OK
from apolo.library.calidad.tensor import carrera_requerida, controlar_tensores, evaluar_lazo
from apolo.library.calidad.tensor import validar_tensores
from apolo.library.ruta_faja_modelo import factor_lazo, ramales
from apolo.services import calidad_tensores_lazo
from apolo.services.calidad_tensores import lazos


def _faja(tensor: str = "ninguno") -> Document:
    doc = Document("faja")
    doc.execute("create_belt_conveyor", {"tensor": tensor})
    return doc


def _items(doc):
    return {i.id: i for i in controlar_tensores(lazos(doc))}


def _declarar_en_cola(doc, carrera: float, eje="x") -> None:
    doc.tensores = validar_tensores([{"piezas": ["c1_tambor_cola"], "carrera_mm": carrera,
                                      "eje": eje}])


# ── la geometría pura: los ramales del arco de contacto ────────────────────────────────


def _arco(alfa_deg: float, r: float = 50.0, largo: float = 400.0) -> np.ndarray:
    """Una línea que pasa por ENCIMA de un rodillo en (0, 0) abrazándolo `alfa_deg`, con sus dos
    ramales rectos hacia abajo, y vuelve lejos por debajo (no toca el rodillo)."""
    a = math.radians(alfa_deg) / 2.0
    angulos = [math.pi / 2 + a - k * 2 * a / 40 for k in range(41)]
    arco = [(r * math.cos(g), r * math.sin(g)) for g in angulos]
    t1, t2 = np.array(arco[0]), np.array(arco[-1])
    izq = t1 + largo * np.array([-math.cos(a), -math.sin(a)])
    der = t2 + largo * np.array([math.cos(a), -math.sin(a)])
    return np.array([izq, *arco, der, (der[0], -3000.0), (izq[0], -3000.0)])


@pytest.mark.parametrize("alfa", [180.0, 90.0, 30.0])
def test_factor_del_arco_es_2_sen_de_medio_abrazamiento(alfa):
    """Corriendo el rodillo por la bisectriz de sus ramales: |ê1 + ê2| = 2·sen(α/2)."""
    fac, abrazo, motivo = factor_lazo(_arco(alfa), (0.0, 0.0), (0.0, 1.0))
    assert motivo == ""
    assert fac == pytest.approx(2 * math.sin(math.radians(alfa) / 2), abs=0.01)
    assert abrazo == pytest.approx(alfa, abs=1.0)


def test_un_desvio_con_poco_abrazamiento_aporta_menos():
    poco, *_ = factor_lazo(_arco(30.0), (0.0, 0.0), (0.0, 1.0))
    cola, *_ = factor_lazo(_arco(180.0), (0.0, 0.0), (0.0, 1.0))
    assert poco < 0.6 < 1.9 < cola


def test_correr_perpendicular_a_los_ramales_no_alarga_el_lazo():
    fac, *_ = factor_lazo(_arco(180.0), (0.0, 0.0), (1.0, 0.0))
    assert fac == pytest.approx(0.0, abs=0.01)


def test_sin_arco_no_hay_ramales():
    circulo = np.array([(50 * math.cos(k / 20 * math.pi), 50 * math.sin(k / 20 * math.pi))
                        for k in range(40)])
    assert ramales(circulo, (0.0, 0.0)) is None  # toda la línea toca: no es un arco


# ── el control puro: la suma por tambor ────────────────────────────────────────────────


def _lazo(*tensores, largo=4738.0) -> dict:
    return {"id": "b", "nombre": "Banda", "tipo": "banda", "largo_mm": largo, "motivo": "",
            "tensores": list(tensores)}


def _t(tid, carrera, factor, tambor, tipo="take_up"):
    return {"tipo": tipo, "id": tid, "nombre": tid, "carrera_mm": carrera, "motivo": "",
            "pernos": [], "tambor": tambor, "factor_lazo": factor, "abrazamiento_deg": None,
            "factor_motivo": "" if factor is not None else "sin la sección del lazo"}


def test_tres_tensores_que_suman():
    """Ninguno alcanza solo (pide 67,4) y los tres juntos sí: se ajustan por separado."""
    tres = [_t("cabeza", 24, 2.0, 0), _t("desvio_a", 24, 1.0, 1), _t("desvio_b", 24, 1.0, 2)]
    e, txt, n = evaluar_lazo(_lazo(*tres))["carrera"]
    assert e == OK and n["lazo_recuperado_mm"] == pytest.approx(96.0)
    assert [a["lazo_mm"] for a in n["aportes"]] == [48.0, 24.0, 24.0]
    assert "cabeza: 24 × 2.00 = 48.0" in txt
    for t in tres:
        assert evaluar_lazo(_lazo(t))["carrera"][0] == FALLA


def test_dos_unidades_del_mismo_tambor_cuentan_una_vez_y_sobran():
    """Las dos UCT de un eje mueven el mismo tambor: un aporte, no dos. Si el lazo pasa sin
    ellas, se nombran (nota, no falla)."""
    tres = [_t("cabeza", 24, 2.0, 0), _t("desvio_a", 24, 1.0, 1), _t("desvio_b", 24, 1.0, 2)]
    ucts = [_t("uct_-y", 150, 2.0, 3, "catalogo"), _t("uct_+y", 150, 2.0, 3, "catalogo")]
    e, _txt, n = evaluar_lazo(_lazo(*tres, *ucts))["carrera"]
    assert e == OK and n["lazo_recuperado_mm"] == pytest.approx(396.0)
    assert n["aportes"][-1]["tensores"] == ["uct_-y", "uct_+y"]
    assert n["no_hacen_falta"][:2] == ["uct_-y", "uct_+y"]
    it = {i.id: i for i in controlar_tensores([_lazo(*tres, *ucts)])}
    assert it["tensor.carrera"].estado == OK
    assert "no hacen falta: uct_-y, uct_+y" in it["tensor.carrera"].detalle


def test_sin_seccion_factor_1_y_lo_dice():
    e, txt, n = evaluar_lazo(_lazo(_t("cola", 60, None, 0)))["carrera"]
    assert e == FALLA and n["lazo_recuperado_mm"] == pytest.approx(60.0)
    assert n["aportes"][0]["nota"] == "factor 1: sin la sección del lazo"


def test_la_cadena_no_suma_ni_lleva_factor():
    cad = {"id": "c", "nombre": "Cadena", "tipo": "cadena", "largo_mm": 2000.0, "motivo": "",
           "tensores": [_t("a", 20, None, None), _t("b", 20, None, None)]}
    e, txt, _n = evaluar_lazo(cad)["carrera"]
    assert e == FALLA and txt.startswith("carrera 20.0 mm; pide 30.0 mm")  # 3 %·L/2, el mejor


# ── sobre el modelo: la faja por defecto ───────────────────────────────────────────────


def test_tensor_de_cola_con_180_aprueba_con_la_mitad_de_la_carrera():
    """Hoy (v6) un tensor de cola de 0,6 × lo que pide fallaba; corriendo a lo largo de sus dos
    ramales recupera 2 × su carrera del lazo y aprueba."""
    doc = _faja()
    (lz,) = lazos(doc)
    pide = carrera_requerida("banda", lz["largo_mm"])
    _declarar_en_cola(doc, round(0.6 * pide, 1))
    (lz,) = lazos(doc)
    (t,) = lz["tensores"]
    assert t["factor_lazo"] == pytest.approx(2.0, abs=0.01)
    assert t["abrazamiento_deg"] == pytest.approx(180.0, abs=2.0)
    assert _items(doc)["tensor.carrera"].estado == OK
    _declarar_en_cola(doc, round(0.45 * pide, 1))  # 0,9 de lo que pide en lazo: falla
    assert _items(doc)["tensor.carrera"].estado == FALLA


def test_tensor_de_cola_que_corre_en_vertical_no_tensa():
    doc = _faja()
    _declarar_en_cola(doc, 200, eje="z")
    (lz,) = lazos(doc)
    assert lz["tensores"][0]["factor_lazo"] == pytest.approx(0.0, abs=0.01)
    assert _items(doc)["tensor.carrera"].estado == FALLA


def test_la_uct_de_catalogo_lee_su_carrera_de_la_caja():
    doc = _faja()
    doc.execute("insert_component", {"component": "UCT205-150",
                                     "position": {"x": -2000, "y": 420, "z": 845}})
    (lz,) = lazos(doc)
    (t,) = lz["tensores"]
    assert t["factor_lazo"] == pytest.approx(2.0, abs=0.01)


def test_sin_seccion_cerrada_el_factor_es_1(monkeypatch):
    monkeypatch.setattr(calidad_tensores_lazo, "linea_media_de_banda",
                        lambda *_a: (None, "la sección de la banda no es un lazo cerrado"))
    doc = _faja()
    _declarar_en_cola(doc, 150)
    (lz,) = lazos(doc)
    assert lz["tensores"][0]["factor_lazo"] is None
    c = _items(doc)["tensor.carrera"]
    assert c.estado == OK
    (ap,) = c.evidencia["aportes"]
    assert ap["factor"] == 1.0 and "no es un lazo cerrado" in ap["nota"]


def test_la_faja_por_defecto_sigue_ok():
    doc = _faja("UCT205-150")
    (lz,) = lazos(doc)
    assert len(lz["tensores"]) == 2  # las dos UCT del eje de cola
    assert len({t["tambor"] for t in lz["tensores"]}) == 1
    items = _items(doc)
    assert {i.estado for i in items.values()} <= {OK, "NO_APLICA"}
    (ap,) = items["tensor.carrera"].evidencia["aportes"]
    assert ap["factor"] == pytest.approx(2.0, abs=0.01) and len(ap["tensores"]) == 2
