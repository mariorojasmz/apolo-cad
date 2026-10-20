"""`create_chain` v2: fase automática y eslabones fijos (plan
`docs/plans/plantilla-rodillos-cadena.md`, D2, F1).

La piloto engranó a mano: giró 12° los piñones alternos (lazos 1:1 Z15) y 3° el piñón motriz
Z30, y fijó la distancia de la motriz en 159.034 porque 159.035 pasaba el exacto de 48 eslabones
(159.03493) y la cadena saltaba a 50. Con `fase: "auto"` la cadena gira el piñón libre lo justo;
con `eslabones` fija el largo y tolera el redondeo de la cota; `centros_cadena(…)` calcula el
exacto para colocar los piñones antes. Sin los params nuevos, todo como en v1.
"""

from __future__ import annotations

import math
import random

import pytest

from apolo.commands import CommandError
from apolo.commands.exec_transmision import medir_transmision
from apolo.commands.expressions import ExpressionError, eval_expression
from apolo.commands.models_transmision import CreateChainParams
from apolo.doc import Document, DocumentError
from apolo.library.checks import MIN_VOLUME_MM3
from apolo.library.transmision import (
    TOL_ESTIRADO_MM, centros_para_eslabones, eslabones_pares, estirado_lazo, giro_para_engranar,
)
from apolo.services.transmision_rules import chain_rules

ERRORES = (DocumentError, CommandError)
P = 12.7
Z15 = "PINON-ASA40-DS-Z15"


def _pinon(doc, ref=Z15, x=0.0, z=0.0, rot=(90, 0, 0)):
    return doc.execute("insert_component", {
        "component": ref, "position": {"x": x, "z": z}, "rotation": dict(zip("xyz", rot))})


def _medir(doc, cid):
    cmd = next(c for c in doc.commands if c["id"] == cid)
    p = CreateChainParams.model_validate(cmd["params"])
    t = medir_transmision(doc.scene, p)
    return t, estirado_lazo(t.paso, t.za, t.zb, t.centros, t.fase_a, t.fase_b, t.eslabones)


def _vol(s) -> float:
    return 0.0 if s is None else (s.volume if hasattr(s, "volume") else sum(x.volume for x in s))


# ------------------------------------------------------------------ la matemática (pura)
def test_giro_para_engranar_da_los_numeros_de_la_piloto():
    r, d = math.radians, math.degrees
    # 1:1 Z15 a 7.5 p con las dos fases iguales: medio diente
    assert d(giro_para_engranar(P, 15, 15, 95.25, 0.0, 0.0, 30, "b")) == pytest.approx(12.0)
    # 1:1 Z14 a 6 p: fase relativa cero
    assert d(giro_para_engranar(P, 14, 14, 76.2, 0.0, r(7), 26, "b")) == pytest.approx(-7.0)
    # la motriz Z30 → Z15 a 159.034 con el conducido como en la piloto: los 3° que se dieron a mano
    assert d(giro_para_engranar(P, 30, 15, 159.034, r(6), r(18), 48, "a")) == pytest.approx(3.0)
    # ya engranado: no se gira
    assert giro_para_engranar(P, 15, 15, 95.25, r(12), 0.0, 30, "a") == 0.0
    assert estirado_lazo(P, 15, 15, 95.25, 0.0, 0.0, 30) == pytest.approx(1.27, abs=1e-3)


@pytest.mark.parametrize("za,zb,eslabones", [(30, 15, 48), (15, 30, 48), (17, 30, 80),
                                             (15, 15, 30), (14, 14, 30), (19, 38, 70)])
