"""La secuencia de MONTAJE desde el grafo de uniones (plan video-tienda-pulido, F1b · D8):
`services/montaje.py`, su uso en el manual de ensamblaje y el video en modo montaje
(`services/montaje_video.py`, `guion_video` con `modo`; las tandas del video las arma la
fábrica de publicaciones, fuera del núcleo).

La piloto (proyecto 74 de la base local) no está en la CI: una «piloto de uniones» la reproduce
con cajas y SU MISMO grafo —bastidor soldado y anclado, ejes atornillados a los largueros, tapas,
rodillo soldado (tubo + buje + piñón), tuercas, cadenas entre piñones, motor sobre su base y dos
guardas atornilladas por fuera—, con los grupos en el orden del log de la piloto. Lo medido sobre
la piloto real está en la bitácora del plan.
"""

from __future__ import annotations

import pytest

from apolo.doc.document import Document
from apolo.services.guion_video import MODO_MONTAJE, GuionError, guion, validar_guion
from apolo.services.montaje import hay_grafo, orden_conjuntos, pasos_manual, secuencia
from apolo.services.montaje_video import etapas_del_modo, etapas_montaje, pasos_montaje
from apolo.services.rotulos import MAX_TITULO_GENERADO

RODILLOS_X = (250, 500, 750)
Z = 715  # altura de los ejes


def _caja(d: Document, nombre: str, medidas, centro) -> str:
    w, dp, h = medidas
    x, y, z = centro
    return d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                    "position": {"x": x, "y": y, "z": z}})


def _uniones() -> Document:
    """La piloto en cajas: el mismo grafo de uniones, 3 rodillos en vez de 20."""
    d = Document("piloto de uniones")
    c: dict = {}
    c["lm"] = _caja(d, "Larguero (-Y)", (1000, 10, 60), (500, -200, 700))
    c["lp"] = _caja(d, "Larguero (+Y)", (1000, 10, 60), (500, 200, 700))
    c["ejes"], c["tapas"], c["tubos"], c["bujes"], c["pinones"], c["tuercas"] = ([] for _ in range(6))
    for i, x in enumerate(RODILLOS_X):
        n = f" ({i + 1})" if i else ""
        c["ejes"].append(_caja(d, f"Eje del rodillo{n}", (12, 420, 12), (x, 0, Z)))
        c["tapas"].append([_caja(d, f"Tapa con rodamiento ({s}Y){n}", (40, 10, 40), (x, y, Z))
                           for s, y in (("-", -150), ("+", 150))])
        c["tubos"].append(_caja(d, f"Tubo del rodillo{n}", (50, 300, 50), (x, 0, Z)))
        c["bujes"].append(_caja(d, f"Buje del piñón{n}", (30, 20, 30), (x, 160, Z)))
        c["pinones"].append(_caja(d, f"Piñón doble-simple{n}", (60, 8, 60), (x, 175, Z)))
        c["tuercas"].append([_caja(d, f"Tuerca del eje ({s}Y){n}", (18, 8, 18), (x, y, Z))
                             for s, y in (("-", -215), ("+", 215))])
    c["cadenas"] = [_caja(d, "Cadena rodillo a rodillo", (250, 8, 60), (x + 125, 175, Z))
                    for x in RODILLOS_X[:2]]
    c["patas"] = [_caja(d, f"Pata ({s}Y)", (40, 40, 660), (100, y, 340))
                  for s, y in (("-", -200), ("+", 200))]
    c["portamotor"] = _caja(d, "Travesaño portamotor", (40, 400, 40), (900, 0, 650))
    c["base"] = _caja(d, "Base del motor", (200, 200, 8), (900, 0, 526))
    c["motor"] = _caja(d, "Motorreductor", (120, 120, 80), (900, 0, 570))
    c["pmotriz"] = _caja(d, "Piñón motriz", (60, 8, 60), (900, 175, 570))
    c["cmotriz"] = _caja(d, "Cadena motriz", (210, 8, 205), (825, 175, 642))
    c["separador"] = _caja(d, "Separador de guarda", (20, 20, 20), (400, 200, 750))
    c["gcadenas"] = _caja(d, "Guarda de cadenas", (1000, 60, 4), (500, 175, 760))
    c["gtrans"] = _caja(d, "Guarda de la transmisión", (220, 4, 220), (850, 190, 600))
    c["placas"] = [_caja(d, f"Placa base ({s}Y)", (100, 100, 10), (100, y, 5))
                   for s, y in (("-", -200), ("+", 200))]

    def une(a, b, kind, **kw):
        d.execute("fasten", {"name": f"u{len(d.fasteners)}", "a": a, "b": b, "kind": kind, **kw})

    for pata, larguero, placa in zip(c["patas"], (c["lm"], c["lp"]), c["placas"]):
        une(pata, larguero, "soldadura")
        une(placa, pata, "soldadura")
        d.execute("ground", {"name": f"piso_{placa}", "feature": placa})
    for larguero in (c["lm"], c["lp"]):
        une(c["portamotor"], larguero, "soldadura")
    une(c["base"], c["portamotor"], "soldadura")
    une(c["separador"], c["lp"], "soldadura")
    for i in range(len(RODILLOS_X)):
        eje = c["ejes"][i]
        for larguero in (c["lm"], c["lp"]):
            une(eje, larguero, "perno", size="M12")
        for tapa in c["tapas"][i]:
            une(tapa, eje, "contacto")
            une(c["tubos"][i], tapa, "contacto")
        for tuerca in c["tuercas"][i]:
            une(tuerca, eje, "contacto")
        une(c["bujes"][i], c["tubos"][i], "soldadura")
        une(c["pinones"][i], c["bujes"][i], "soldadura")
    for j, cadena in enumerate(c["cadenas"]):
        une(cadena, c["pinones"][j], "contacto")
        une(cadena, c["pinones"][j + 1], "contacto")
    une(c["motor"], c["base"], "perno", size="M8")
    une(c["pmotriz"], c["motor"], "perno", size="M6")
    une(c["cmotriz"], c["pmotriz"], "contacto")
    une(c["cmotriz"], c["pinones"][-1], "contacto")
    une(c["gcadenas"], c["separador"], "perno", size="M6")
    une(c["gtrans"], c["portamotor"], "perno", size="M6")
    planos = lambda *xs: [x for v in xs for x in (v if isinstance(v, list) else [v])]  # noqa: E731
    rodillos = planos(c["ejes"], *c["tapas"], c["tubos"], c["bujes"], c["pinones"], *c["tuercas"])
    for grupo, miembros in (
            ("Bastidor", [c["lm"], c["lp"]]), ("Rodillos", rodillos), ("Cadenas", c["cadenas"]),
            ("Patas y travesaños", planos(c["patas"], c["portamotor"], c["placas"])),
            ("Motorreductor", [c["base"], c["motor"], c["pmotriz"], c["cmotriz"]]),
            ("Guardas", [c["separador"], c["gcadenas"], c["gtrans"]])):
        d.execute("create_group", {"name": grupo, "members": miembros})
    d.ids = c
    return d


