"""La etiqueta de un cambio del historial (`apolo.doc.pasos`, plan deshacer-con-etiqueta, D4).

Una aserción por fila de la gramática de D4 sobre logs y escenas de juguete (el descriptor es
puro: no necesita geometría). Lo que el `Document` hace con la etiqueta —apilarla, moverla
entre pilas, recalcularla al coalescer— está en `tests/test_deshacer_pasos.py`.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import pasos
from apolo.doc.pasos import describir


def _cmd(cid: str, tipo: str, **params) -> dict:
    return {"id": cid, "type": tipo, "params": params}


def _pieza(fid: str, nombre: str, cid: str | None = None):
    return SimpleNamespace(id=fid, name=nombre, command_id=cid or fid)


def _escena(*piezas) -> dict:
    return {p.id: p for p in piezas}


def _caja(cid: str, nombre: str, **params) -> dict:
    return _cmd(cid, "create_box", name=nombre, width=100, depth=100, height=100, **params)


def _nuevo(cmd: dict, antes=(), escena=None) -> str:
    """Etiqueta de agregar `cmd` a un log que tenía `antes`."""
    escena = escena if escena is not None else {}
    return describir(list(antes), [*antes, cmd], escena, escena)


# ------------------------------------------------------------------ un comando nuevo
def test_nuevo_con_nombre_propio():
    assert _nuevo(_caja("c1", "Soporte motor")) == "Caja «Soporte motor»"
    insertar = _cmd("c2", "insert_project", name="Faja A", attachment="abc")
    assert _nuevo(insertar) == "Insertar proyecto «Faja A»"


def test_nuevo_sin_name_se_nombra_por_la_pieza_que_referencia():
    placa = _caja("c1", "Placa base")
    escena = _escena(_pieza("c1", "Placa base"))
    taladro = _cmd("c2", "drill_hole", feature="c1", diameter=10)
    assert _nuevo(taladro, [placa], escena) == "Taladro «Placa base»"
    redondeo = _cmd("c3", "fillet", feature="c1", radius=2)
    assert _nuevo(redondeo, [placa], escena) == "Redondeo «Placa base»"


def test_nuevo_sin_nada_que_lo_nombre_va_solo_el_titulo():
    assert _nuevo(_cmd("c1", "create_box", name="")) == "Caja"
    assert _nuevo(_cmd("c2", "fillet", feature="c99", radius=2)) == "Redondeo"


def test_tipo_desconocido_se_llama_comando():
    assert _nuevo(_cmd("c1", "tipo_que_no_existe", name="Pieza X")) == "Comando «Pieza X»"


# ------------------------------------------------------------------ transform
@pytest.mark.parametrize(("translate", "rotate", "esperado"), [
    ({"x": 25, "y": 0, "z": 0}, {}, "Mover «Guarda tambor motriz»"),
    ({}, {"x": 0, "y": 0, "z": 90}, "Rotar «Guarda tambor motriz»"),
    ({"z": -5}, {"y": 15}, "Mover y rotar «Guarda tambor motriz»"),
    ({"x": "=L/2"}, {}, "Mover «Guarda tambor motriz»"),  # una expresión cuenta como mover
    ({"x": 0}, {"z": 0}, "Mover / Rotar «Guarda tambor motriz»"),  # nada: el título
])
def test_transform_se_nombra_por_su_verbo(translate, rotate, esperado):
    guarda = _caja("c1", "Guarda tambor motriz")
    escena = _escena(_pieza("c1", "Guarda tambor motriz"))
    mover = _cmd("c2", "transform", feature="c1", translate=translate, rotate=rotate)
    assert _nuevo(mover, [guarda], escena) == esperado


def test_transform_group_dice_que_mueve_un_grupo():
    mover = _cmd("c9", "transform_group", group="Faja A", translate={"x": 100})
    assert _nuevo(mover) == "Mover grupo «Faja A»"
    girar = _cmd("c9", "transform_group", group="Faja A", rotate={"z": 90})
    assert _nuevo(girar) == "Rotar grupo «Faja A»"


# ------------------------------------------------------------------ variables
def test_variable_nueva_editada_y_eliminada():
    nueva = _cmd("c1", "set_variable", name="L", expression="3200")
    assert _nuevo(nueva) == "Variable «L» = 3200"
    con_igual = _cmd("c1", "set_variable", name="L", expression="=2*ancho + 40")
    assert _nuevo(con_igual) == "Variable «L» = 2*ancho + 40"
    vieja = _cmd("c1", "set_variable", name="L", expression="2000")
    assert describir([vieja], [nueva], {}, {}) == "Variable «L»: 2000 → 3200"
    assert describir([vieja], [], {}, {}) == "Eliminar Variable «L»"


# ------------------------------------------------------------------ un comando editado
def test_editado_nombra_los_campos_por_su_titulo():
    antes = _caja("c1", "Soporte motor")
    movida = _caja("c1", "Soporte motor", position={"x": 50})
    assert describir([antes], [movida], {}, {}) == "Editar Caja «Soporte motor»: Posición"
    dos = {**antes, "params": {**antes["params"], "width": 200, "height": 50}}
    assert describir([antes], [dos], {}, {}) == "Editar Caja «Soporte motor»: Ancho (X) y Alto (Z)"
    cuatro = {**antes, "params": {**dos["params"], "depth": 7, "position": {"x": 1}}}
    assert (describir([antes], [cuatro], {}, {})
            == "Editar Caja «Soporte motor»: Ancho (X), Fondo (Y) y 2 más")


def test_campo_sin_titulo_no_se_nombra_y_suma_en_el_resto():
    antes = _caja("c1", "Soporte")
    rara = {**antes, "params": {**antes["params"], "clave_vieja": 3}}
    assert describir([antes], [rara], {}, {}) == "Editar Caja «Soporte»: 1 parámetro"
    mas = {**antes, "params": {**rara["params"], "width": 5}}
    assert describir([antes], [mas], {}, {}) == "Editar Caja «Soporte»: Ancho (X) y 1 más"


def test_editado_sin_name_se_nombra_por_su_pieza():
    redondeo = _cmd("c2", "fillet", feature="c1", radius=2)
    otro = _cmd("c2", "fillet", feature="c1", radius=5)
    escena = _escena(_pieza("c1", "Placa"))
    assert describir([redondeo], [otro], escena, escena).startswith("Editar Redondeo «Placa»: ")


# ------------------------------------------------------------------ un comando eliminado
def test_eliminado():
    caja = _caja("c1", "Soporte motor")
    escena = _escena(_pieza("c1", "Soporte motor"))
    assert describir([caja], [], escena, {}) == "Eliminar Caja «Soporte motor»"


def test_pieza_eliminada_se_nombra_desde_la_escena_de_antes():
    caja = _cmd("c1", "create_box", name="")  # sin name: lo nombra la pieza que creó
    antes = _escena(_pieza("c1", "Soporte motor"))
    assert describir([caja], [], antes, {}) == "Eliminar Caja «Soporte motor»"
    borrar = _cmd("c2", "delete_feature", feature="c1")  # la pieza ya no está DESPUÉS
    assert describir([caja], [caja, borrar], antes, {}) == "Eliminar «Soporte motor»"


def test_pattern_group_se_nombra_por_la_pieza_de_su_fuente_no_por_el_id():
    caja = _caja("c1", "Rodillo")
    escena = _escena(_pieza("c1", "Rodillo"))
    patron = _cmd("c2", "pattern_group", source="c1", count=3, spacing={"x": 100})
    assert _nuevo(patron, [caja], escena) == "Patrón de grupo «Rodillo»"


def test_piezas_prefijadas_de_insert_project_nombran_al_comando():
    cmd = _cmd("c7", "tipo_raro")
    escena = _escena(_pieza("c7_c1", "Larguero (+Y)", "c7_c1"))
    assert _nuevo(cmd, (), escena) == "Comando «Larguero (+Y)»"


# ------------------------------------------------------------------ lotes
def test_lote_homogeneo_hasta_tres_nombres():
    log = [_caja(f"c{i}", n) for i, n in enumerate(("Guarda", "Tapa", "Motor"), 1)]
    escena = _escena(*(_pieza(c["id"], c["params"]["name"]) for c in log))
    movs = [_cmd(f"c{i}", "transform", feature=f"c{i - 3}", translate={"x": 5})
            for i in (4, 5, 6)]
    assert describir(log, log + movs, escena, escena) == "Mover ×3: «Guarda», «Tapa» y «Motor»"
    assert describir([], log, {}, escena) == "Caja ×3: «Guarda», «Tapa» y «Motor»"
    editados = [{**c, "params": {**c["params"], "width": 5}} for c in log[:2]]
    assert describir(log[:2], editados, escena, escena) == "Editar Caja ×2: «Guarda» y «Tapa»"


def test_lote_homogeneo_de_mas_de_tres_dice_cuantos_mas():
    log = [_caja(f"c{i}", n) for i, n in enumerate("ABCD", 1)]
    assert describir(log, [], {}, {}) == "Eliminar ×4: «A», «B» y 2 más"


def test_eliminar_de_varios_tipos_es_un_solo_verbo():
    log = [_caja("c1", "Soporte"), _cmd("c2", "fasten", name="perno_soporte", a="c1", b="c9")]
    assert describir(log, [], {}, {}) == "Eliminar ×2: «Soporte» y «perno_soporte»"


def test_lote_de_transforms_con_verbos_distintos_cae_al_titulo():
    log = [_caja("c1", "A")]
    escena = _escena(_pieza("c1", "A"))
    movs = [_cmd("c2", "transform", feature="c1", translate={"x": 5}),
            _cmd("c3", "transform", feature="c1", rotate={"z": 5})]
    assert describir(log, log + movs, escena, escena) == "Mover / Rotar ×2: «A»"


def test_lote_mixto_cuenta_honesto():
    viejos = [_caja(f"c{i}", f"P{i}") for i in range(1, 22)]
    editados = [{**c, "params": {**c["params"], "width": 7}} for c in viejos]
    nuevos = [_caja(f"c{i}", f"N{i}") for i in range(22, 34)]
    assert (describir(viejos, editados + nuevos, {}, {})
            == "Lote de 33 comandos: 12 nuevos, 21 editados")
    uno = [_caja("c1", "A"), _caja("c2", "B")]
    otro = [{**uno[0], "params": {**uno[0]["params"], "width": 1}}, _caja("c3", "C")]
    assert describir(uno, otro, {}, {}) == "Lote de 3 comandos: 1 nuevo, 1 editado, 1 eliminado"
    distintos = [_caja("c1", "A"), _cmd("c2", "create_cylinder", name="B")]
    assert describir([], distintos, {}, {}) == "Lote de 2 comandos: 2 nuevos"


# ------------------------------------------------------------------ sin cambios e intención
def test_sin_cambios_con_y_sin_foco():
    caja = _caja("c1", "Soporte motor")
    assert describir([caja], [caja], {}, {}, foco="c1") == "Editar Caja «Soporte motor» (sin cambios)"
    assert describir([caja], [caja], {}, {}) == "Sin cambios en el modelo"
    assert describir([caja], [caja], {}, {}, foco="c99") == "Sin cambios en el modelo"


def test_la_intencion_gana_sobre_el_diff():
    vieja = _cmd("c1", "set_variable", name="largo_total", expression="4000")
    nueva = _cmd("c1", "set_variable", name="largo_total", expression="3200")
    texto = "Aplicar variante «3.2m (prueba paramétrica)»"
    assert describir([vieja], [nueva], {}, {}, intencion=texto) == texto
    assert describir([vieja], [nueva], {}, {}, intencion="  ") == "Variable «largo_total»: 4000 → 3200"


# ------------------------------------------------------------------ topes
def test_nombres_largos_se_cortan_a_40_y_la_etiqueta_a_120():
    largo = "Ménsula soldada de la chumacera del tambor motriz lado operador"
    etiqueta = _nuevo(_caja("c1", largo))
    nombre = re.search(r"«(.*)»", etiqueta).group(1)
    assert len(nombre) == 40 and nombre.endswith("…") and largo.startswith(nombre[:-1])
    log = [_caja(f"c{i}", f"{i} {largo}") for i in range(1, 4)]  # 3 × 40 no caben en 120
    lote = describir([], log, {}, {})
    assert len(lote) <= 120 and lote.startswith("Caja ×3: «") and lote.endswith("más")
    expr = _cmd("c1", "set_variable", name="x" * 40, expression="1 + " * 60 + "1")
    assert len(_nuevo(expr)) <= 120


def _minimos(tipo: str) -> dict:
    """Params con todas las referencias a un id que ninguna escena tiene."""
    campos = REGISTRY[tipo].model.model_fields
    p = {k: "c1" for k in ("feature", "target", "feature_a", "a", "parent", "source")
         if k in campos}
    if "features" in campos:
        p["features"] = ["c1", "c2"]
    return p


@pytest.mark.parametrize("tipo", sorted(REGISTRY))
def test_nunca_aparece_un_id_ni_un_type_crudo(tipo):
    cmd = {"id": "c45", "type": tipo, "params": _minimos(tipo)}
    sin_name = {**cmd, "params": {k: v for k, v in cmd["params"].items() if k != "name"}}
    otro = {**sin_name, "params": {**sin_name["params"], "zz": 1}}
    for etiqueta in (describir([], [sin_name], {}, {}), describir([sin_name], [], {}, {}),
                     describir([sin_name], [otro], {}, {}),
                     describir([sin_name], [sin_name], {}, {}, foco="c45")):
        assert not re.search(r"\bc\d+(_\w+)?\b", etiqueta), etiqueta
        assert tipo not in etiqueta and "zz" not in etiqueta, etiqueta
        assert 0 < len(etiqueta) <= 120


# ------------------------------------------------------------------ D10 y las pilas
def test_etiqueta_nunca_lanza(monkeypatch):
    def revienta(*_a, **_k):
        raise RuntimeError("descriptor roto")

    monkeypatch.setattr(pasos, "describir", revienta)
    assert pasos.etiqueta([], [_caja("c1", "A")], {}, {}) == "Cambio en el modelo"


def test_error_de_pasos():
    assert pasos.error_de_pasos(1, 3, "deshacer") is None
    assert pasos.error_de_pasos(3, 3, "rehacer") is None
    assert pasos.error_de_pasos(1, 0, "deshacer") == "Nada que deshacer"
    assert pasos.error_de_pasos(2, 1, "deshacer") == "Sólo hay 1 cambio para deshacer"
    assert pasos.error_de_pasos(5, 3, "rehacer") == "Sólo hay 3 cambios para rehacer"
    for malo in (0, -1, 1.5, True, "2", None):
        assert "entero" in pasos.error_de_pasos(malo, 3, "deshacer")


def test_trasladar_etiqueta_cada_entrada_con_el_cambio_que_la_revierte():
    pila = [{"commands": [i], "hidden": {"x"}, "etiqueta": f"E{i}"} for i in range(1, 5)]
    actual = {"commands": [5], "hidden": set()}
    origen, destino = pasos.trasladar(pila, [], 3, actual, 50)
    assert [e["commands"] for e in origen] == [[1]]
    assert [(e["commands"], e["etiqueta"]) for e in destino] == [
        ([5], "E4"), ([4], "E3"), ([3], "E2")]
    assert all(e["hidden"] == set() for e in destino)
    assert pila[-1]["etiqueta"] == "E4" and len(pila) == 4  # pura: no toca la entrada
    assert len(pasos.trasladar(pila, [{}] * 50, 2, actual, 50)[1]) == 50  # el tope
