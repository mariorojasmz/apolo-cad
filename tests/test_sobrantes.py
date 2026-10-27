"""La puerta no obliga a poner lo que no hace falta (plan puerta-sin-sobrediseno, F3 + D11):
avisos JUSTIFICADOS por escrito, la prueba de qué SOBRA y la primera corrida de la puerta.

Lo caro (sondas sobre un modelo con guardas) vive en `test_defectos_sembrados.py`; aquí, lo puro,
el metadato con su endpoint y la reconstrucción local del campo de la muñeca."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.calidad import justificadas as J
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.calidad.puerta import erc, semaforo_entrega
from apolo.library.calidad.sobrantes import sin_sobrantes
from apolo.library.calidad.vida_util import controlar_vida_util
from apolo.services import calidad_sobrantes as CS
from apolo.services.puerta_publicacion import firma

PORQUE = "la guía del producto pide este cierre contra el polvo del galpón"


# ------------------------------------------------------------------ el metadato
@pytest.mark.parametrize("valor, error", [
    ({"regla": "x"}, "lista"),
    ([{"porque": PORQUE}], "di qué se justifica"),
    ([{"regla": "lint", "porque": "no aplica"}], "al menos 20"),
    ([{"regla": "lint", "porque": PORQUE, "nota": "x"}], "no reconocida"),
    ([{"pieza": "", "porque": PORQUE}], "texto no vacío"),
])
def test_una_justificacion_mal_escrita_se_rechaza_con_la_correccion(valor, error):
    with pytest.raises(ValueError, match=error):
        J.validar_justificadas(valor)


def test_la_justificacion_cubre_su_regla_y_con_pieza_solo_esas_piezas():
    js = J.validar_justificadas([{"regla": "a", "porque": PORQUE},
                                 {"regla": "b", "pieza": "c1", "porque": PORQUE},
                                 {"regla": "b", "pieza": "c2", "porque": PORQUE},
                                 {"pieza": "c9", "porque": PORQUE}])
    assert J.del_aviso("a", ["c7"], js) and J.del_aviso("a", [], js)
    assert len(J.del_aviso("b", ["c1", "c2"], js)) == 2
    assert J.del_aviso("b", ["c1", "c3"], js) == []  # c3 sin justificar
    assert J.del_aviso("b", [], js) == []            # sin piezas pide la regla sola
    assert J.del_aviso("z", ["c1"], js) == []
    assert J.de_pieza("c9", js)["porque"] == PORQUE and J.de_pieza("c1", js) is None


# ------------------------------------------------------------------ D11: un aviso justificado pasa
def _entrega(veredicto, bloqueantes=(), avisos=()):
    return {"entrega": {"veredicto": veredicto, "bloqueantes": list(bloqueantes),
                        "avisos": list(avisos)}}


def test_el_semaforo_amarillo_justificado_pasa_y_el_rojo_nunca():
    aviso = {"regla": "lint pre-entrega", "detalle": "barreno sin perno", "piezas": ["c3"]}
    js = [{"regla": "lint pre-entrega", "porque": PORQUE}]
    assert semaforo_entrega(_entrega("AMARILLO", avisos=[aviso]))["estado"] == FALLA
    r = semaforo_entrega({**_entrega("AMARILLO", avisos=[aviso]), "justificadas": js})
    assert r["estado"] == OK and r["evidencia"]["justificados"][0]["justificacion"][0]["porque"]
    rojo = {"regla": "interferencias en diseño", "piezas": ["c1", "c2"]}
    r = semaforo_entrega({**_entrega("ROJO", [rojo], [aviso]),
                          "justificadas": js + [{"regla": "interferencias en diseño",
                                                 "porque": PORQUE}]})
    assert r["estado"] == FALLA and "1 bloqueante(s) y 0 aviso(s) (1 justificado(s))" in r["detalle"]


def test_el_erc_justifica_avisos_y_nunca_errores():
    reglas = [{"regla": "calentamiento", "estado": "aviso", "elementos": ["-Q1"]},
              {"regla": "protección del motor", "estado": "error", "elementos": ["-M1"]}]
    js = [{"regla": r["regla"], "porque": PORQUE} for r in reglas]
    r = erc({"electrico": reglas, "justificadas": js})
    assert r["estado"] == FALLA and [c["regla"] for c in r["evidencia"]["casos"]] == [
        "protección del motor"]
    r = erc({"electrico": reglas[:1], "justificadas": js})
    assert r["estado"] == OK and "1 aviso(s) justificado(s)" in r["detalle"]


def test_ingenieria_reglas_justifica_el_aviso_no_el_error():
    reglas = [{"regla": "holgura de servicio", "estado": "aviso", "detalle": "x"},
              {"regla": "asiento ISO 286", "estado": "error", "detalle": "k6 en inserto"}]
    js = [{"regla": r["regla"], "porque": PORQUE} for r in reglas]

    def estado(rs, j):
        return next(i for i in controlar_vida_util(rs, justificadas=j) if i.id == "vida.reglas")

    assert estado(reglas[:1], []).estado == FALLA
    it = estado(reglas[:1], js)
    assert it.estado == OK and it.evidencia["justificadas"][0]["regla"] == "holgura de servicio"
    assert estado(reglas, js).estado == FALLA


# ------------------------------------------------------------------ D5/D6: el ítem
def test_el_item_de_sobrantes_falla_salvo_lo_justificado():
    s = {"candidatas": 3, "sobrantes": [{"id": "c5", "nombre": "Guarda lateral", "masa_kg": 0.4,
                                         "origen": "agregada", "la_pide": "ninguna"}],
         "necesarias": [{"id": "c4", "nombre": "Guarda", "la_pide": "peligros",
                         "detalle": "una sonda recta llega sin ella"}], "ms": 10}
    r = sin_sobrantes({"sobrantes": s})
    assert r["estado"] == FALLA and r["piezas"] == ["c5"] and "Guarda lateral" in r["detalle"]
    assert r["evidencia"]["necesarias"][0]["la_pide"] == "peligros"
    r = sin_sobrantes({"sobrantes": s, "justificadas": [{"pieza": "c5", "porque": PORQUE}]})
    assert r["estado"] == OK and r["evidencia"]["justificadas"][0]["id"] == "c5"
    assert sin_sobrantes({"sobrantes": {"error": "no corrió"}})["estado"] == SIN_EVALUAR


# ------------------------------------------------------------------ D9: la primera corrida
def test_la_primera_corrida_se_anota_una_vez_y_viaja_en_el_apolo():
    d = Document("t")
    for k in range(3):
        d.execute("create_box", {"name": f"Caja {k}", "width": 10, "depth": 10, "height": 10})
    assert CS.marcar_primera_corrida(d) is True
    assert d.puerta_primera == {"ultimo_comando": 3, "comandos": 3}
    d.execute("create_box", {"name": "Agregada", "width": 10, "depth": 10, "height": 10})
    assert CS.marcar_primera_corrida(d) is False and d.puerta_primera["ultimo_comando"] == 3
    d2 = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert d2.puerta_primera == d.puerta_primera
    assert [CS.numero(x) for x in ("c369", "c40_c3", "v1", None)] == [369, 40, -1, -1]


def test_el_endpoint_guarda_las_justificaciones_y_la_firma_las_cuenta():
    d = Document("t")
    fid = d.execute("create_box", {"name": "Guarda", "width": 10, "depth": 10, "height": 10})
    api.DOC = d
    c = TestClient(api.app)
    antes = firma(d)
    r = c.put("/api/justificadas", json={"justificadas": [{"pieza": "c99", "porque": PORQUE}]})
    assert r.status_code == 400 and "c99" in r.json()["detail"]
    r = c.put("/api/justificadas", json={"justificadas": [{"regla": "x", "porque": "corto"}]})
    assert r.status_code == 400 and "20 caracteres" in r.json()["detail"]
    r = c.put("/api/justificadas", json={"justificadas": [{"pieza": fid, "porque": PORQUE}]})
    assert r.status_code == 200 and c.get("/api/justificadas").json()["justificadas"][0]["pieza"] == fid
    assert firma(d) != antes
    assert Document.from_apolo_bytes(d.to_apolo_bytes()).justificadas == d.justificadas
    c.put("/api/justificadas", json={"justificadas": []})
    assert firma(d) == antes  # sin justificaciones, la firma de siempre


# ------------------------------------------------------------------ D7: el campo, por zonas
def test_el_campo_rehecho_por_zona_es_el_mismo_que_entero():
    """`libre_sin` recalcula sólo la zona de la pieza quitada: debe dar los MISMOS voxeles libres
    que rehacer el campo entero sin ella (lo que no está a r_brazo de la zona no cambia)."""
    from apolo.library.seguridad.alcance import CampoAlcance

    rng = np.random.default_rng(7)
    pared = np.c_[rng.uniform(0, 400, 4000), np.full(4000, 100.0), rng.uniform(0, 300, 4000)]
    tapa = np.c_[rng.uniform(150, 250, 800), rng.uniform(40, 60, 800), rng.uniform(80, 180, 800)]
    caja = ((0.0, 0.0, 0.0), (400.0, 200.0, 300.0))
    con = CampoAlcance(np.r_[pared, tapa], caja, 0.0)
    sin = CampoAlcance(pared, caja, 0.0)
    assert con.misma_grilla(caja, 0.0) and not con.misma_grilla(((0, 0, 0), (401, 200, 300)), 0.0)
    cerca = pared[(pared[:, 0] > 50) & (pared[:, 0] < 350)]
    libre = con.libre_sin(cerca, tapa.min(axis=0), tapa.max(axis=0))
    assert (libre != con.libre).any() and (libre == sin.libre).all()
    rehecho = CampoAlcance(None, caja, 0.0, libre=libre)
    assert np.array_equal(rehecho._prof, sin._prof)
