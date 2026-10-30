"""Puerta de publicación F1 — el núcleo (plan puerta-de-publicacion, D1, D2, D8, D11 y D13b): el
registro y su agregador (los cuatro estados, NO_APLICA sólo por `aplica_si`), los controles de lo
que ya existe, los choques DENTRO de un super-comando, la gravedad obligatoria, la firma del modelo,
el endpoint y la tool MCP. Lo de la fábrica de publicaciones (la ficha `calidad.md`, la firma
leída del `.apolo` y la fábrica que para en «calidad») se prueba con ella, fuera del núcleo."""

from __future__ import annotations


import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.calidad import puerta as p
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR, Item
from apolo.library.calidad.registro import (
    FAMILIAS,
    REGISTRO,
    Entrada,
    Fuente,
    General,
    evaluar,
    hay,
    hecho,
    siempre,
)
from apolo.services import puerta_publicacion as pp


# ------------------------------------------------------------------ registro y agregador
def _r(estado, detalle="", **ev):
    return lambda _ins: {"estado": estado, "detalle": detalle, "evidencia": ev, "piezas": ["c1"]}


def _entrada(iid, evaluar_, aplica=siempre, familia="montaje"):
    return Entrada(iid, f"título {iid}", "modo", "norma", familia, aplica, evaluar_)


def test_agregador_los_cuatro_estados_y_aprobado():
    def revienta(_ins):
        raise ValueError("sin datos")

    reg = (_entrada("a.ok", _r(OK, mantenimiento=["engrasa la cadena"])),
           _entrada("a.falla", _r(FALLA, "no cumple"), familia="estructura"),
           _entrada("a.no_aplica", _r(FALLA), hecho("motores", "sin motorreductor")),
           _entrada("a.dice_no_aplica", _r(NO_APLICA, "no vi nada")),
           _entrada("a.revienta", revienta))
    r = evaluar({"hechos": {"motores": 0}, "firma": "f", "tiempos": {"total": 1.0}}, reg)
    est = {i["id"]: i for i in r["items"]}
    assert est["a.ok"]["estado"] == OK and est["a.falla"]["estado"] == FALLA
    # NO_APLICA sólo por aplica_si, con su porqué, y sin correr el control
    assert est["a.no_aplica"]["estado"] == NO_APLICA
    assert est["a.no_aplica"]["detalle"] == "sin motorreductor"
    # un control que dice «no aplica» cuando su entrada dice que sí: SIN_EVALUAR (D1)
    assert est["a.dice_no_aplica"]["estado"] == SIN_EVALUAR
    assert "no vi nada" in est["a.dice_no_aplica"]["detalle"]
    assert est["a.revienta"]["estado"] == SIN_EVALUAR and "sin datos" in est["a.revienta"]["detalle"]
    assert r["aprobado"] is False and r["firma"] == "f" and r["version_registro"] == "31"
    assert r["conteos"] == {OK: 1, FALLA: 1, SIN_EVALUAR: 2, NO_APLICA: 1}
    assert r["por_familia"]["estructura"] == {"estado": FALLA, OK: 0, FALLA: 1, SIN_EVALUAR: 0,
                                              NO_APLICA: 0}
    assert r["por_familia"]["montaje"]["estado"] == SIN_EVALUAR
    assert r["mantenimiento"] == ["engrasa la cadena"] and r["tiempos_s"] == {"total": 1.0}
    assert {i["familia"] for i in r["items"]} <= set(FAMILIAS)


def test_aprobado_exige_todo_lo_aplicable_ok_y_sin_evaluar_bloquea():
    todo_ok = (_entrada("x", _r(OK)), _entrada("y", _r(FALLA), hecho("carril", "sin tablero")))
    assert evaluar({"hechos": {}}, todo_ok)["aprobado"] is True
    assert evaluar({"hechos": {}}, (_entrada("z", _r(SIN_EVALUAR)),))["aprobado"] is False
    # una puerta vacía (nada aplicable) no es una puerta aprobada
    assert evaluar({"hechos": {}}, (_entrada("y", _r(OK), hecho("carril", "no")),))["aprobado"] \
        is False


