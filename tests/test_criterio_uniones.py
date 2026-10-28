"""`declare_structure` propone con criterio de taller (plan mcp-sin-friccion, D6).

Aceptación del contrato: sobre la piloto (proyecto 74, fixture sin geometría que extrae
`scripts/fixture_estructura.py`), la propuesta coincide con la estructura declarada a mano en
≥ 95 % de las uniones y no suelda ningún par desmontable; sobre la plantilla
`create_roller_conveyor` (generada aquí), coincide con las uniones que la propia plantilla
declara. Más las reglas una por una, la pieza que quedaría suelta y la respuesta corta.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.assembly.autodetect import detect_structure
from apolo.doc import Document
from apolo.services.criterio_uniones import criterio
from apolo.services.estructura import propuesta_estructura, roles_de, uniones_con_criterio
from apolo.services.estructura_corta import propuesta_corta
from apolo.services.roles import rol_union

FIXTURE = Path(__file__).parent / "data" / "estructura_piloto74.json"
#: Roles que hacen DESMONTABLE (o no soldable) un par: soldarlos es el error de la piloto.
DESMONTABLES = {"tuerca", "perno", "eje", "rodamiento", "chumacera", "flexible", "equipo"}


def _soldadura_desmontable(roles: dict, a: str, b: str) -> bool:
    ra, rb = roles.get(a, ""), roles.get(b, "")
    if ra in DESMONTABLES or rb in DESMONTABLES:
        return True
    if "guarda" in (ra, rb) and ra != rb:
        return True
    return (ra == "gira") != (rb == "gira")


def test_piloto_coincide_con_lo_declarado_a_mano_y_no_suelda_lo_desmontable():
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    maquinas = set(fx["grupos"])
    roles = {fid: rol_union(n, cat, ncat, maquinas)[0] for fid, (n, cat, ncat) in fx["piezas"].items()}
    cand = [{"a": a, "b": b, "direction": d} for a, b, d in fx["candidatos"]]
    uniones = criterio(roles, cand, fx["moviles"])
    tipo = {frozenset((u["a"], u["b"])): u["kind"] for u in uniones}

    esperado = {frozenset((a, b)): k for a, b, k in fx["esperado"]}
    aciertos = sum(1 for par, k in esperado.items() if tipo.get(par) == k)
    assert len(esperado) == 264
    assert aciertos / len(esperado) >= 0.95, f"{aciertos}/{len(esperado)}"
    # cero soldaduras en pares desmontables: los declarados como perno/contacto y los que la mano
    # no declaró pero unen tornillería, guardas, ejes, rodamientos, cadenas, motor o lo que gira
    malas = [par for par, k in tipo.items() if k == "soldadura" and (
        esperado.get(par, "soldadura") != "soldadura" or _soldadura_desmontable(roles, *sorted(par)))]
    assert malas == []
    # lo que se omite es lo que la mano no declaró (la tuerca ↔ larguero, la cadena ↔ el eje…)
    assert not [par for par, k in tipo.items() if k is None and par in esperado]


def _ids(doc, rol):
    return sorted(fid for fid, f in doc.scene.items() if f.name.split(" · ")[-1].startswith(rol))


def test_plantilla_de_rodillos_coincide_con_sus_propias_uniones():
    doc = Document("plantilla")
    doc.execute("create_roller_conveyor", {"largo": 1000})
    uniones = uniones_con_criterio(doc, detect_structure(doc.scene, joints=doc.joints))
    tipo = {frozenset((u["a"], u["b"])): u["kind"] for u in uniones}
    declarado = {frozenset((f["a"], f["b"])): f["kind"] for f in doc.fasteners.values()}
    detectados = {par: k for par, k in declarado.items() if par in tipo}
    aciertos = sum(1 for par, k in detectados.items() if tipo[par] == k)
    # medido con los pies de F5: 157 de 164 pares detectados; los 7 son decisiones de ESTA máquina
    # (cárter soldado a la base que corre con el motor, orejas con pernos en ranura, tapa soldada)
    assert aciertos / len(detectados) >= 0.95, f"{aciertos}/{len(detectados)}"
    roles = {k: r for k, (r, _) in roles_de(doc).items()}
    # la tuerca del pie nivelador va soldada a la placa de la pata (F5): no es desmontable
    soldadas = {k for k, (r, c) in roles_de(doc).items() if r == "tuerca" and "soldad" in c}
    assert not [par for par, k in tipo.items()
                if k == "soldadura" and not par & soldadas
                and _soldadura_desmontable(roles, *sorted(par))]
    # las reglas de D6, con las piezas de la plantilla
    eje, larguero, tuerca = _ids(doc, "Eje del rodillo")[0], _ids(doc, "Larguero (-Y)")[0], \
        _ids(doc, "Tuerca del eje (-Y)")[0]
    assert tipo[frozenset((eje, larguero))] == "perno"
    assert tipo[frozenset((eje, tuerca))] == "contacto"
    assert tipo.get(frozenset((tuerca, larguero)), None) is None
    motor = _ids(doc, "Motorreductor")[0]
    assert all(tipo[frozenset((motor, g))] is None
               for g in _ids(doc, "pared interior") if frozenset((motor, g)) in tipo)


@pytest.mark.parametrize("nombre, categoria, rol", [
    ("Eje del rodillo (3)", None, "eje"),
    ("Tubo del rodillo", "tubos_circulares", "gira"),
    ("Buje del piñón (brida soldada al tubo)", None, "gira"),
    ("Tapa con rodamiento 6201 (+Y)", None, "rodamiento"),
    ("Separador de guarda", None, "estructura"),
    ("Guarda de la transmisión · pared exterior", None, "guarda"),
    ("Bandeja de cadenas (tramo 1)", None, "guarda"),
    ("Base del motor", None, "estructura"),
    ("Pata (-Y, alimentación)", "tubos_estructurales", "estructura"),
    ("Motorreductor", "motorreductores", "equipo"),
    ("Tuerca del eje (-Y)", "tuercas", "tuerca"),
    ("Tornillería ménsula soporte motor", None, "perno"),
    ("Chumacera UCP207 (lado motriz)", None, "chumacera"),
    ("Faja de banda · Pata (1)", None, "estructura"),
    ("Transportador de rodillos · Oreja del portamotor (-Y)", None, ""),
    # una tapa es guarda sólo si cubre (F6): la de un rodillo gira con él, la de un tubo lo cierra
    ("Tapa del rodillo (alojamiento 6203)", None, "gira"),
    ("Tapa-cubo del tambor motriz", None, "gira"),
    ("Tapa (alojamiento 6203)", None, "rodamiento"),
    ("Tapa del tubo (-X)", None, "estructura"),
    ("Tapa de la bandeja", None, "guarda"),
    ("Tapa de la polea", None, "guarda"),
    ("Tapa", None, "guarda"),
])
def test_rol_por_el_sustantivo_que_encabeza_el_nombre(nombre, categoria, rol):
    maquinas = {"Transportador de rodillos", "Faja de banda"}
    assert rol_union(nombre, categoria, None, maquinas)[0] == rol


def test_la_tapa_del_rodillo_no_es_una_guarda_que_pida_pernos():
    """Una tapa ESTRUCTURAL de rodillo se tomaba por guarda y la puerta le exigía fijación
    desmontable con herramienta; la tapa de una bandeja sigue siendo guarda."""
    from apolo.library.seguridad.guardas import revisar_guardas
    from apolo.library.seguridad.modelo import Pieza

    caja = ((0.0, 0.0, 0.0), (10.0, 10.0, 10.0))
    nombres = {"t": "Tapa del rodillo (alojamiento 6203) (3)", "b": "Tapa de la bandeja",
               "m": "Larguero (-Y)"}
    piezas = {i: Pieza(i, n, rol_union(n)[0], None, None, caja, None, False)
              for i, n in nombres.items()}
    uniones = [{"a": "t", "b": "m", "kind": "contacto"}, {"a": "b", "b": "m", "kind": "contacto"}]
    r = revisar_guardas(piezas, uniones, set())
    assert [(g["nombre"], g["estado"]) for g in r["guardas"]] == [("Tapa de la bandeja", "FALLA")]


def test_dos_partes_de_la_misma_guarda_comparten_cuerpo():
    a = rol_union("Guarda de la transmisión · pared exterior")
    b = rol_union("Guarda de la transmisión · extremo (+X)")
    c = rol_union("Guarda de cadenas")
    assert a == b == ("guarda", "guarda de la transmisión") and c[1] != a[1]
    cand = [{"a": "p", "b": "x", "direction": "soporte"}, {"a": "p", "b": "g", "direction": "soporte"}]
    roles = {"p": "guarda", "x": "guarda", "g": "guarda"}
    cuerpos = {"p": a[1], "x": b[1], "g": c[1]}
    kinds = [u["kind"] for u in criterio(roles, cand, cuerpos=cuerpos)]
    assert kinds == ["soldadura", "perno"]


def test_el_separador_del_eje_va_en_contacto_aunque_lo_toque_la_tuerca():
    """Regla 4b (F6 de plantilla-rodillos-cadena): el separador entre la tuerca interior y el
    6201 es tope axial, no lo aprieta la tuerca; el eje con el larguero sigue con perno."""
    sep = rol_union("Transportador de rodillos · Separador del eje (-Y)", None, None,
                    {"Transportador de rodillos"})
    assert sep == ("estructura", "separador del eje (-y)")
    roles = {"e": "eje", "s": "estructura", "t": "tuerca", "l": "estructura"}
    cand = [{"a": "e", "b": "s", "direction": "mismo_nivel"},
            {"a": "e", "b": "l", "direction": "mismo_nivel"},
            {"a": "t", "b": "e", "direction": "mismo_nivel"},
            {"a": "t", "b": "s", "direction": "mismo_nivel"},
            {"a": "t", "b": "l", "direction": "mismo_nivel"}]
    cuerpos = {"s": sep[1], "l": "larguero (-y)"}
    kinds = [u["kind"] for u in criterio(roles, cand, cuerpos=cuerpos)]
    assert kinds[:2] == ["contacto", "perno"]
    # el «Separador de guarda» (soldado sobre el ala) no es un separador del eje
    guarda = {"s": rol_union("Separador de guarda")[1], "l": "larguero (-y)"}
    assert criterio(roles, cand[:1], cuerpos=guarda)[0]["kind"] == "perno"


def test_guarda_no_se_fija_a_lo_que_gira_ni_al_motor_y_se_atornilla_a_su_soporte():
    roles = {"g": "guarda", "m": "equipo", "p": "gira", "t": "estructura", "c": "flexible"}
    cand = [{"a": "g", "b": x, "direction": "mismo_nivel"} for x in ("m", "p", "t", "c")]
    assert [u["kind"] for u in criterio(roles, cand)] == [None, None, "perno", None]


def test_lo_que_gira_no_se_suelda_a_lo_fijo_pero_si_a_lo_que_gira_con_el():
    roles = {"buje": "gira", "tubo": "gira", "pinon": "gira", "eje": "eje", "larg": "estructura"}
    cand = [{"a": "buje", "b": "tubo", "direction": "mismo_nivel"},
            {"a": "buje", "b": "pinon", "direction": "mismo_nivel"},
            {"a": "tubo", "b": "eje", "direction": "mismo_nivel"},
            {"a": "tubo", "b": "larg", "direction": "mismo_nivel"}]
    u = criterio(roles, cand)
    assert [x["kind"] for x in u] == ["soldadura", "soldadura", "contacto", "contacto"]
    # sin tuerca que lo apriete, el eje puede ser vivo: a revisar; lo fijo, siempre
    assert [x["a_revisar"] for x in u] == [False, False, True, True]


def _caja(doc, nombre, x, y, z, w, d, h):
    return doc.execute("create_box", {"name": nombre, "width": w, "depth": d, "height": h,
                                      "position": {"x": x, "y": y, "z": z}})


@pytest.fixture()
def bastidor_con_ejes():
    """Dos largueros sobre cuatro patas, tres ejes que los atraviesan (un patrón) apretados con
    una tuerca por lado (patrones): la forma de la piloto, en cajas."""
    doc = Document("ejes-con-tuerca")
    largueros = {s: _caja(doc, f"Larguero ({s}Y)", 500, y, 500, 1000, 10, 60)
                 for s, y in (("-", -200), ("+", 200))}
    for s, y in (("-", -200), ("+", 200)):
        for x, donde in ((50, "alimentación"), (950, "motriz")):
            _caja(doc, f"Pata ({s}Y, {donde})", x, y, 235, 40, 10, 470)
    eje = doc.execute("create_cylinder", {"name": "Eje del rodillo", "radius": 6, "height": 440,
                                          "axis": "y", "position": {"x": 100, "y": 0, "z": 500}})
    tuercas = [_caja(doc, f"Tuerca del eje ({s}Y)", 100, y, 500, 18, 10, 18)
               for s, y in (("-", -210), ("+", 210))]
    for fid in [eje, *tuercas]:
        doc.execute("pattern_linear", {"feature": fid, "count": 3, "spacing": {"x": 300, "y": 0, "z": 0}})
    return doc, eje, largueros, tuercas


def test_eje_con_tuerca_va_con_perno_y_la_tuerca_es_parte_de_su_perno(bastidor_con_ejes):
    doc, eje, largueros, tuercas = bastidor_con_ejes
    prop = propuesta_estructura(doc)
    tipo = {frozenset((a["params"]["a"], a["params"]["b"])): a["params"]["kind"]
            for a in prop["acciones"] if a["type"] == "fasten"}
    assert tipo[frozenset((eje, largueros["-"]))] == "perno"
    assert tipo[frozenset((eje, tuercas[0]))] == "contacto"
    assert frozenset((tuercas[0], largueros["-"])) not in tipo
    assert {o["motivo"].split(": ", 1)[1].split(":")[0] for o in prop["omitidas"]} == {
        "la tuerca es parte de su perno"}
    patas = [k for par, k in tipo.items() if any(doc.scene[f].name.startswith("Pata") for f in par)]
    assert patas and set(patas) == {"soldadura"}  # la pata a tope bajo el larguero: marco
    assert not any(a.get("a_revisar") for a in prop["acciones"])


def test_la_respuesta_corta_declara_lo_mismo_en_pocas_ordenes(bastidor_con_ejes):
    """Aplicar cada `fasten` de `patrones` deja exactamente las uniones de `aplicar=true`."""
    doc, *_ = bastidor_con_ejes
    blob = doc.to_apolo_bytes()
    api.DOC = doc
    client = TestClient(api.app)
    corta = client.post("/api/assembly/declare", json={"aplicar": False, "resumen": True}).json()
    assert "acciones" not in corta and corta["n_a_revisar"] == 0 and corta["n_omitidas"] == 6
    lote = [{"type": "ground", "params": {"name": f"piso{i}", "feature": f}}
            for i, f in enumerate(corta["anclajes"])]
    for i, fila in enumerate(corta["patrones"]):
        assert "fasten" in fila, fila
        lote += [{"type": "fasten", "params": {"name": f"u{i}_{j}", "kind": fila["kind"], **f}}
                 for j, f in enumerate(fila["fasten"])]
    assert len(lote) < corta["n_fasteners"]
    assert client.post("/api/commands/batch", json={"actions": lote}).status_code == 200
    por_lote = {(frozenset((f["a"], f["b"])), f["kind"]) for f in doc.fasteners.values()}

    otro = Document.from_apolo_bytes(blob)
    api.DOC = otro
    r = client.post("/api/assembly/declare", json={"aplicar": True, "resumen": True})
    assert r.status_code == 200
    aplicada = r.json()
    assert "features" not in aplicada and aplicada["uniones_declaradas"] == corta["n_fasteners"]
    assert aplicada["por_tipo"] == corta["por_tipo"] and aplicada["fasteners"] == len(otro.fasteners)
    assert por_lote == {(frozenset((f["a"], f["b"])), f["kind"]) for f in otro.fasteners.values()}


def test_una_omitida_vuelve_si_sin_ella_la_pieza_queda_suelta():
    """La guarda que sólo toca el tambor: omitirla la dejaría cayendo → contacto a revisar."""
    doc = Document("guarda-suelta")
    _caja(doc, "Base", 0, 0, 10, 400, 200, 20)
    _caja(doc, "Tambor", 0, 0, 120, 200, 200, 200)
    _caja(doc, "Guarda del tambor", 0, 0, 230, 200, 200, 20)
    uniones = uniones_con_criterio(doc, detect_structure(doc.scene, joints=doc.joints))
    guarda = next(u for u in uniones if "Guarda" in u["motivo"])
    assert guarda["kind"] == "contacto" and guarda["a_revisar"]
    assert "queda suelta" in guarda["motivo"]


def test_propuesta_corta_recorta_y_cuenta():
    doc = Document("vacio")
    corta = propuesta_corta(doc, {"acciones": [], "omitidas": []})
    assert corta["n_fasteners"] == 0 and "patrones" not in corta and "seguir" in corta