@pytest.fixture(scope="module")
def piloto():
    d = _uniones()
    return d, secuencia(d)


def _posicion(pasos) -> dict[str, int]:
    return {f: i for i, p in enumerate(pasos) for f in p.ids}


# ------------------------------------------------------------------ la secuencia (D8)
def test_la_piloto_se_arma_como_en_el_taller(piloto):
    _, pasos = piloto
    assert [(p.titulo, p.union, len(p.ids)) for p in pasos] == [
        ("Conjunto soldado · Bastidor", "soldado", 9),
        ("Eje del rodillo", "perno", 3),
        ("Tapa con rodamiento", "contacto", 6),
        ("Conjunto soldado · Rodillos", "soldado", 9),
        ("Tuerca del eje", "contacto", 6),
        ("Cadena rodillo a rodillo", "contacto", 2),
        ("Motorreductor", "perno", 1),
        ("Piñón motriz", "perno", 1),
        ("Cadena motriz", "contacto", 1),
        ("Guardas", "perno", 2),
    ]


def test_lo_soldado_va_antes_que_lo_atornillado(piloto):
    d, pasos = piloto
    base = pasos[0]
    assert base.union == "soldado" and base.nivel == 0
    assert set(base.ids) == {d.ids[k] for k in ("lm", "lp", "portamotor", "base", "separador")} \
        | set(d.ids["patas"]) | set(d.ids["placas"])
    assert "Se ancla al piso." in base.texto and "8 uniones soldadas" in base.texto
    # cada conjunto soldado entra entero, en un solo paso: nunca una pieza suelta de él
    rodillos = pasos[3]
    for i in range(len(RODILLOS_X)):
        assert {d.ids["tubos"][i], d.ids["bujes"][i], d.ids["pinones"][i]} <= set(rodillos.ids)


def test_cada_pieza_entra_despues_de_aquella_a_la_que_se_fija(piloto):
    d, pasos = piloto
    pos = _posicion(pasos)
    for u in d.fasteners.values():
        if u["kind"] in ("soldadura", "pegado"):
            assert pos[u["a"]] == pos[u["b"]], u  # mismo conjunto, mismo paso
        else:
            assert pos[u["a"]] > pos[u["b"]], u