def test_fuente_lleva_sus_ids_a_items_generales():
    """D14: los ids del módulo (F2) no se reescriben; el registro los publica como ítems
    GENERALES, con los elementos que evaluó. Varios orígenes → el peor manda."""
    f = Fuente("f2", "x:y", {
        "elementos_rodantes.l10": General("Rodantes L10", "función", ("vida.l10",),
                                          hay("elementos_rodantes", "sin rodamientos"),
                                          "elementos_rodantes"),
        "transmision_flexible.tension": General(
            "Tensión", "función", ("tensor.reconocido", "tensor.agarre"),
            hay("transmisiones_flexibles", "la máquina no tiene transmisiones flexibles"),
            "transmisiones_flexibles", vacio_ok=("tensor.agarre",)),
        "transmision.capacidad": General("Capacidad", "función", ("vida.cadena",),
                                         hay("transmisiones", "sin transmisiones")),
        "union.falta": General("Falta", "montaje", ("agarre.nada",)),
        "ingenieria.reglas": General("Resto", "función", ("vida.reglas",),
                                     vacio_ok=("vida.reglas",))})
    items = [Item("vida.l10", "L10", NO_APLICA, "m", "ISO 281", detalle="ninguna regla"),
             Item("vida.cadena", "Cadena", FALLA, "m", "n", detalle="FS 1,09").to_dict(),
             Item("tensor.reconocido", "R", OK, "m", "n", detalle="take-up"),
             Item("tensor.agarre", "A", NO_APLICA, "m", "n", detalle="sin perno tensor"),
             Item("vida.reglas", "Resto", NO_APLICA, "m", "n", detalle="no hay más reglas"),
             Item("tensor.nuevo", "Nuevo control", FALLA, "m", "n", detalle="sin general")]
    hechos = {"elementos": {"transmisiones_flexibles": {"banda": 1}}}
    r = evaluar({"hechos": hechos, "fuentes": {"f2": items}}, (f,))
    est = {i["id"]: i for i in r["items"]}
    assert est["elementos_rodantes.l10"]["estado"] == NO_APLICA
    assert est["elementos_rodantes.l10"]["detalle"] == "sin rodamientos"
    t = est["transmision_flexible.tension"]
    assert t["estado"] == OK and t["evidencia"]["elementos"] == {"banda": 1}
    assert set(t["evidencia"]["origen"]) == {"tensor.reconocido", "tensor.agarre"}
    # los hechos dicen «sin transmisiones» pero el control SÍ midió una: gana lo medido
    assert est["transmision.capacidad"]["estado"] == FALLA
    assert est["transmision.capacidad"]["evidencia"]["origen"] == "vida.cadena"
    assert est["union.falta"]["estado"] == SIN_EVALUAR and "no produjo" in est["union.falta"]["detalle"]
    assert est["ingenieria.reglas"]["estado"] == OK
    assert est["tensor.nuevo"]["estado"] == FALLA  # sin general: sale tal cual, nunca se pierde
    # con rodamientos, el «ninguna regla» del control no puede quedar como no aplica
    hechos["elementos"]["elementos_rodantes"] = {"rodamiento": 2}
    r = evaluar({"hechos": hechos, "fuentes": {"f2": items}}, (f,))
    assert {i["id"]: i["estado"] for i in r["items"]}["elementos_rodantes.l10"] == SIN_EVALUAR
    # una fuente que no corre: SIN_EVALUAR con el error
    r = evaluar({"hechos": {}, "fuentes": {"f2": {"error": "ImportError: no está"}}}, (f,))
    (malo,) = r["items"]
    assert malo["id"] == "f2.fuente" and malo["estado"] == SIN_EVALUAR
    assert "ImportError" in malo["detalle"]


