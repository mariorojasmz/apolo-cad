"""Puerta de publicación — F3 en el registro (plan puerta-de-publicacion, D4, D5, D8, D14): la fuente
«seguridad» lleva sus seis ítems a los tres generales, descarta `seguridad.electrico` (repite
`riesgos.electrico`), corre UNA vez por puerta, los detectores de los hechos usan su mismo
criterio y el resultado trae la tabla de riesgos (que la fábrica de publicaciones, fuera del
núcleo, lleva a `calidad.json` y `calidad.md`)."""

from __future__ import annotations

import pytest
from test_calidad_seguridad import _transmision
from test_puerta_publicacion import _puerta

from apolo.doc import Document
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import REGISTRO, evaluar
from apolo.services import calidad_seguridad as cs


def _it(iid, estado, detalle="", **ev):
    return {"id": iid, "titulo": iid, "estado": estado, "modo_de_falla": "m", "norma": "n",
            "evidencia": ev, "piezas": [], "detalle": detalle}


def _por_id(r) -> dict:
    return {i["id"]: i for i in r["items"]}


# ------------------------------------------------------------------ el registro con F3
def test_el_registro_publica_f3_en_sus_tres_generales_y_su_tabla_de_riesgos():
    seguridad = {
        "items": [_it("seguridad.resguardo_iso13857", FALLA, "cuña de cola: 11 sondas alcanzan"),
                  _it("seguridad.guarda_con_herramienta", OK, "2 guardas atornilladas"),
                  _it("reparabilidad.desgaste_sin_soldadura", OK),
                  _it("reparabilidad.desgaste_desmontable", OK),
                  _it("reparabilidad.banda_montable", NO_APLICA, "sin banda"),
                  _it("reparabilidad.lubricacion", FALLA, "un control nuevo"),
                  _it("seguridad.ruido", OK, "un control nuevo sin general")],
        "riesgos": [{"peligro": "Transmisión", "tipo": "atrapamiento", "medida": "ninguna",
                     "verificacion": "seguridad.resguardo_iso13857", "estado": FALLA},
                    {"peligro": "Contacto eléctrico", "tipo": "eléctrico",
                     "medida": "tablero verificado por el ERC",
                     "verificacion": "riesgos.electrico"}]}
    hechos = {"carril": True, "elementos": {
        "partes_moviles": {"transmision": 1}, "resguardos": {"guarda": 2},
        "consumibles": {"cadena": 1, "piñón": 2}}}
    r = evaluar({"hechos": hechos, "fuentes": {"seguridad": seguridad},
                 "electrico": [{"regla": "x", "estado": "aviso", "detalle": "falta tierra"}]})
    it = _por_id(r)
    pm = it["riesgos.partes_moviles"]
    assert pm["estado"] == FALLA and pm["familia"] == "seguridad"
    assert pm["evidencia"]["origen"] == "seguridad.resguardo_iso13857"
    assert pm["evidencia"]["elementos"] == {"transmision": 1}
    g = it["riesgos.resguardos_desmontables_con_herramienta"]
    assert g["estado"] == OK and g["evidencia"]["origen"] == "seguridad.guarda_con_herramienta"
    c = it["consumibles.reemplazables"]
    assert c["familia"] == "montaje" and c["estado"] == FALLA
    # un ítem de reparabilidad NUEVO lo recoge el prefijo (nunca se pierde); sin banda, se cumple
    assert set(c["evidencia"]["origen"]) == {
        "reparabilidad.desgaste_sin_soldadura", "reparabilidad.desgaste_desmontable",
        "reparabilidad.banda_montable", "reparabilidad.lubricacion"}
    assert c["evidencia"]["origen"]["reparabilidad.banda_montable"]["estado"] == OK
    assert it["seguridad.ruido"]["estado"] == OK  # sin general: sale tal cual
    assert "seguridad.resguardo_iso13857" not in it
    # la tabla: verificada por el ítem GENERAL; la fila sin estado toma el del ítem que la verifica
    transm, elec = r["riesgos"]
    assert transm["verificacion"] == "riesgos.partes_moviles" and transm["estado"] == FALLA
    assert elec["verificacion"] == "riesgos.electrico"
    assert elec["estado"] == it["riesgos.electrico"]["estado"] == FALLA  # el aviso bloquea


def test_una_fuente_sin_tabla_da_riesgos_vacio_y_f3_que_no_corre_bloquea():
    r = evaluar({"hechos": {}, "fuentes": {"seguridad": {"error": "RuntimeError: OCCT"}}})
    assert r["riesgos"] == [] and r["version_registro"] == "14"
    malo = _por_id(r)["seguridad.fuente"]
    assert malo["estado"] == SIN_EVALUAR and "OCCT" in malo["detalle"]