def test_con_fases_al_azar_el_giro_siempre_engrana(za, zb, eslabones):
    c = centros_para_eslabones(P, za, zb, eslabones)
    azar = random.Random(f"{za}-{zb}")
    for _ in range(6):
        fa, fb = azar.uniform(0, 2 * math.pi), azar.uniform(0, 2 * math.pi)
        for gira in "ab":
            g = giro_para_engranar(P, za, zb, c, fa, fb, eslabones, gira)
            assert abs(g) <= math.pi / (za if gira == "a" else zb) + 1e-9  # menos de medio diente
            fa2, fb2 = (fa + g, fb) if gira == "a" else (fa, fb + g)
            assert estirado_lazo(P, za, zb, c, fa2, fb2, eslabones) <= TOL_ESTIRADO_MM


def test_expresion_centros_cadena():
    assert eval_expression("=centros_cadena(12.7, 30, 15, 48)", {}) == pytest.approx(159.03493, abs=1e-5)
    assert eval_expression("centros_cadena(p, 15, 15, 30)", {"p": 12.7}) == pytest.approx(95.25)
    for mal, msg in (("centros_cadena(12.7, 15, 15)", "4 argumentos"),
                     ("centros_cadena(12.7, 15.5, 15, 30)", "enteros"),
                     ("centros_cadena(12.7, 30, 15, 10)", "no alcanzan")):
        with pytest.raises(ExpressionError, match=msg):
            eval_expression(mal, {})


# ------------------------------------------------------------------ fase: auto
def test_sin_params_nuevos_la_cadena_es_la_de_v1():
    """Un log viejo (sin `fase` ni `eslabones`) no gira ningún piñón: el lazo 1:1 en fase igual
    sigue con su eslabón estirado, como siempre."""
    doc = Document("v1")
    a, b = _pinon(doc), _pinon(doc, x=95.25)
    antes = doc.scene[b].shape
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    assert doc.scene[b].shape is antes
    t, estirado = _medir(doc, cid)
    assert t.eslabones == 30 and estirado == pytest.approx(1.27, abs=1e-3)


def test_fase_auto_gira_medio_diente_el_pinon_b_y_no_choca():
    doc = Document("auto")
    a, b = _pinon(doc), _pinon(doc, x=95.25)
    fase_a = doc.scene[a].anchors["fase"]["origin"]
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "fase": "auto"})
    t, estirado = _medir(doc, cid)
    assert estirado <= TOL_ESTIRADO_MM
    assert math.degrees(abs(t.fase_b - t.fase_a)) % 24 == pytest.approx(12.0, abs=1e-4)
    assert doc.scene[a].anchors["fase"]["origin"] == fase_a  # A no se tocó
    for fid in (a, b):
        assert _vol(doc.scene[cid].shape & doc.scene[fid].shape) < MIN_VOLUME_MM3
    assert not any(r["regla"].startswith("cadena desfasada") for r in chain_rules(doc))


def test_fase_auto_con_pinon_volteado():
    doc = Document("volteado")
    a, b = _pinon(doc), _pinon(doc, x=95.25, rot=(-90, 0, 7))
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "fase": "auto"})
    assert _medir(doc, cid)[1] <= TOL_ESTIRADO_MM
    assert _vol(doc.scene[cid].shape & doc.scene[b].shape) < MIN_VOLUME_MM3


def test_fase_auto_ya_engranado_no_toca_los_pinones():
    doc = Document("engranado")
    a, b = _pinon(doc), _pinon(doc, x=95.25, rot=(90, 0, 12))
    shapes = (doc.scene[a].shape, doc.scene[b].shape)
    doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "fase": "auto"})
    assert (doc.scene[a].shape, doc.scene[b].shape) == shapes