def test_el_registro_es_general_y_coherente():
    from apolo.library.calidad.registro import MAPA_SEGURIDAD, _ids_de_f2

    ids = [e.id for e in REGISTRO if isinstance(e, Entrada)]
    mecanica, seguridad = [e for e in REGISTRO if isinstance(e, Fuente)]
    assert seguridad.mapa is MAPA_SEGURIDAD  # F3 entra por su fuente
    generales = ids + list(mecanica.mapa) + list(MAPA_SEGURIDAD)
    assert len(generales) == len(set(generales))
    assert all(e.familia in FAMILIAS for e in REGISTRO if isinstance(e, Entrada))
    assert all(g.familia in FAMILIAS for g in [*mecanica.mapa.values(), *MAPA_SEGURIDAD.values()])
    # todo id de F2 lo recoge un ítem general (ninguno sale con el nombre del mecanismo)
    recogidos = {o for g in mecanica.mapa.values() for o in g.origen}
    assert set(_ids_de_f2()) == recogidos
    # los nombres son de modos de falla generales, no de un transportador
    assert not [i for i in generales if any(x in i for x in ("tensor", "banda", "faja", "vida."))]
    assert {"transmision_flexible.tension", "union.agarre", "union.largo_comercial",
            "publicado.sustitutos_fieles", "diseno.soluciones_por_funcion", "fabricabilidad",
            "riesgos.electrico", "riesgos.partes_moviles", "consumibles.reemplazables"} <= set(
        generales)


# ------------------------------------------------------------------ controles de lo existente
def test_gravedad_sin_simular_es_sin_evaluar_nunca_verde():
    assert p.gravedad({"gravedad": {"resultado": None, "motivo": "MuJoCo no instalado"}})[
        "estado"] == SIN_EVALUAR
    caen = p.gravedad({"gravedad": {"resultado": {"fell": [
        {"id": "c3", "nombre": "Tapa", "caida_mm": 120.0}], "estables": []}}})
    assert caen["estado"] == FALLA and caen["piezas"] == ["c3"]
    assert p.gravedad({"gravedad": {"resultado": {"fell": [], "estables": ["c1"],
                                                  "n_grounded": 1}}})["estado"] == OK


def test_lo_que_la_entrega_no_evaluo_se_justifica_o_bloquea():
    entrega = {"no_aplica": ["poses (sin estudios de movimiento declarados)",
                             "gravedad (opt-in: con_gravedad=true — MuJoCo)",
                             "acceso de herramienta: 1 fijador(es) …"]}
    ok = p.no_aplica_justificado({"entrega": entrega, "hechos": {"sin_estudios": True}})
    assert ok["estado"] == OK and len(ok["evidencia"]["justificados"]) == 1
    # con estudios declarados, «sin estudios» no se justifica; lo desconocido nunca
    malo = p.no_aplica_justificado({"entrega": {"no_aplica": [
        "poses (sin estudios de movimiento declarados)", "un chequeo nuevo que no corrió"]},
        "hechos": {"sin_estudios": False}})
    assert malo["estado"] == SIN_EVALUAR and len(malo["evidencia"]["sin_justificar"]) == 2
    assert p.semaforo_entrega({"entrega": {"veredicto": "AMARILLO", "bloqueantes": [],
                                           "avisos": [{"regla": "lint", "detalle": "x"}]}})[
        "estado"] == FALLA


def test_acceso_de_herramienta_no_evaluado_bloquea():
    rep = {"evaluados": 3, "sin_herramienta": [], "solo_boca": [],
           "no_evaluados": [{"id": "c9", "nombre": "Eje roscado", "motivo": "sin hexágono"}]}
    r = p.acceso_herramienta({"acceso": rep})
    assert r["estado"] == SIN_EVALUAR and r["piezas"] == ["c9"]
    rep["no_evaluados"], rep["solo_boca"] = [], [{"id": "c4", "nombre": "Tuerca", "bloquean": []}]
    assert p.acceso_herramienta({"acceso": rep})["estado"] == FALLA


def test_memoria_marcha_erc_y_escenarios():
    assert p.memoria({"memoria": {"veredicto": "NO CONFORME", "errores": [{"regla": "flecha"}]}})[
        "estado"] == FALLA
    assert p.memoria({"memoria": {"veredicto": "NO CONCLUYENTE"}})["estado"] == SIN_EVALUAR
    assert p.memoria({"memoria": {"veredicto": "APROBADO CON AVISOS"}})["estado"] == OK
    assert p.marcha({"marcha": {"resultado": "infiel", "detalle": "cruza la guarda 37 mm"}})[
        "estado"] == FALLA
    assert p.marcha({"marcha": {"resultado": "sin_marcha", "detalle": "x"}})["estado"] == SIN_EVALUAR
    assert p.erc({"electrico": [{"regla": "tierra", "estado": "error", "elementos": ["-M1"]}]})[
        "piezas"] == ["-M1"]
    assert p.escenarios({"escenarios": [{"escenario": "a", "estado": "aviso"}]})["estado"] == \
        SIN_EVALUAR
    assert p.escenarios({"escenarios": [{"escenario": "a", "estado": "error"}]})["estado"] == FALLA