def test_las_guardas_van_al_final_y_las_tuercas_cierran(piloto):
    d, pasos = piloto
    assert set(pasos[-1].ids) == {d.ids["gcadenas"], d.ids["gtrans"]}
    pos = _posicion(pasos)
    tuercas = [t for par in d.ids["tuercas"] for t in par]
    assert min(pos[t] for t in tuercas) > max(pos[t] for t in d.ids["tubos"])  # rodillo, tuerca
    assert pasos[4].texto == "Se enrosca en «Eje del rodillo», «Eje del rodillo (2)» y «Eje del rodillo (3)»."


def test_el_texto_dice_como_se_une_con_las_uniones_declaradas(piloto):
    _, pasos = piloto
    assert pasos[1].texto == "Se atornilla (M12) a «Larguero (-Y)» y «Larguero (+Y)»."
    assert pasos[2].texto.startswith("Se apoya en ")
    assert pasos[6].texto == "Se atornilla (M8) a «Base del motor»."
    assert pasos[-1].texto == ("Se atornilla (M6) a «Separador de guarda» y "
                               "«Travesaño portamotor».")


def test_una_tapa_que_sostiene_algo_no_se_salta_su_soporte():
    """Regla 3 contra la 2: la tapa plana CUBRE al sensor (que queda dentro), pero el sensor se
    atornilla a ella: el soporte gana y la tapa entra antes."""
    d = Document("tapa con sensor")
    marco = _caja(d, "Marco", (400, 400, 40), (0, 0, 20))
    tapa = _caja(d, "Tapa de inspección", (300, 300, 4), (0, 0, 100))
    sensor = _caja(d, "Sensor", (40, 40, 40), (0, 0, 70))
    d.execute("ground", {"name": "g", "feature": marco})
    d.execute("fasten", {"name": "f1", "a": tapa, "b": marco, "kind": "perno"})
    d.execute("fasten", {"name": "f2", "a": sensor, "b": tapa, "kind": "perno"})
    assert [p.ids for p in secuencia(d)] == [(marco,), (tapa,), (sensor,)]


def test_la_tapa_suelta_cubre_y_va_despues():
    d = Document("tapa sin carga")
    marco = _caja(d, "Marco", (400, 400, 40), (0, 0, 20))
    tapa = _caja(d, "Tapa", (300, 300, 4), (0, 0, 100))
    poste = _caja(d, "Poste", (40, 40, 40), (0, 0, 60))
    sensor = _caja(d, "Sensor", (20, 20, 20), (0, 0, 90))
    d.execute("ground", {"name": "g", "feature": marco})
    for i, (a, b) in enumerate(((tapa, marco), (poste, marco), (sensor, poste))):
        d.execute("fasten", {"name": f"f{i}", "a": a, "b": b, "kind": "perno"})
    orden = [p.ids[0] for p in secuencia(d)]
    assert orden.index(tapa) > orden.index(sensor)  # la tapa va después de lo que tapa


def test_entre_vecinos_del_mismo_nivel_manda_el_sentido_de_la_union():
    d = Document("mismo nivel")
    base = _caja(d, "Base", (400, 400, 20), (0, 0, 10))
    soporte = _caja(d, "Soporte", (40, 40, 40), (0, 0, 40))  # creado antes, pero se fija a…
    mensula = _caja(d, "Ménsula", (40, 40, 40), (100, 0, 40))  # …la ménsula
    d.execute("ground", {"name": "g", "feature": base})
    for i, (a, b) in enumerate(((soporte, base), (mensula, base), (soporte, mensula))):
        d.execute("fasten", {"name": f"f{i}", "a": a, "b": b, "kind": "perno"})
    assert [p.ids[0] for p in secuencia(d)] == [base, mensula, soporte]


def test_sin_grafo_queda_el_orden_del_log_y_lo_dice():
    d = Document("cajas")
    ids = [_caja(d, f"Caja {i}", (100, 100, 100), (i * 200, 0, 50)) for i in range(3)]
    assert not hay_grafo(d)
    pasos = secuencia(d)
    assert [f for p in pasos for f in p.ids] == ids
    assert all(p.union == "suelto" and "revisa su sujeción" in p.texto for p in pasos)


def test_sin_anclajes_la_base_es_el_conjunto_mas_grande():
    d = Document("sin piso")
    a, b = _caja(d, "Ala", (100, 10, 10), (0, 0, 0)), _caja(d, "Alma", (10, 100, 10), (0, 0, 0))
    perno = _caja(d, "Placa", (50, 50, 5), (0, 0, 20))
    d.execute("fasten", {"name": "w", "a": a, "b": b, "kind": "soldadura"})
    d.execute("fasten", {"name": "p", "a": perno, "b": a, "kind": "perno"})
    orden, nivel, _, de = orden_conjuntos(d)
    assert nivel[de[a]] == 0 and nivel[de[perno]] == 1
    assert [p.union for p in secuencia(d)] == ["soldado", "perno"]