# ------------------------------------------------------------------ el adaptador
def test_el_adaptador_descarta_seguridad_electrico_y_deja_su_fila(monkeypatch):
    """`seguridad.electrico` repite la Entrada `riesgos.electrico` (el mismo ERC): el adaptador no
    lo publica ni corre el ERC otra vez; la fila eléctrica de la tabla se queda, sin estado."""
    from apolo.services import electrico

    def sin_erc(_doc):
        raise AssertionError("el adaptador no debe correr el ERC: ya lo corre la Entrada")

    monkeypatch.setattr(electrico, "tiene_carril", lambda _doc: True)
    monkeypatch.setattr(electrico, "chequeo", sin_erc)
    d, _ = _transmision("cerrada")
    r = cs.items_seguridad(d)
    ids = [i["id"] for i in r["items"]]
    assert cs.ID_ELECTRICO not in ids and len(ids) == 5
    fila = r["riesgos"][-1]
    assert fila["tipo"] == "eléctrico" and fila["verificacion"] == "riesgos.electrico"
    assert "estado" not in fila


# ------------------------------------------------------------------ la puerta entera
@pytest.fixture(scope="module")
def cadena_expuesta():
    d, piezas = _transmision(None)
    return d, piezas, _puerta(d)


def test_una_cadena_expuesta_falla_en_riesgos_partes_moviles(cadena_expuesta):
    _d, (a, b, c), r = cadena_expuesta
    it = _por_id(r)
    pm = it["riesgos.partes_moviles"]
    assert pm["estado"] == FALLA and {a, b, c} <= set(pm["piezas"])
    assert pm["evidencia"]["elementos"] == {"transmision": 1}
    cons = it["consumibles.reemplazables"]["evidencia"]
    assert cons["elementos"] == {"cadena": 1, "piñón": 2}
    # sin banda, su control no tiene nada que juzgar: se cumple, con el motivo de su evidencia
    assert cons["origen"]["reparabilidad.banda_montable"] == {
        "estado": OK, "detalle": "nada que verificar (sin banda)",
        "evidencia": {"motivo": "sin banda"}}
    # sin guardas: el ítem de guardas no aplica, con el porqué del detector
    g = it["riesgos.resguardos_desmontables_con_herramienta"]
    assert g["estado"] == NO_APLICA and g["detalle"] == "sin resguardos"
    assert not {"seguridad.electrico", "seguridad.resguardo_iso13857"} & set(it)
    assert "fuentes.seguridad" in r["tiempos_s"]


def test_una_pieza_estatica_no_tiene_ninguno_de_los_tres():
    d = Document("ménsula")
    m = d.execute("create_box", {"name": "Ménsula", "width": 120, "depth": 80, "height": 10,
                                 "position": {"x": 0, "y": 0, "z": 5}})
    d.execute("ground", {"name": "g0", "feature": m})
    r = _puerta(d)
    it = _por_id(r)
    assert {k: (it[k]["estado"], it[k]["detalle"]) for k in (
        "riesgos.partes_moviles", "riesgos.resguardos_desmontables_con_herramienta",
        "consumibles.reemplazables")} == {
        "riesgos.partes_moviles": (NO_APLICA, "pieza o estructura sin partes móviles"),
        "riesgos.resguardos_desmontables_con_herramienta": (NO_APLICA, "sin resguardos"),
        "consumibles.reemplazables": (NO_APLICA, "sin piezas de desgaste")}
    assert r["riesgos"] == [] and r["aprobado"] is True


def test_f3_corre_una_vez_y_la_deteccion_se_comparte(monkeypatch):
    llamadas = {"controles_f3": 0, "_analizar": 0, "datos_calidad": 0}
    for nombre in llamadas:
        real = getattr(cs, nombre)

        def contar(*a, _real=real, _n=nombre, **k):
            llamadas[_n] += 1
            return _real(*a, **k)

        monkeypatch.setattr(cs, nombre, contar)
    d, _ = _transmision("abierta_abajo")
    r = _puerta(d)
    assert llamadas == {"controles_f3": 1, "_analizar": 1, "datos_calidad": 1}
    assert _por_id(r)["riesgos.partes_moviles"]["estado"] == FALLA  # abierta por abajo


def test_f3_es_una_fuente_del_registro():
    (f,) = [e for e in REGISTRO if getattr(e, "clave", None) == "seguridad"]
    assert f.servicio == "apolo.services.calidad_seguridad:items_seguridad"