# ------------------------------------------------------------------ choques dentro de un super-comando
def _dos_cajas(solape_mm: float) -> Document:
    """Dos piezas de UN super-comando sembrado (command_id compartido): solapan `solape_mm` en X."""
    d = Document("sembrado")
    a = d.execute("create_box", {"name": "Larguero", "width": 100, "depth": 100, "height": 100})
    b = d.execute("create_box", {"name": "Motor", "width": 100, "depth": 100, "height": 100,
                                 "position": {"x": 100 - solape_mm, "y": 0, "z": 0}})
    d.scene[b].command_id = d.scene[a].command_id
    return d


def test_choque_sembrado_dentro_de_un_super_comando_falla():
    d = _dos_cajas(10.0)  # 10 × 100 × 100 = 100 000 mm³
    it = pp.interferencia_interna(d)
    assert it["comandos"] == 1 and len(it["choques"]) == 1
    assert it["choques"][0]["volumen_mm3"] == pytest.approx(100000, rel=1e-3)
    assert p.interferencia_interna({"interna": it})["estado"] == FALLA
    # la puerta de entrega no lo ve: excluye `same_command_pairs`
    from apolo.services.delivery_inputs import delivery_inputs
    assert delivery_inputs(d, expand=lambda x: x)["interferencias"] == []


def test_un_asiento_tolerado_o_un_contacto_declarado_no_es_choque():
    it = pp.interferencia_interna(_dos_cajas(0.004))  # 40 mm³ ≤ EXCESS_TOL_MM3
    assert it["choques"] == [] and len(it["tolerados"]) == 1
    assert p.interferencia_interna({"interna": it})["evidencia"]["contactos_tolerados"] == 1
    d = _dos_cajas(10.0)
    a, b = sorted(d.scene)
    d.execute("fasten", {"name": "f1", "a": a, "b": b, "kind": "contacto"})
    assert pp.interferencia_interna(d)["choques"] == []


def test_create_belt_conveyor_v4_sin_choques_internos():
    """Medido (F1, D13b): la v3 de la faja de banda chocaba DENTRO de sí (15 choques: el
    motorreductor atravesaba el larguero 392 599 mm³, la cama entraba en las guardas, los ejes
    pasaban por los largueros sin barreno…). La v4 (montaje de taller) no choca: el testigo
    quedó en OK."""
    d = Document("faja")
    d.execute("create_belt_conveyor", {})
    it = pp.interferencia_interna(d)
    assert it["comandos"] == 1 and it["choques"] == []
    assert p.interferencia_interna({"interna": it})["estado"] == OK


# ------------------------------------------------------------------ firma, endpoint y gravedad
def test_la_firma_es_la_misma_desde_el_documento_y_desde_el_apolo():
    d = _dos_cajas(10.0)
    f0 = pp.firma(d)
    assert pp.firma(Document.from_apolo_bytes(d.to_apolo_bytes())) == f0
    d.colors["c1"] = "#ff0000"
    assert pp.firma(d) == f0  # el color no cambia lo que la puerta evalúa
    d.set_requirements({"carga_kg": 20})
    assert pp.firma(d) != f0
    assert pp.firma(Document.from_apolo_bytes(d.to_apolo_bytes())) == pp.firma(d)


def _mesa_chica() -> Document:
    d = Document("mesa")
    patas = [d.execute("create_box", {"name": f"Pata ({i})", "width": 40, "depth": 40,
                                      "height": 400, "position": {"x": x, "y": 0, "z": 200}})
             for i, x in enumerate((-200, 200))]
    t = d.execute("create_box", {"name": "Tablero", "width": 500, "depth": 300, "height": 20,
                                 "position": {"x": 0, "y": 0, "z": 410}})
    for i, pata in enumerate(patas):
        d.execute("ground", {"name": f"g{i}", "feature": pata})
        d.execute("fasten", {"name": f"f{i}", "a": t, "b": pata, "kind": "contacto"})
    return d