def test_las_ocultas_no_se_montan():
    d = _uniones()
    oculta = d.ids["gtrans"]
    d.scene[oculta].visible = False
    assert oculta not in {f for p in secuencia(d) for f in p.ids}


def test_una_parte_acotada_se_ordena_sola(piloto):
    d, _ = piloto
    parte = {f: d.scene[f] for f in (d.ids["ejes"][0], *d.ids["tuercas"][0], d.ids["lm"])}
    pasos = secuencia(d, parte)
    assert [p.ids for p in pasos][0] == (d.ids["lm"],)
    assert {f for p in pasos for f in p.ids} == set(parte)


# ------------------------------------------------------------------ el manual (D8)
def test_el_manual_usa_la_secuencia_de_montaje(piloto):
    from apolo.drawing import assembly_manual

    d, pasos = piloto
    etapas = pasos_manual(d)
    assert [e["label"] for e in etapas] == [p.titulo for p in pasos]
    assert etapas[1]["union"] == pasos[1].texto
    paginas = assembly_manual(d.scene, commands=d.commands, project_name="Piloto", size_px=120,
                              stages=etapas)
    assert len(paginas) == len(pasos) + 1
    texto = " ".join(lb.text for lb in paginas[2].labels)
    assert "Larguero (-Y)" in texto and "PASO 2 DE 10" in texto


def test_el_endpoint_del_manual_sigue_al_grafo(piloto, monkeypatch):
    from fastapi.testclient import TestClient

    import apolo.api.main as api
    import apolo.drawing as drawing

    d, pasos = piloto
    visto = {}

    def espia(scene, **kw):
        visto["stages"] = kw.get("stages")
        raise ValueError("solo miro")

    monkeypatch.setattr(drawing, "extraer_manual", espia)  # la fase bajo STATE_LOCK (manual-rapido)
    api.DOC = d
    r = TestClient(api.app).get("/api/assembly-manual.pdf")
    assert r.status_code == 400 and r.json()["detail"] == "solo miro"
    assert [s["label"] for s in visto["stages"]] == [p.titulo for p in pasos]
    api.DOC = Document("sin grafo")
    _caja(api.DOC, "Caja", (10, 10, 10), (0, 0, 0))
    TestClient(api.app).get("/api/assembly-manual.pdf")
    assert visto["stages"] is None  # sin estructura declarada: la heurística de siempre


# ------------------------------------------------------------------ el video en modo montaje
def test_las_etapas_de_montaje_traen_cada_pieza_una_vez_en_orden(piloto):
    d, pasos = piloto
    es = etapas_montaje(d, 75)
    tandas = [f for e in es for t in e.pasos for f in t]
    assert tandas == [f for p in pasos for f in p.ids]
    for e in es:
        assert len(e.titulo) <= MAX_TITULO_GENERADO
        assert 6.0 <= e.duracion_s <= 15.0
    assert es[0].titulo == "Bastidor" and "2 largueros" in es[0].texto


def test_los_pasos_de_video_numeran_la_secuencia(piloto):
    d, pasos = piloto
    vp = pasos_montaje(d, pasos)
    assert [p.k for p in vp] == list(range(1, len(pasos) + 1))
    assert vp[0].grupos == ("Bastidor",) and vp[-1].grupos == ("Guardas",)
    assert vp[1].agregados == pasos[1].ids and vp[1].quitados == ()


def test_el_guion_de_montaje_se_valida_contra_el_documento(piloto):
    d, _ = piloto
    g = guion(d, etapas_del_modo(d, 60, MODO_MONTAJE), modo=MODO_MONTAJE)
    assert g["modo"] == "montaje" and isinstance(g["etapas"][0]["pasos"][0], list)
    validar_guion(g, d)
    diseno = guion(d, etapas_del_modo(d, 60, "diseño"))
    assert "modo" not in diseno and isinstance(diseno["etapas"][0]["pasos"][0], int)
    validar_guion(diseno, d)

    def roto(cambio, patron):
        import copy

        h = copy.deepcopy(g)
        cambio(h)
        with pytest.raises(GuionError, match=patron):
            validar_guion(h, d)

    roto(lambda h: h.update(modo="armado"), "modo: 'armado' no existe")
    roto(lambda h: h["etapas"][0].update(pasos=[3, 7]), "lista no vacía de tandas")
    roto(lambda h: h["etapas"][1]["pasos"][0].append(h["etapas"][0]["pasos"][0][0]),
         "ya entraron antes")
    roto(lambda h: h["etapas"][0]["pasos"][0].append("c999"), r"piezas \['c999'\] no existen")
    with pytest.raises(ValueError, match="Modo de video desconocido"):
        etapas_del_modo(d, 60, "armado")