@pytest.mark.parametrize("hacia_atras", [True, False])
def test_un_patron_de_pinones_iguales_sale_engranado_rodillo_a_rodillo(hacia_atras):
    """Lo que la piloto hizo con DOS familias de piñones (una girada 12°): con UNA sola, la
    cadena gira los alternos. Vale con A = el siguiente (como la piloto) o el anterior."""
    doc = Document("patron")
    pin = _pinon(doc)
    pat = doc.execute("pattern_linear", {"feature": pin, "count": 6, "spacing": {"x": 95.25}})
    pins = [pin] + [f"{pat}_{i}" for i in range(1, 6)]
    ids = doc.execute_many([{"type": "create_chain", "params": {
        "name": f"Lazo {i}", "fase": "auto", "hilera_a": 1 + i % 2, "hilera_b": 1 + i % 2,
        **({"pinon_a": pins[i + 1], "pinon_b": pins[i]} if hacia_atras
           else {"pinon_a": pins[i], "pinon_b": pins[i + 1]})}} for i in range(5)])
    for cid in ids:
        assert _medir(doc, cid)[1] <= TOL_ESTIRADO_MM, cid
    assert not any(r["regla"].startswith("cadena desfasada") for r in chain_rules(doc))
    # regenerar desde cero da lo mismo (el giro se recalcula en cada regenerate)
    claves = [doc.scene[cid].mesh_key for cid in ids]
    doc.regenerate()
    assert [doc.scene[cid].mesh_key for cid in ids] == claves


def test_fase_auto_con_los_dos_pinones_cargados_falla_con_el_giro():
    doc = Document("cargados")
    a, b = _pinon(doc), _pinon(doc, x=95.25)
    doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    with pytest.raises(ERRORES, match=r"ya cargan otras cadenas.*[+-]12\.000°"):
        doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "hilera_a": 2, "hilera_b": 2,
                                     "fase": "auto"})


# ------------------------------------------------------------------ eslabones fijos
def _motriz(doc, c):
    doc.execute("set_variable", {"name": "c_motriz", "expression": str(c)})
    a = _pinon(doc, "PINON-ASA40-1-Z30", z="=-c_motriz")
    b = _pinon(doc, "PINON-ASA40-1-Z15", rot=(90, 0, 18))
    return a, b


def test_eslabones_fijos_toleran_el_redondeo_de_la_cota():
    doc = Document("159.035")
    a, b = _motriz(doc, 159.035)
    sin = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    con = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "eslabones": 48,
                                       "name": "Cadena motriz"})
    assert doc.scene[sin].cut_length == pytest.approx(50 * P)  # el salto que vio la piloto
    assert doc.scene[con].cut_length == pytest.approx(48 * P)
    t, _ = _medir(doc, con)
    assert t.centros_exactos == pytest.approx(159.03493, abs=1e-5)


def test_motriz_de_la_piloto_con_centros_cadena_y_fase_auto():
    doc = Document("motriz")
    a, b = _motriz(doc, "=centros_cadena(12.7, 30, 15, 48)")
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "eslabones": 48,
                                       "fase": "auto", "potencia_kw": 0.37, "rpm_a": 50})
    t, estirado = _medir(doc, cid)
    assert t.eslabones == 48 and estirado <= TOL_ESTIRADO_MM
    assert t.centros == pytest.approx(t.centros_exactos, abs=1e-4)
    for fid in (a, b):
        assert _vol(doc.scene[cid].shape & doc.scene[fid].shape) < MIN_VOLUME_MM3


@pytest.mark.parametrize("eslabones,mensaje", [
    (46, r"centros exactos son \d+\.\d{4} mm.*centros_cadena\(12\.7, 30, 15, 46\).*eslabones = 48"),
    (47, "impar"),
    (2, "eslabones"),
])
def test_eslabones_que_no_alcanzan_se_rechazan_con_el_exacto(eslabones, mensaje):
    doc = Document("no alcanza")
    a, b = _motriz(doc, 159.0)
    with pytest.raises(ERRORES, match=mensaje):
        doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "eslabones": eslabones})


def test_eslabones_de_mas_dejan_flecha_y_la_regla_la_publica():
    doc = Document("flojo")
    a, b = _motriz(doc, 159.0)
    n, _ = eslabones_pares(P, 30, 15, 159.0)
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "eslabones": n + 4})
    assert doc.scene[cid].cut_length == pytest.approx((n + 4) * P)
    regla = next(r for r in chain_rules(doc) if r["regla"].startswith("transmisión por cadena"))
    assert "flecha" in regla["detalle"]