def test_gravedad_no_disponible_queda_sin_evaluar_y_no_aprueba(monkeypatch):
    from apolo.api.routers import validation

    def sin_mujoco(_body, **_kw):
        raise HTTPException(status_code=400, detail="MuJoCo no está instalado")

    monkeypatch.setattr(validation, "_stability", sin_mujoco)
    api.DOC = _mesa_chica()
    r = TestClient(api.app).post("/api/puerta-publicacion")
    assert r.status_code == 200, r.text
    out = r.json()
    grav = next(i for i in out["items"] if i["id"] == "entrega.gravedad")
    assert grav["estado"] == SIN_EVALUAR and "MuJoCo no está instalado" in grav["detalle"]
    assert out["aprobado"] is False and out["firma"] == pp.firma(api.DOC)
    assert {i["id"] for i in out["items"]} >= {"entrega.semaforo", "union.agarre",
                                                "memoria.veredicto", "publicado.sustitutos_fieles"}
    # el semáforo de entrega lo dice en `no_aplica`, que el ítem de la gravedad ya cubre
    assert next(i for i in out["items"] if i["id"] == "entrega.no_evaluado")["estado"] == OK


def test_endpoint_como_job_y_el_modelo_que_cambia_da_409(monkeypatch):
    from apolo.api.routers import validation

    api.DOC = _mesa_chica()
    c = TestClient(api.app)
    r = c.post("/api/puerta-publicacion?async=true")
    assert r.status_code == 202
    job = c.get(f"/api/jobs/{r.json()['job_id']}", params={"wait_s": 30}).json()
    assert job["estado"] == "ok" and job["resultado"]["version_registro"] == "31"
    grav = next(i for i in job["resultado"]["items"] if i["id"] == "entrega.gravedad")
    assert grav["estado"] == OK  # la mesa anclada no se cae
    # si el modelo cambia mientras corre la gravedad, no hay veredicto que mezcle dos modelos
    real = validation._stability

    def y_edita(body, **kw):
        api.DOC.set_requirements({"carga_kg": 5})
        return real(body, **kw)

    monkeypatch.setattr(validation, "_stability", y_edita)
    r = c.post("/api/puerta-publicacion")
    assert r.status_code == 409 and "cambió" in r.json()["detail"]


def test_la_puerta_sobre_create_belt_conveyor():
    """De punta a punta sobre la faja de la plantilla (v4): su marcha es fiel (D13), no choca por
    dentro, declara uniones y anclajes (no se cae), su bastidor es de acero, su tensor de carro
    cubre el lazo y la memoria sale conforme. No se publica sin las funciones declaradas (D15:
    metadato del proyecto, no de la plantilla)."""
    d = Document("faja")
    d.execute("create_belt_conveyor", {})
    d.set_requirements({"carga_kg": 15, "largo_paquete_mm": 400, "ancho_paquete_mm": 300,
                        "velocidad_m_s": 0.3})
    api.DOC = d
    out = TestClient(api.app).post("/api/puerta-publicacion").json()
    items = {i["id"]: i for i in out["items"]}
    est = {k: i["estado"] for k, i in items.items()}
    assert est["publicado.sustitutos_fieles"] == OK
    assert items["publicado.sustitutos_fieles"]["evidencia"]["elementos"] == {"banda": 1}
    assert items["transmision_flexible.tension"]["evidencia"]["elementos"] == {"banda": 1}
    for iid in ("montaje.interferencia_interna", "entrega.semaforo", "entrega.gravedad",
                "estructura.flecha", "estructura.vuelco", "transmision_flexible.tension",
                "memoria.veredicto", "elementos_rodantes.l10"):
        assert est[iid] == OK, (iid, items[iid]["detalle"])
    assert out["aprobado"] is False
    assert est["diseno.soluciones_por_funcion"] == FALLA  # nadie declaró por qué es así


# ------------------------------------------------------------------ generalidad (D14) y D15
def _puerta(doc) -> dict:
    """La puerta sobre `doc` sin la API: gravedad estable dada, sin marcha (lo cubren los de la API)."""
    ins = pp.reunir(doc, expand=lambda x: x, gravedad={
        "resultado": {"fell": [], "estables": list(doc.scene), "n_grounded": len(doc.grounds)},
        "motivo": ""})
    ins["marcha"] = {"resultado": "sin_marcha", "detalle": "no se corre en este test"}
    return evaluar(ins)


