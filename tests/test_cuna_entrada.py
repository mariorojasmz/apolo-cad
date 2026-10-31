"""La cuña de ENTRADA con el sentido de marcha conocido (plan puerta-sin-sobrediseno, F2: D3–D4).

Puro (`library/seguridad/cuna_entrada.py`, `library/requisitos.py`) y sobre el testigo de la
plantilla (`services/calidad_cunas.py` + `calidad_sondas.cunas`): con sentido, UNA cuña por
tambor —donde la banda llega— y la otra sin peligro; sin sentido o `reversible`, las dos."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from apolo.library.requisitos import normalizar_requisitos, vector_sentido
from apolo.library.seguridad.cuna_entrada import borde_de_entrada, lazo_en_marcha, llegada

R, T, L = 50.0, 4.0, 1000.0
RM = R + T / 2  # radio de la línea media sobre un tambor


def _estadio(n_arco: int = 36) -> np.ndarray:
    """La línea media ANTIHORARIA de una faja de dos tambores (cola en u = 0, cabeza en u = L)
    en el plano (u, w), w arriba: arcos muestreados y tramos rectos de dos puntos."""
    pts = []
    for k in range(n_arco + 1):  # cabeza: de abajo a arriba por la derecha
        a = -math.pi / 2 + math.pi * k / n_arco
        pts.append((L + RM * math.cos(a), RM * math.sin(a)))
    for k in range(n_arco + 1):  # cola: de arriba a abajo por la izquierda
        a = math.pi / 2 + math.pi * k / n_arco
        pts.append((RM * math.cos(a), RM * math.sin(a)))
    return np.array(pts)


def test_lazo_en_marcha_sigue_el_ramal_superior():
    media = _estadio()
    hacia_u, _ = lazo_en_marcha(media, (1.0, 0.0), (0.0, 1.0))
    hacia_menos_u, _ = lazo_en_marcha(media, (-1.0, 0.0), (0.0, 1.0))
    assert np.allclose(hacia_menos_u, media)          # antihorario: el ramal de arriba va a −u
    assert np.allclose(hacia_u, media[::-1])


def test_la_banda_llega_arriba_a_la_cabeza_y_abajo_a_la_cola():
    """Transporte hacia +u: el ramal de carga llega a la cabeza por ARRIBA; el de retorno, a la
    cola por ABAJO (las cuñas de entrada de ISO 12100 en una faja de dos tambores)."""
    lazo, _ = lazo_en_marcha(_estadio(), (1.0, 0.0), (0.0, 1.0))
    cabeza = llegada(lazo, (L, 0.0), R, T)
    cola = llegada(lazo, (0.0, 0.0), R, T)
    # el contacto empieza un poco antes de la tangente (la tolerancia de contacto): del lado de
    # donde viene la banda, nunca del de salida
    assert cabeza[1] == pytest.approx(RM, abs=1.0) and L - 15.0 < cabeza[0] <= L
    assert cola[1] == pytest.approx(-RM, abs=1.0) and 0.0 <= cola[0] < 15.0
    # al revés, se invierten: la cola recibe el ramal de carga
    lazo_r, _ = lazo_en_marcha(_estadio(), (-1.0, 0.0), (0.0, 1.0))
    assert llegada(lazo_r, (0.0, 0.0), R, T)[1] == pytest.approx(RM, abs=1.0)


def test_un_desvio_por_fuera_se_mide_igual():
    """Un rodillo que la banda toca por FUERA (desvío de un drive central) también tiene su
    llegada: manda la banda, no el giro de la junta."""
    lazo, _ = lazo_en_marcha(_estadio(), (1.0, 0.0), (0.0, 1.0))
    r_d = 30.0
    centro = (L / 2, -RM - T / 2 - r_d)  # bajo el ramal de retorno, tocándolo
    q = llegada(lazo, centro, r_d, T, tol=1.0)
    # el retorno va hacia −u: llega al desvío desde el lado de la cabeza
    assert q is not None and q[1] == pytest.approx(-RM, abs=0.5) and L / 2 < q[0] < L / 2 + 15


def test_sin_decision_devuelve_el_motivo():
    media = _estadio()
    assert lazo_en_marcha(media, (1.0, 0.0), (0.0, 0.1))[0] is None   # tambores verticales
    lazo, motivo = lazo_en_marcha(media, (0.1, 0.0), (0.0, 1.0))
    assert lazo is None and "paralelo" in motivo
    lazo, motivo = lazo_en_marcha(media, (0.3, 0.95), (0.0, 1.0))  # 72° fuera del ramal
    assert lazo is None and "ramal superior" in motivo
    assert llegada(media, (5000.0, 0.0), R, T) is None              # no lo toca


def test_borde_de_entrada():
    assert borde_de_entrada([0.0, math.pi], 0.2) == 0
    assert borde_de_entrada([0.0, math.pi], math.pi - 0.1) == 1
    assert borde_de_entrada([-3.1, 3.1], math.pi) is None              # ambiguos
    assert borde_de_entrada([], 0.0) is None


# ------------------------------------------------------------------ el requisito
@pytest.mark.parametrize("entrada, guardado", [
    ([1, 0, 0], [1.0, 0.0, 0.0]), ([0, -2, 0], [0.0, -1.0, 0.0]), ("+X", [1.0, 0.0, 0.0]),
    ("-y", [0.0, -1.0, 0.0]), ("1, 0, 0", [1.0, 0.0, 0.0]), ("[0 0 1]", [0.0, 0.0, 1.0]),
])
def test_sentido_transporte_valido(entrada, guardado):
    assert vector_sentido(entrada) == guardado
    assert normalizar_requisitos({"sentido_transporte": entrada})["sentido_transporte"] == guardado


@pytest.mark.parametrize("malo", [[1, 0], [0, 0, 0], "abc", [True, 0, 0], ["a", 0, 0], 5,
                                  "--x", [1, 0, float("nan")]])
def test_sentido_transporte_mal_formado_se_rechaza_al_declarar(malo):
    from apolo.doc import Document
    from apolo.doc.errors import DocumentError

    with pytest.raises(DocumentError, match="sentido_transporte"):
        Document().set_requirements({"sentido_transporte": malo})


def test_reversible_es_si_o_no():
    assert normalizar_requisitos({"reversible": "sí"}) == {"reversible": True}
    assert normalizar_requisitos({"reversible": False}) == {"reversible": False}
    with pytest.raises(ValueError, match="reversible"):
        normalizar_requisitos({"reversible": "a veces"})


# ------------------------------------------------------------------ sobre el testigo de la plantilla
TESTIGO = Path(__file__).resolve().parent / "data" / "testigos" / "faja.apolo"


@pytest.fixture(scope="module")
def faja():
    from apolo.doc import Document
    from apolo.services.calidad_seguridad import analisis

    doc = Document.from_apolo_bytes(TESTIGO.read_bytes())
    # la v5 tal cual: el testigo trae el criterio 7 (la pila de sus pies, pie-nivelador F2), que
    # suma el rodillo de retorno del 6 con su cuña; aquí se miran las de los dos tambores
    (cmd,) = [c for c in doc.commands if c["type"] == "create_belt_conveyor"]
    doc.edit(cmd["id"], {**cmd["params"], "criterio": 5})
    return doc, analisis(doc)


def _puntos(doc, an) -> dict:
    """{tambor: (puntos, sentido)} como los arma `controles_seguridad`."""
    from apolo.services.calidad_cunas import llegadas
    from apolo.services.calidad_sondas import cunas

    dc, out = an["dc"], {}
    ent = llegadas(doc, an)
    for p in an["peligros"]:
        if p.get("cuna"):
            b, t = p["cuna"]["banda"], p["cuna"]["tambor"]
            pz = dc["piezas"]
            c = cunas(dc["solidos"][b], pz[b].caja, pz[t].caja, pz[t].redondo, ent[p["id"]]["hacia"])
            out[t.rsplit("_", 1)[-1]] = (c["puntos"], ent[p["id"]]["sentido"], pz[t].redondo)
    return out


def _con(doc, **req):
    doc.requirements = {k: v for k, v in {**(doc.requirements or {}), **req}.items()
                        if v is not None}


def test_la_plantilla_declara_su_sentido_y_queda_una_cuna_por_tambor(faja):
    doc, an = faja
    _con(doc, sentido_transporte=None, reversible=None)
    doc.escenarios = {}
    pts = _puntos(doc, an)
    assert set(pts) == {"motriz", "cola"}
    for nombre, (puntos, sentido, _red) in pts.items():
        assert len(puntos) == 3, nombre          # una cuña × tres estaciones a lo ancho
        assert sentido.startswith("cuña de entrada") and "plantilla create_belt_conveyor" in sentido
    # transporte hacia +X (el motriz está en +X): la cuña del motriz arriba y del lado de la cola;
    # la de la cola, abajo y del lado del motriz
    (pm, _s, rm), (pc, _s2, rc) = pts["motriz"], pts["cola"]
    assert all(p[2] > rm.centro[2] and p[0] < rm.centro[0] for p in pm)
    assert all(p[2] < rc.centro[2] and p[0] > rc.centro[0] for p in pc)


def test_sin_sentido_o_reversible_las_dos_cunas_como_antes(faja):
    from apolo.services.calidad_sondas import cunas

    doc, an = faja
    _con(doc, reversible=True)
    pts = _puntos(doc, an)
    _con(doc, reversible=None)
    una = _puntos(doc, an)
    dc = an["dc"]
    for nombre, (puntos, sentido, _r) in pts.items():
        assert len(puntos) == 6 and sentido.startswith("reversible")
        assert set(una[nombre][0]) < set(puntos)  # la de entrada es una de las dos de siempre
    # sin `hacia` (sin sentido conocido), `cunas` da las dos, como hasta la v6
    p = next(p for p in an["peligros"] if p.get("cuna"))
    b, t = p["cuna"]["banda"], p["cuna"]["tambor"]
    pz = dc["piezas"]
    c = cunas(dc["solidos"][b], pz[b].caja, pz[t].caja, pz[t].redondo)
    assert len(c["puntos"]) == 6 and c["cuna"] == "las dos"


def test_el_escenario_gana_al_requisito_y_el_requisito_a_la_plantilla(faja):
    doc, an = faja
    doc.escenarios = {}
    _con(doc, sentido_transporte=[-1.0, 0.0, 0.0], reversible=None)
    req = _puntos(doc, an)
    try:
        assert all(s.endswith("sentido: requisito sentido_transporte") for _p, s, _r in req.values())
        # al revés de la plantilla: la cuña del motriz pasa abajo
        pm, _s, rm = req["motriz"]
        assert all(p[2] < rm.centro[2] for p in pm)
        banda = next(p["cuna"]["banda"] for p in an["peligros"] if p.get("cuna"))
        doc.escenarios = {"marcha": {"escenario": {"mecanica": {"bandas": [
            {"pieza": banda, "junta_motriz": "x", "direccion_transporte": [1, 0, 0]}]}}}}
        esc = _puntos(doc, an)
        assert all(s.endswith("sentido: escenario «marcha»") for _p, s, _r in esc.values())
        assert all(p[2] > rm.centro[2] for p in esc["motriz"][0])
        # dos escenarios que se contradicen: desconocido, las dos cuñas
        doc.escenarios["otra"] = {"escenario": {"mecanica": {"bandas": [
            {"pieza": banda, "junta_motriz": "x", "direccion_transporte": [-1, 0, 0]}]}}}
        contradichos = _puntos(doc, an)
        assert all(len(p) == 6 and "distintos" in s for p, s, _r in contradichos.values())
    finally:
        doc.escenarios = {}
        _con(doc, sentido_transporte=None)


def test_una_banda_a_mano_sin_sentido_es_desconocida():
    from apolo.doc import Document
    from apolo.services.calidad_cunas import DESCONOCIDO, sentido_de_bandas

    doc = Document()
    fid = doc.execute("create_box", {"name": "Banda", "width": 1000, "depth": 400, "height": 4})
    assert sentido_de_bandas(doc, [fid]) == {fid: {"vector": None, "fuente": DESCONOCIDO}}
    doc.set_requirements({"sentido_transporte": "+X"})
    assert sentido_de_bandas(doc, [fid])[fid]["vector"] == [1.0, 0.0, 0.0]
