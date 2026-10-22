"""Puerta de publicación F2 — VIDA ÚTIL (plan puerta-de-publicacion D2/D3, D9): las reglas de
`engineering_check` llevadas a ítems con umbrales industriales, el ítem y su agregado, y los
ítems de función mecánica de un documento real."""

import pytest

from apolo.doc import Document
from apolo.library.calidad.item import (
    FALLA,
    NO_APLICA,
    OK,
    SIN_EVALUAR,
    Item,
    aprobado,
    peor,
    recortar,
)
from apolo.library.calidad.vida_util import INFORMATIVAS, controlar_vida_util
from apolo.services.calidad_mecanica import items_funcion_mecanica


def _regla(nombre, estado="ok", fs=None, **calc):
    r = {"regla": nombre, "estado": estado, "detalle": f"{nombre}: {estado}"}
    if fs is not None or calc:
        r["calc"] = {"fs": fs, **calc}
    return r


def _por_id(reglas, **kw):
    return {i.id: i for i in controlar_vida_util(reglas, **kw)}


# ── el ítem ─────────────────────────────────────────────────────────────────────────────


def test_item_y_agregado():
    with pytest.raises(ValueError):
        Item("x", "x", "VERDE", "m", "n")
    assert peor([OK, SIN_EVALUAR, NO_APLICA]) == SIN_EVALUAR
    assert peor([OK, FALLA, SIN_EVALUAR]) == FALLA
    assert peor([NO_APLICA]) == NO_APLICA
    ok = Item("a", "a", OK, "m", "n")
    assert aprobado([ok, Item("b", "b", NO_APLICA, "m", "n")])
    assert not aprobado([ok, Item("c", "c", SIN_EVALUAR, "m", "n")])  # SIN_EVALUAR bloquea
    assert not aprobado([Item("d", "d", NO_APLICA, "m", "n")])
    assert aprobado([ok.to_dict()])
    assert recortar(list(range(25)), 20) == {"casos": list(range(20)), "casos_omitidos": 5}


# ── umbrales ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("fs", "estado"), [(0.5, FALLA), (1.0, OK), (3.0, OK)])
def test_l10_contra_20000_h(fs, estado):
    it = _por_id([_regla("vida L10 de rodamientos", "aviso" if fs < 1 else "ok", fs,
                         resultado="L10 = …")])["vida.l10"]
    assert it.estado == estado
    assert it.evidencia["valores"][0]["L10_h"] == round(fs * 20000)


def test_l10_no_calculable_queda_sin_evaluar():
    it = _por_id([_regla("vida L10 de rodamientos", "aviso")])["vida.l10"]
    assert it.estado == SIN_EVALUAR


@pytest.mark.parametrize(("regla", "fs", "estado"), [
    ("motorización", 1.0, OK),      # P_motor / P_absorbida = 1,0 × 1,3 = 1,30
    ("motorización", 0.9, FALLA),   # 1,17 < 1,25
    ("motor", 0.9, OK),             # plantilla de rodillos: ×1,5 de arranque → 1,35
    ("par del motor", 1.2, FALLA),
])
def test_factor_de_servicio(regla, fs, estado):
    assert _por_id([_regla(regla, "ok", fs)])["vida.factor_servicio"].estado == estado


def test_factor_de_servicio_sin_regla():
    assert _por_id([], hay_motor=True)["vida.factor_servicio"].estado == SIN_EVALUAR
    assert _por_id([], hay_motor=False)["vida.factor_servicio"].estado == NO_APLICA
    gravedad = _regla("motorización", "ok")  # «Transportador de gravedad (sin motor)»
    assert _por_id([gravedad])["vida.factor_servicio"].estado == NO_APLICA


@pytest.mark.parametrize(("reglas", "iid", "estado"), [
    ([_regla("transmisión por cadena · lazo", "ok", 1.1)], "vida.cadena", FALLA),
    ([_regla("transmisión por cadena · lazo", "ok", 1.5)], "vida.cadena", OK),
    ([_regla("cadena desfasada · lazo", "aviso")], "vida.cadena", FALLA),
    ([_regla("pandeo de patas", "ok", 2.5)], "vida.pandeo", FALLA),
    ([_regla("estabilidad al vuelco", "aviso", 0.8)], "vida.vuelco", FALLA),
    ([_regla("flecha de viga · larguero", "ok", 1.4)], "vida.flecha", OK),
    ([_regla("unión apernada · u1", "aviso", 1.2)], "vida.uniones", FALLA),   # u = 0,83
    ([_regla("unión apernada · u1", "ok", 2.0)], "vida.uniones", OK),         # u = 0,5
    ([_regla("unión apernada · u1", "ok")], "vida.uniones", OK),              # redundante
    ([_regla("soldadura · s1", "aviso", 1.1)], "vida.soldaduras", FALLA),
    ([_regla("uniones apernadas sin dimensionar", "aviso")], "vida.dimensionadas", FALLA),
])
def test_umbrales_por_familia(reglas, iid, estado):
    it = _por_id(reglas)[iid]
    assert it.estado == estado
    if estado != OK:
        assert it.evidencia["casos"]


def test_uniones_dimensionadas_sin_regla_resumen():
    assert _por_id([], hay_uniones=True)["vida.dimensionadas"].estado == OK
    assert _por_id([], hay_uniones=False)["vida.dimensionadas"].estado == NO_APLICA


# ── el resto: error → FALLA; aviso → FALLA salvo las informativas ─────────────────────


def test_un_aviso_que_debe_fallar_y_uno_informativo():
    it = _por_id([_regla("adherencia del tambor motriz", "aviso"),
                  _regla("geometría", "aviso")])["vida.reglas"]
    assert it.estado == FALLA
    assert [c["regla"] for c in it.evidencia["casos"]] == ["adherencia del tambor motriz"]
    assert it.evidencia["informativas"] == ["geometría"]
    assert _por_id([_regla("geometría", "aviso")])["vida.reglas"].estado == OK
    assert all(INFORMATIVAS.values())  # cada informativa dice su porqué


def test_error_siempre_falla():
    assert _por_id([_regla("geometría", "error")])["vida.reglas"].estado == FALLA
    assert _por_id([_regla("pre-entrega · barreno sin perno", "aviso")])[
        "vida.reglas"].estado == FALLA


# ── sobre un documento ──────────────────────────────────────────────────────────────────


def test_items_de_funcion_mecanica_de_un_documento():
    doc = Document("faja")
    doc.execute("create_belt_conveyor", {"tensor": "ninguno"})
    doc.execute("create_take_up", {"position": {"x": -2000, "z": 845}})
    doc.set_requirements({"carga_kg": 30, "largo_paquete_mm": 400})
    items = {i.id: i for i in items_funcion_mecanica(doc)}
    assert {"agarre.cruza", "agarre.retencion", "agarre.largo", "tensor.reconocido",
            "tensor.carrera", "tensor.agarre", "vida.l10", "vida.factor_servicio",
            "vida.reglas"} <= set(items)
    assert items["agarre.cruza"].estado == OK                # los dos pernos del tensor
    assert items["tensor.carrera"].estado == FALLA           # 24 mm contra ~107
    assert all(set(i.to_dict()) == {"id", "titulo", "estado", "modo_de_falla", "norma",
                                    "evidencia", "piezas", "detalle"} for i in items.values())
    assert not aprobado(items.values())