def _eje_con_chumaceras() -> Document:
    """Una máquina que NO es un transportador: un eje que gira sobre dos chumaceras, sin banda."""
    d = Document("eje")
    base = d.execute("create_box", {"name": "Base", "width": 600, "depth": 200, "height": 20,
                                    "position": {"x": 0, "y": 0, "z": 10}})
    sop = [d.execute("insert_component", {"component": "UCP205", "position": {"x": x, "y": 0,
                                                                             "z": 56.5}})
           for x in (-200, 200)]
    eje = d.execute("create_cylinder", {"name": "Eje Ø25 h7", "radius": 12.5, "height": 600,
                                        "axis": "x", "position": {"x": 0, "y": 0, "z": 56.5}})
    d.execute("ground", {"name": "g0", "feature": base})
    for k, s in enumerate(sop):
        d.execute("fasten", {"name": f"f{k}", "a": s, "b": base, "kind": "contacto"})
    d.execute("add_joint", {"name": "giro_eje", "type": "continua", "parent": sop[0],
                            "child": eje, "origin": {"x": 0, "y": 0, "z": 56.5},
                            "axis": {"x": 1, "y": 0, "z": 0}})
    return d


def test_una_maquina_que_no_es_transportador_tiene_sus_items_y_no_los_de_banda():
    out = _puerta(_eje_con_chumaceras())
    it = {i["id"]: i for i in out["items"]}
    assert it["transmision_flexible.tension"]["estado"] == NO_APLICA
    assert it["transmision_flexible.tension"]["detalle"] == \
        "la máquina no tiene transmisiones flexibles"
    assert it["publicado.sustitutos_fieles"]["estado"] == NO_APLICA
    assert it["elementos_rodantes.l10"]["estado"] != NO_APLICA
    assert it["elementos_rodantes.l10"]["evidencia"]["elementos"] == {"chumacera": 2}
    fam = it["diseno.soluciones_por_funcion"]
    assert fam["estado"] == FALLA and set(fam["evidencia"]["sin_declarar"]) >= {
        "apoyo_rotativo", "estructura"}


def test_una_pieza_estatica_suelta_pasa_con_lo_que_le_aplica():
    d = Document("ménsula")
    m = d.execute("create_box", {"name": "Ménsula", "width": 120, "depth": 80, "height": 10,
                                 "position": {"x": 0, "y": 0, "z": 5}})
    d.execute("ground", {"name": "g0", "feature": m})
    out = _puerta(d)
    est = {i["id"]: i["estado"] for i in out["items"]}
    malos = {k: e for k, e in est.items() if e in (FALLA, SIN_EVALUAR)}
    assert not malos, (malos, [i["detalle"] for i in out["items"] if i["id"] in malos])
    assert out["aprobado"] is True
    assert est["fabricabilidad"] == OK and est["entrega.gravedad"] == OK
    for no in ("transmision_flexible.tension", "union.agarre", "diseno.soluciones_por_funcion",
               "elementos_rodantes.l10", "accionamiento.factor_servicio"):
        assert est[no] == NO_APLICA


def test_soluciones_por_funcion_declaradas():
    d = _eje_con_chumaceras()
    fams = pp.reunir(d, expand=lambda x: x, gravedad={"resultado": None})["hechos"][
        "familias_funcion"]
    assert set(fams) == {"apoyo_rotativo", "estructura"}
    pp.poner_funciones(d, [
        {"funcion": "apoyo_rotativo", "solucion": "chumaceras de pie UCP205",
         "descartadas": [{"solucion": "bujes de bronce", "motivo": "mantenimiento de lubricación"}],
         "piezas": []},
        {"funcion": "soporte del conjunto", "solucion": "placa base anclada",
         "descartadas": [{"solucion": "bastidor soldado", "motivo": "una sola pieza basta"}],
         "piezas": ["c1"]}])
    r = p.soluciones_por_funcion({"hechos": {"familias_funcion": fams}, "funciones": d.funciones})
    assert r["estado"] == OK
    assert r["evidencia"]["familias"]["estructura"]["cubierta_por"] == "soporte del conjunto"
    # viaja en el .apolo y cambia la firma (la puerta lo evalúa)
    assert Document.from_apolo_bytes(d.to_apolo_bytes()).funciones == d.funciones


@pytest.mark.parametrize(("valor", "texto"), [
    ({"funcion": "x"}, "lista"),
    ([{"funcion": "x", "solucion": "y", "descartadas": []}], "al menos una alternativa"),
    ([{"funcion": "x", "solucion": "y", "descartadas": [{"solucion": "z"}]}], "motivo"),
    ([{"funcion": "", "solucion": "y", "descartadas": [{"solucion": "z", "motivo": "m"}]}],
     "funcion"),
    ([{"funcion": "x", "solucion": "y", "otra": 1,
       "descartadas": [{"solucion": "z", "motivo": "m"}]}], "no reconocida"),
])
def test_funciones_rechaza_con_la_correccion(valor, texto):
    from apolo.library.calidad.funciones import validar_funciones

    with pytest.raises(ValueError, match=texto):
        validar_funciones(valor)


def test_api_funciones_get_put():
    api.DOC = _mesa_chica()
    c = TestClient(api.app)
    assert c.get("/api/funciones").json()["funciones"] == []
    assert "transmision_flexible" in c.get("/api/funciones").json()["familias"]
    f0 = pp.firma(api.DOC)
    ok = c.put("/api/funciones", json={"funciones": [
        {"funcion": "estructura", "solucion": "dos patas y tablero", "piezas": ["c1"],
         "descartadas": [{"solucion": "caballete", "motivo": "menos estable"}]}]})
    assert ok.status_code == 200 and api.DOC.funciones[0]["solucion"] == "dos patas y tablero"
    assert pp.firma(api.DOC) != f0
    malo = c.put("/api/funciones", json={"funciones": [
        {"funcion": "x", "solucion": "y", "piezas": ["no-existe"],
         "descartadas": [{"solucion": "z", "motivo": "m"}]}]})
    assert malo.status_code == 400 and "no-existe" in malo.json()["detail"]
    assert len(api.DOC.funciones) == 1  # el rechazo no tocó lo guardado


# ------------------------------------------------------------------ la tool MCP
def test_la_tool_resume_lo_que_falta():
    from apolo.tools.calidad import resumir

    r = evaluar({"hechos": {}, "firma": "f"}, (_entrada("a", _r(OK)), _entrada("b", _r(FALLA))))
    corto = resumir(r)
    assert [x["id"] for x in corto["pendientes"]] == ["b"] and corto["aprobado"] is False
    assert "evidencia" not in corto["pendientes"][0]


def test_la_tool_lista_cada_caso_por_aparato_con_su_sugerencia():
    """nombres-por-funcion F6: el detalle nombraba 4 aparatos «y 9 más»; el resumen trae los casos."""
    from apolo.tools.calidad import MAX_CASOS, resumir

    casos = [{"designacion": f"-S{k}", "tipo": "pulsador", "motivo": "sin rótulo", "piezas": ["c1"],
              "sugerencia": "Marcha" if k == 1 else None} for k in range(1, MAX_CASOS + 4)]
    item = {"id": "interfaz.nombres_por_funcion", "estado": FALLA, "evidencia": {"casos": casos}}
    (p,) = resumir({"items": [item]})["pendientes"]
    assert len(p["casos"]) == MAX_CASOS and p["casos_omitidos"] == 3
    assert p["casos"][0] == {"designacion": "-S1", "tipo": "pulsador", "motivo": "sin rótulo",
                             "sugerencia": "Marcha"}
    assert "piezas" not in p["casos"][0] and "sugerencia" not in p["casos"][1]

def test_el_item_pedido_sobrevive_al_recibo():
    """Con la puerta como job, `publication_gate(item=)` perdía el filtro: `get_job` resumía."""
    import json

    from apolo.tools.calidad import de_job, recibo_puerta

    r = evaluar({"hechos": {}, "firma": "f"}, (_entrada("a", _r(OK)), _entrada("b", _r(FALLA))))
    assert "detail='item:b'" in json.loads(recibo_puerta("j1", False, "b"))["seguir"]
    assert "detail='full'" in json.loads(recibo_puerta("j1", True, ""))["seguir"]
    assert de_job(r, "item:b")["item"]["id"] == "b"
    assert "ids" in de_job(r, "item:zzz") and "pendientes" in de_job(r, "diff")